"""
PostgreSQL + pgvector 向けの文字起こしベクトル同期と検索（アプリ側でチャンク化・埋め込み）。

pgai の destination / vectorizer は使わず、自前テーブルに VECTOR 列へ保存する。
"""
from __future__ import annotations

import os
import re
import sqlite3
from typing import Any

try:
    from dotenv import load_dotenv

    _BASE = os.environ.get(
        "TRANSCRIPTION_BASE_DIR", os.path.dirname(os.path.abspath(__file__))
    )
    load_dotenv(os.path.join(_BASE, ".env"))
except ImportError:
    _BASE = os.environ.get(
        "TRANSCRIPTION_BASE_DIR", os.path.dirname(os.path.abspath(__file__))
    )

PG_DSN_ENV = "TRANSCRIPTION_DATABASE_URL"
PG_DSN_ALT = "DATABASE_URL"

# ベクトル行を格納するテーブル（sql/vector_transcript_setup.sql と一致）
PG_VECTOR_TABLE_ENV = "TRANSCRIPTION_VECTOR_TABLE"
DEFAULT_VECTOR_TABLE = "public.transcript_vector_chunks"

CHUNK_CHARS_ENV = "TRANSCRIPTION_CHUNK_CHARS"
CHUNK_OVERLAP_ENV = "TRANSCRIPTION_CHUNK_OVERLAP"
DEFAULT_CHUNK_CHARS = 512
DEFAULT_CHUNK_OVERLAP = 50


def get_pg_dsn() -> str | None:
    dsn = (os.environ.get(PG_DSN_ENV) or "").strip()
    if dsn:
        return dsn
    return (os.environ.get(PG_DSN_ALT) or "").strip() or None


def get_vector_table_sql_ident() -> str:
    t = (os.environ.get(PG_VECTOR_TABLE_ENV) or DEFAULT_VECTOR_TABLE).strip()
    if not re.match(r"^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$", t):
        raise ValueError(
            f"TRANSCRIPTION_VECTOR_TABLE は schema.table 形式の英数字のみ: {t!r}"
        )
    return t


def _chunk_size() -> int:
    try:
        return max(64, int((os.environ.get(CHUNK_CHARS_ENV) or str(DEFAULT_CHUNK_CHARS)).strip()))
    except ValueError:
        return DEFAULT_CHUNK_CHARS


def _chunk_overlap() -> int:
    try:
        o = int((os.environ.get(CHUNK_OVERLAP_ENV) or str(DEFAULT_CHUNK_OVERLAP)).strip())
        return max(0, min(o, _chunk_size() - 1))
    except ValueError:
        return DEFAULT_CHUNK_OVERLAP


def _chunk_text(text: str) -> list[str]:
    """文字単位でチャンク化（重複あり）。"""
    chunk_size = _chunk_size()
    overlap = _chunk_overlap()
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    step = max(1, chunk_size - overlap)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start += step
    return chunks


def _format_time_mm_ss(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}分{s}秒"


def _build_content_line(
    filename: str,
    speaker: str,
    start: float,
    end: float,
    text: str,
) -> str:
    sp = speaker or "UNKNOWN"
    return (
        f"[ファイル: {filename}] [{sp}] "
        f"({_format_time_mm_ss(start)}〜{_format_time_mm_ss(end)}) {text}"
    )


def _open_pg():
    import psycopg

    dsn = get_pg_dsn()
    if not dsn:
        return None
    return psycopg.connect(dsn, autocommit=True)


def count_transcript_vector_chunks() -> int | None:
    """transcript_vector_chunks の行数。接続・テーブルエラー時は None。"""
    if not get_pg_dsn():
        return None
    tbl = get_vector_table_sql_ident()
    schema, tname = tbl.split(".", 1)
    pg = _open_pg()
    if not pg:
        return None
    try:
        with pg.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{tname}"')
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return None
    finally:
        pg.close()


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


def sync_file_from_sqlite(file_id: int, sqlite_db_path: str) -> tuple[bool, str | None]:
    """
    SQLite の1ファイル分をチャンク化し、設定されたバックエンドで埋め込み、PostgreSQL に保存する。
    """
    dsn = get_pg_dsn()
    if not dsn:
        return False, "TRANSCRIPTION_DATABASE_URL が未設定です"

    conn_sql = sqlite3.connect(sqlite_db_path, timeout=30.0)
    try:
        cur_sql = conn_sql.cursor()
        cur_sql.execute(
            """
            SELECT f.id, f.filename, f.project_id, p.name
            FROM files f
            JOIN projects p ON f.project_id = p.id
            WHERE f.id = ?
            """,
            (file_id,),
        )
        meta = cur_sql.fetchone()
        if not meta:
            return False, "SQLite にファイルがありません"
        _, filename, project_id, project_name = meta
        cur_sql.execute(
            """
            SELECT segment_index, speaker, text, start_time, end_time
            FROM segments
            WHERE file_id = ?
            ORDER BY segment_index
            """,
            (file_id,),
        )
        segs = cur_sql.fetchall()
    finally:
        conn_sql.close()

    if not segs:
        return False, "セグメントがありません（同期スキップ）"

    rows_to_insert: list[tuple[Any, ...]] = []
    texts_for_embed: list[str] = []

    for segment_index, speaker, text, start_time, end_time in segs:
        t = (text or "").strip()
        if not t:
            continue
        line = _build_content_line(
            filename, str(speaker or ""), float(start_time), float(end_time), t
        )
        parts = _chunk_text(line)
        for chunk_index, chunk in enumerate(parts):
            texts_for_embed.append(chunk)
            rows_to_insert.append(
                (
                    file_id,
                    filename,
                    project_id,
                    project_name,
                    int(segment_index),
                    int(chunk_index),
                    str(speaker or ""),
                    float(start_time),
                    float(end_time),
                    chunk,
                )
            )

    if not rows_to_insert:
        return False, "埋め込み対象テキストがありません"

    try:
        from embedding_providers import embed_texts

        embeddings = embed_texts(texts_for_embed)
    except Exception as e:
        return False, f"埋め込み API エラー: {e}"

    if len(embeddings) != len(rows_to_insert):
        return False, "埋め込み件数がチャンク件数と一致しません"

    tbl = get_vector_table_sql_ident()
    schema, table = tbl.split(".", 1)

    pg = _open_pg()
    if not pg:
        return False, "PostgreSQL 接続に失敗しました"
    try:
        with pg.cursor() as cur:
            cur.execute(
                f'DELETE FROM "{schema}"."{table}" WHERE file_id = %s',
                (file_id,),
            )
            insert_sql = f"""
                INSERT INTO "{schema}"."{table}"
                (file_id, filename, project_id, project_name, segment_index,
                 chunk_index, speaker, start_time_sec, end_time_sec, content, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
            """
            for row, emb in zip(rows_to_insert, embeddings):
                cur.execute(
                    insert_sql,
                    row + (_vector_literal(emb),),
                )
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        pg.close()


def delete_file_from_pg(file_id: int) -> None:
    if not get_pg_dsn():
        return
    tbl = get_vector_table_sql_ident()
    schema, tname = tbl.split(".", 1)
    pg = _open_pg()
    if not pg:
        return
    try:
        with pg.cursor() as cur:
            cur.execute(
                f'DELETE FROM "{schema}"."{tname}" WHERE file_id = %s',
                (file_id,),
            )
    except Exception:
        pass
    finally:
        pg.close()


def search_transcripts(
    query: str,
    *,
    limit: int = 15,
) -> tuple[list[dict[str, Any]], str | None]:
    q = (query or "").strip()
    if not q:
        return [], None
    if not get_pg_dsn():
        return [], "TRANSCRIPTION_DATABASE_URL が未設定です"

    try:
        from embedding_providers import embed_texts

        q_emb = embed_texts([q])
        if not q_emb:
            return [], "クエリの埋め込みが空です"
        vec_lit = _vector_literal(q_emb[0])
    except Exception as e:
        return [], f"クエリの埋め込みに失敗しました: {e}"

    tbl = get_vector_table_sql_ident()
    schema, tname = tbl.split(".", 1)

    pg = _open_pg()
    if not pg:
        return [], "PostgreSQL に接続できません"

    rows_out: list[dict[str, Any]] = []
    try:
        with pg.cursor() as cur:
            cur.execute(
                f"""
                SELECT file_id, filename, project_name, speaker, segment_index,
                       chunk_index, start_time_sec, end_time_sec, content,
                       (embedding <=> %s::vector) AS distance
                FROM "{schema}"."{tname}"
                ORDER BY distance
                LIMIT %s
                """,
                (vec_lit, int(limit)),
            )
            for row in cur.fetchall():
                rows_out.append(
                    {
                        "file_id": row[0],
                        "filename": row[1],
                        "project_name": row[2],
                        "speaker": row[3],
                        "segment_index": row[4],
                        "chunk_index": row[5],
                        "start_time_sec": float(row[6]) if row[6] is not None else 0.0,
                        "end_time_sec": float(row[7]) if row[7] is not None else 0.0,
                        "content": row[8] or "",
                        "distance": float(row[9]) if row[9] is not None else None,
                    }
                )
        return rows_out, None
    except Exception as e:
        return [], f"検索 SQL でエラー: {e}"
    finally:
        pg.close()

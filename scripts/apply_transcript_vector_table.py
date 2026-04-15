#!/usr/bin/env python3
"""TRANSCRIPTION_DATABASE_URL（または DATABASE_URL）で transcript_vector_chunks を作成する。"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

try:
    import psycopg
except ImportError:
    print("psycopg が必要です: pip install 'psycopg[binary]'", file=sys.stderr)
    sys.exit(1)

_BASE = Path(__file__).resolve().parent.parent


def _pick_sql_rel() -> str:
    dim_s = (os.environ.get("TRANSCRIPTION_EMBEDDING_DIMENSIONS") or "").strip()
    if dim_s:
        d = int(dim_s)
        if d == 768:
            return "sql/vector_transcript_setup_ollama.sql"
        if d == 1536:
            return "sql/vector_transcript_setup.sql"
        raise SystemExit(
            f"TRANSCRIPTION_EMBEDDING_DIMENSIONS={d} 用の固定 SQL が未用意です（768 または 1536）。"
            f" 必要なら sql/ をコピーして VECTOR({d}) に合わせてください。"
        )
    b = (os.environ.get("TRANSCRIPTION_EMBEDDING_BACKEND") or "openai").strip().lower()
    if b in ("ollama", "gemini"):
        return "sql/vector_transcript_setup_ollama.sql"
    if b == "openai":
        return "sql/vector_transcript_setup.sql"
    if b == "huggingface":
        raise SystemExit(
            "huggingface は次元がモデル依存です。TRANSCRIPTION_EMBEDDING_DIMENSIONS を設定し、"
            "sql/vector_transcript_setup.sql をコピーして VECTOR(n) を合わせた SQL を適用してください。"
        )
    return "sql/vector_transcript_setup.sql"


def _sql_without_full_line_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _split_sql_statements(text: str) -> list[str]:
    parts = re.split(r";\s*", text)
    return [p.strip() for p in parts if p.strip()]


def main() -> None:
    if load_dotenv:
        load_dotenv(_BASE / ".env")
    dsn = (os.environ.get("TRANSCRIPTION_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if not dsn:
        raise SystemExit("TRANSCRIPTION_DATABASE_URL または DATABASE_URL を .env に設定してください。")

    rel = _pick_sql_rel()
    path = _BASE / rel
    raw = path.read_text(encoding="utf-8")
    body = _sql_without_full_line_comments(raw)
    stmts = _split_sql_statements(body)

    with psycopg.connect(dsn, autocommit=True) as conn:
        for stmt in stmts:
            conn.execute(stmt + ";")

    print(f"適用しました: {rel}")


if __name__ == "__main__":
    main()

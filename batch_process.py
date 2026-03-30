"""
音声ファイルの文字起こし・話者分離（AssemblyAI API）を行い、データベースに保存します。
"""
import gc
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from database_schema import create_database_schema

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# --- 設定 ---
BASE_DIR = os.environ.get("TRANSCRIPTION_BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "transcription.db")

# AssemblyAI speech_model: universal=高精度, nano=速度優先（環境変数 ASSEMBLYAI_SPEECH_MODEL で切替）
_SPEECH_MODEL_ENV = "ASSEMBLYAI_SPEECH_MODEL"


def _resolve_speech_model(aai: Any) -> Any:
    """aai.SpeechModel.universal（既定）または nano（速度優先）。"""
    raw = os.environ.get(_SPEECH_MODEL_ENV, "universal").strip().lower()
    if raw in ("nano", "speed", "fast"):
        return aai.SpeechModel.nano
    return aai.SpeechModel.universal

# 辞書登録
correction_dict = {
    "カルテ": "KARTE",
    "ジャーニー": "Journey",
    "シグナルズ": "Signals",
    "グーグル": "Google",
    "ルッカー": "Looker",
}


def resolve_assemblyai_api_key(explicit: Optional[str] = None) -> str:
    """環境変数または呼び出し元から渡されたキーを返す（空なら空文字）。"""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    return os.environ.get("ASSEMBLYAI_API_KEY", "").strip()


def _format_speaker_label(raw: Optional[str]) -> str:
    """AssemblyAI の話者ラベルを「Speaker A」形式に揃える。"""
    s = (raw or "").strip()
    if not s:
        return "Speaker A"
    if s.upper().startswith("SPEAKER"):
        if s.startswith("Speaker"):
            return s
        return re.sub(r"^SPEAKER_?", "Speaker ", s, count=1, flags=re.I).strip()
    return f"Speaker {s}"


def get_audio_files(base_dir: str) -> List[str]:
    """輪読会ファイルのリストを取得します。"""
    audio_extensions = [".mp4", ".wav", ".mp3", ".m4a", ".flac"]
    files: List[str] = []
    for ext in audio_extensions:
        pattern = f"輪読会*{ext}"
        found_files = list(Path(base_dir).glob(pattern))
        files.extend([str(f) for f in found_files])
    files.sort()
    return files


def process_audio_file(
    audio_file: str,
    db_path: str,
    project_id: int = 1,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    単一の音声ファイルを AssemblyAI で処理してデータベースに保存します。

    Args:
        audio_file: 音声ファイルのパス
        db_path: データベースファイルのパス
        project_id: プロジェクトID
        api_key: AssemblyAI API キー（未指定時は環境変数 ASSEMBLYAI_API_KEY）
    """
    import assemblyai as aai

    key = resolve_assemblyai_api_key(api_key)
    if not key:
        return {
            "success": False,
            "filename": os.path.basename(audio_file),
            "error": (
                "AssemblyAI の API キーが設定されていません。\n\n"
                "Streamlit Cloud: Secrets に ASSEMBLYAI_API_KEY を設定してください。\n"
                "ローカル: 環境変数 ASSEMBLYAI_API_KEY または .env に設定してください。"
            ),
        }

    filename = os.path.basename(audio_file)
    file_size = os.path.getsize(audio_file)

    print(f"\n{'=' * 60}")
    print(f"処理開始: {filename} (project_id={project_id}) [AssemblyAI]")
    print(f"{'=' * 60}")

    aai.settings.api_key = key
    speech_model = _resolve_speech_model(aai)
    print(f"speech_model: {speech_model.value}")
    config = aai.TranscriptionConfig(
        speaker_labels=True,
        language_code="ja",
        speech_model=speech_model,
    )

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT OR REPLACE INTO files
            (filename, filepath, file_size, status, updated_at, project_id)
            VALUES (?, ?, ?, 'processing', CURRENT_TIMESTAMP, ?)
        """,
            (filename, audio_file, file_size, project_id),
        )

        file_id = cursor.lastrowid
        if file_id is None:
            cursor.execute(
                "SELECT id FROM files WHERE project_id = ? AND filename = ?",
                (project_id, filename),
            )
            result = cursor.fetchone()
            if result:
                file_id = result[0]
            else:
                raise RuntimeError("ファイルIDの取得に失敗しました")

        conn.commit()

        print("--- AssemblyAI で文字起こし・話者分離 ---")
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(audio_file, config=config)

        if transcript.status == aai.TranscriptStatus.error:
            err = transcript.error or "不明なエラー"
            raise RuntimeError(err)

        audio_duration = 0.0
        try:
            ad = getattr(transcript, "audio_duration", None)
            if ad is not None:
                audio_duration = float(ad)
        except (TypeError, ValueError):
            audio_duration = 0.0
        if audio_duration <= 0 and transcript.utterances:
            try:
                audio_duration = max(u.end for u in transcript.utterances) / 1000.0
            except (TypeError, ValueError):
                audio_duration = 0.0

        print(f"音声の長さ: {audio_duration:.2f} 秒")

        cursor.execute("DELETE FROM segments WHERE file_id = ?", (file_id,))
        try:
            cursor.execute("DELETE FROM summaries WHERE file_id = ?", (file_id,))
        except sqlite3.OperationalError:
            pass

        segment_count = 0
        utterances = list(transcript.utterances or [])

        if utterances:
            for idx, utt in enumerate(utterances):
                speaker = _format_speaker_label(getattr(utt, "speaker", None))
                text = (getattr(utt, "text", None) or "").strip()
                for original, corrected in correction_dict.items():
                    text = text.replace(original, corrected)
                start_ms = float(getattr(utt, "start", 0) or 0)
                end_ms = float(getattr(utt, "end", 0) or 0)
                start_time = start_ms / 1000.0
                end_time = end_ms / 1000.0
                cursor.execute(
                    """
                    INSERT INTO segments
                    (file_id, segment_index, speaker, text, start_time, end_time)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (file_id, idx, speaker, text, start_time, end_time),
                )
                segment_count += 1
        else:
            full_text = (transcript.text or "").strip()
            for original, corrected in correction_dict.items():
                full_text = full_text.replace(original, corrected)
            cursor.execute(
                """
                INSERT INTO segments
                (file_id, segment_index, speaker, text, start_time, end_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (file_id, 0, "Speaker A", full_text, 0.0, max(audio_duration, 0.0)),
            )
            segment_count = 1

        cursor.execute(
            """
            UPDATE files
            SET duration = ?, status = 'completed', updated_at = CURRENT_TIMESTAMP,
                error_message = NULL
            WHERE id = ?
        """,
            (audio_duration, file_id),
        )
        conn.commit()

        print(f"✅ {filename} の処理が完了しました（{segment_count}セグメント）")

        return {
            "success": True,
            "filename": filename,
            "file_id": file_id,
            "duration": audio_duration,
            "segment_count": segment_count,
        }

    except Exception as e:
        error_msg = str(e)
        print(f"❌ エラーが発生しました: {error_msg}")

        try:
            cursor.execute(
                """
                UPDATE files
                SET status = 'error', error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ? AND filename = ?
            """,
                (error_msg, project_id, filename),
            )
            conn.commit()
        except Exception:
            pass

        return {
            "success": False,
            "filename": filename,
            "error": error_msg,
        }

    finally:
        conn.close()
        gc.collect()


def main() -> None:
    """CLI バッチ処理"""
    print("=" * 60)
    print("音声ファイルのバッチ処理を開始します（AssemblyAI）")
    print("=" * 60)

    create_database_schema(DB_PATH)

    audio_files = get_audio_files(BASE_DIR)
    if not audio_files:
        print("⚠️  処理対象のファイルが見つかりませんでした")
        return

    print(f"\n処理対象ファイル数: {len(audio_files)}")
    for i, f in enumerate(audio_files, 1):
        print(f"  {i}. {os.path.basename(f)}")

    results = []
    for i, audio_file in enumerate(audio_files, 1):
        print(f"\n[{i}/{len(audio_files)}] 処理中...")
        results.append(process_audio_file(audio_file, DB_PATH))

    print("\n" + "=" * 60)
    print("処理結果サマリー")
    print("=" * 60)

    success_count = sum(1 for r in results if r.get("success", False))
    error_count = len(results) - success_count

    print(f"成功: {success_count}件")
    print(f"失敗: {error_count}件")

    if error_count > 0:
        print("\n失敗したファイル:")
        for r in results:
            if not r.get("success", False):
                print(f"  - {r.get('filename')}: {r.get('error', 'Unknown error')}")

    print(f"\n✅ データベース: {DB_PATH}")


if __name__ == "__main__":
    main()

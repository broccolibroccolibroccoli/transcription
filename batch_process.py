"""
輪読会ファイルのバッチ処理スクリプト
複数の音声ファイルを処理してデータベースに保存します。
"""
import torchaudio_compat  # noqa: F401 — torch.load(OmegaConf) / torchaudio / whisperx より先
import torch
import whisperx
import whisperx.asr as _wx_asr


def _patch_whisperx_load_model_hotwords() -> None:
    """faster-whisper 1.1+ の TranscriptionOptions は hotwords 必須。
    whisperx は asr_options でマージするが、load_model の参照が asr 直とズレると未マージのまま呼ばれる。
    whisperx.load_model と whisperx.asr.load_model の両方をラップする。
    参考: https://github.com/m-bain/whisperX/issues/918
    """

    def _wrap(orig):
        def _inner(*args, **kwargs):
            opts = kwargs.get("asr_options")
            merged = dict(opts) if opts else {}
            merged.setdefault("hotwords", None)
            kwargs["asr_options"] = merged
            return orig(*args, **kwargs)

        return _inner

    _orig_top = whisperx.load_model
    _orig_asr = _wx_asr.load_model
    wrapped = _wrap(_orig_asr)
    _wx_asr.load_model = wrapped
    if _orig_top is _orig_asr:
        whisperx.load_model = wrapped
    else:
        whisperx.load_model = _wrap(_orig_top)


_patch_whisperx_load_model_hotwords()
import json
import re
import gc
import numpy as np
import sqlite3
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from database_schema import create_database_schema

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# --- 設定 ---
BASE_DIR = os.environ.get("TRANSCRIPTION_BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "transcription.db")
device = "cpu"
# メモリが厳しいときは WHISPERX_BATCH_SIZE=1、WHISPERX_COMPUTE_TYPE=int8（CPU）を試す
try:
    batch_size = max(1, int(os.environ.get("WHISPERX_BATCH_SIZE", "4")))
except ValueError:
    batch_size = 4
compute_type = os.environ.get("WHISPERX_COMPUTE_TYPE", "float32")

# 辞書登録
correction_dict = {
    "カルテ": "KARTE",
    "ジャーニー": "Journey",
    "シグナルズ": "Signals",
    "グーグル": "Google",
    "ルッカー": "Looker"
}

# Hugging Faceトークン（話者分離用。環境変数 HF_TOKEN または .env で設定）
HF_TOKEN = os.environ.get("HF_TOKEN", "")

# ASR モデル名（WhisperX）。Streamlit Cloud 等で OOM する場合は base / small を指定
WHISPER_MODEL = os.environ.get("WHISPERX_ASR_MODEL", "large-v3")

# 話者分離（pyannote / Lightning）はメモリを多く使う。Community Cloud 等で OOM→「Oh no」になる場合は true
def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


SKIP_DIARIZATION = _env_truthy("TRANSCRIPTION_SKIP_DIARIZATION")
DEFAULT_SPEAKER_WHEN_SKIPPED = os.environ.get("TRANSCRIPTION_DEFAULT_SPEAKER", "SPEAKER_00")

# pyannote パイプライン名（WhisperX / pyannote の対応表に合わせる）。未設定は WhisperX 既定に任せる
WHISPERX_DIARIZE_MODEL = os.environ.get("WHISPERX_DIARIZE_MODEL", "").strip()

# アライメント用 wav2vec2（HF モデル ID）。未設定は WhisperX 既定（日本語は jonatasgrosman/...）
WHISPERX_ALIGN_MODEL = os.environ.get("WHISPERX_ALIGN_MODEL", "").strip()
# true のときステップ2アライメントを省略（Whisper セグメントの時刻のまま。torch/モデル不整合時の回避用）
SKIP_ALIGN = _env_truthy("TRANSCRIPTION_SKIP_ALIGN")


def _free_align_model(model_align, metadata) -> None:
    """話者分離の前にアライメント用モデルを解放し、ピークメモリを下げる。"""
    del model_align
    del metadata
    gc.collect()
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _build_diarization_pipeline():
    """WhisperX の DiarizationPipeline の引数名差（token / use_auth_token）に耐える。"""
    kwargs = {"device": device}
    if HF_TOKEN:
        kwargs["token"] = HF_TOKEN
    if WHISPERX_DIARIZE_MODEL:
        kwargs["model_name"] = WHISPERX_DIARIZE_MODEL
    from whisperx.diarize import DiarizationPipeline

    try:
        return DiarizationPipeline(**kwargs)
    except TypeError:
        kwargs.pop("token", None)
        if HF_TOKEN:
            kwargs["use_auth_token"] = HF_TOKEN
        return DiarizationPipeline(**kwargs)


def get_audio_files(base_dir: str) -> List[str]:
    """
    輪読会ファイルのリストを取得します。
    
    Args:
        base_dir: 検索するディレクトリ
        
    Returns:
        音声ファイルのパスのリスト
    """
    audio_extensions = ['.mp4', '.wav', '.mp3', '.m4a', '.flac']
    files = []
    
    for ext in audio_extensions:
        pattern = f"輪読会*{ext}"
        found_files = list(Path(base_dir).glob(pattern))
        files.extend([str(f) for f in found_files])
    
    # ファイル名でソート
    files.sort()
    return files


def process_audio_file(audio_file: str, db_path: str, project_id: int = 1) -> Dict[str, any]:
    """
    単一の音声ファイルを処理してデータベースに保存します。
    
    Args:
        audio_file: 音声ファイルのパス
        db_path: データベースファイルのパス
        project_id: プロジェクトID（デフォルト: 1=未分類）
        
    Returns:
        処理結果の辞書
    """
    filename = os.path.basename(audio_file)
    file_size = os.path.getsize(audio_file)
    
    print(f"\n{'='*60}")
    print(f"処理開始: {filename} (project_id={project_id})")
    print(f"{'='*60}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # ファイル情報をデータベースに登録（または更新）
        cursor.execute("""
            INSERT OR REPLACE INTO files 
            (filename, filepath, file_size, status, updated_at, project_id)
            VALUES (?, ?, ?, 'processing', CURRENT_TIMESTAMP, ?)
        """, (filename, audio_file, file_size, project_id))
        
        file_id = cursor.lastrowid
        if file_id is None:
            # 既存のファイルの場合、IDを取得
            cursor.execute("SELECT id FROM files WHERE project_id = ? AND filename = ?", (project_id, filename))
            result = cursor.fetchone()
            if result:
                file_id = result[0]
            else:
                raise Exception("ファイルIDの取得に失敗しました")
        
        conn.commit()
        
        # --- 1. WhisperXによる文字起こし ---
        print("--- ステップ1: WhisperXで文字起こし開始 ---")
        model = whisperx.load_model(WHISPER_MODEL, device, compute_type=compute_type)
        audio = whisperx.load_audio(audio_file)
        result = model.transcribe(audio, batch_size=batch_size, language="ja")
        
        # メモリ解放
        del model
        gc.collect()
        
        # --- 2. タイムスタンプの補正 (Alignment) ---
        if SKIP_ALIGN:
            print(
                "--- ステップ2: アライメントをスキップ（TRANSCRIPTION_SKIP_ALIGN） ---"
            )
        else:
            print("--- ステップ2: タイムスタンプを補正 ---")
            _align_kw: dict = {"language_code": "ja", "device": device}
            if WHISPERX_ALIGN_MODEL:
                _align_kw["model_name"] = WHISPERX_ALIGN_MODEL
            model_a, metadata = whisperx.load_align_model(**_align_kw)
            result = whisperx.align(
                result["segments"],
                model_a,
                metadata,
                audio,
                device,
                return_char_alignments=False,
            )
            _free_align_model(model_a, metadata)

        # --- 3. 話者分離 (Diarization) ---
        audio_duration = len(audio) / 16000
        print(f"音声の長さ: {audio_duration:.2f} 秒")

        if SKIP_DIARIZATION:
            print(
                "--- ステップ3: 話者分離をスキップ（TRANSCRIPTION_SKIP_DIARIZATION） ---"
            )
            for seg in result["segments"]:
                seg["speaker"] = DEFAULT_SPEAKER_WHEN_SKIPPED
        else:
            print("--- ステップ3: 話者分離を実行 ---")
            diarize_model = _build_diarization_pipeline()

            diarize_segments = diarize_model(audio, min_speakers=2, max_speakers=2)

            if len(diarize_segments) > 0:
                last_idx = diarize_segments.index[-1]
                diarize_segments.at[last_idx, "end"] = audio_duration
                print(f"diarizationの終了時間を {audio_duration:.2f} 秒に延長しました")

            result = whisperx.assign_word_speakers(
                diarize_segments,
                result,
                fill_nearest=True,
            )
            del diarize_model
            gc.collect()

        # --- 4. データベースへの保存 ---
        print("--- ステップ4: データベースに保存 ---")
        
        # 既存のセグメント・要約を削除
        cursor.execute("DELETE FROM segments WHERE file_id = ?", (file_id,))
        try:
            cursor.execute("DELETE FROM summaries WHERE file_id = ?", (file_id,))
        except sqlite3.OperationalError:
            pass  # summariesテーブルが存在しない場合はスキップ
        
        # セグメントをデータベースに保存
        last_speaker = None
        segment_count = 0
        
        for idx, segment in enumerate(result["segments"]):
            speaker = segment.get("speaker", None)
            
            # 話者が取れない場合は直前の話者を継承
            if speaker is None:
                speaker = last_speaker if last_speaker else "UNKNOWN"
            else:
                last_speaker = speaker
            
            text = segment["text"].strip()
            
            # 辞書置換
            for original, corrected in correction_dict.items():
                text = text.replace(original, corrected)
            
            start_time = segment.get("start", 0.0)
            end_time = segment.get("end", 0.0)
            
            # データベースに挿入
            cursor.execute("""
                INSERT INTO segments 
                (file_id, segment_index, speaker, text, start_time, end_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (file_id, idx, speaker, text, start_time, end_time))
            
            segment_count += 1
        
        # ファイル情報を更新
        cursor.execute("""
            UPDATE files 
            SET duration = ?, status = 'completed', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (audio_duration, file_id))
        
        conn.commit()
        
        print(f"✅ {filename} の処理が完了しました（{segment_count}セグメント）")
        
        return {
            "success": True,
            "filename": filename,
            "file_id": file_id,
            "duration": audio_duration,
            "segment_count": segment_count
        }
        
    except Exception as e:
        # エラーを記録
        error_msg = str(e)
        print(f"❌ エラーが発生しました: {error_msg}")
        
        cursor.execute("""
            UPDATE files 
            SET status = 'error', error_message = ?, updated_at = CURRENT_TIMESTAMP
            WHERE project_id = ? AND filename = ?
        """, (error_msg, project_id, filename))
        
        conn.commit()
        
        return {
            "success": False,
            "filename": filename,
            "error": error_msg
        }
        
    finally:
        conn.close()
        # メモリ解放
        gc.collect()


def main():
    """メイン処理"""
    print("="*60)
    print("輪読会ファイルのバッチ処理を開始します")
    print("="*60)
    
    # データベーススキーマの作成
    create_database_schema(DB_PATH)
    
    # 音声ファイルのリストを取得
    audio_files = get_audio_files(BASE_DIR)
    
    if not audio_files:
        print("⚠️  処理対象のファイルが見つかりませんでした")
        return
    
    print(f"\n処理対象ファイル数: {len(audio_files)}")
    for i, f in enumerate(audio_files, 1):
        print(f"  {i}. {os.path.basename(f)}")
    
    # 各ファイルを処理
    results = []
    for i, audio_file in enumerate(audio_files, 1):
        print(f"\n[{i}/{len(audio_files)}] 処理中...")
        result = process_audio_file(audio_file, DB_PATH)
        results.append(result)
    
    # 結果のサマリー
    print("\n" + "="*60)
    print("処理結果サマリー")
    print("="*60)
    
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

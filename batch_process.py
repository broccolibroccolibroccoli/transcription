"""
輪読会ファイルのバッチ処理スクリプト
複数の音声ファイルを処理してデータベースに保存します。
"""
import torchaudio_compat  # noqa: F401 — whisperx より先（pyannote が torchaudio を参照するため）
import whisperx
import whisperx.asr as _wx_asr
import whisperx.diarize


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
import torch
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
batch_size = 4
compute_type = "float32"

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
        print("--- ステップ2: タイムスタンプを補正 ---")
        model_a, metadata = whisperx.load_align_model(language_code="ja", device=device)
        result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
        
        # --- 3. 話者分離 (Diarization) ---
        print("--- ステップ3: 話者分離を実行 ---")
        
        # 音声の実際の長さを取得（サンプリングレート16kHz）
        audio_duration = len(audio) / 16000
        print(f"音声の長さ: {audio_duration:.2f} 秒")
        
        diarize_model = whisperx.diarize.DiarizationPipeline(
            token=HF_TOKEN,
            device=device
        )
        
        diarize_segments = diarize_model(audio, min_speakers=2, max_speakers=2)
        
        # diarize_segmentsの末尾を音声終端まで延ばす
        if len(diarize_segments) > 0:
            last_idx = diarize_segments.index[-1]
            diarize_segments.at[last_idx, "end"] = audio_duration
            print(f"diarizationの終了時間を {audio_duration:.2f} 秒に延長しました")
        
        # fill_nearest=True で話者未割当セグメントを近傍から補完
        result = whisperx.assign_word_speakers(
            diarize_segments,
            result,
            fill_nearest=True
        )
        
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

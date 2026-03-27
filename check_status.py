"""
バッチ処理の進行状況を確認するスクリプト
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = "/Users/kayoko.namba/Desktop/transcription/transcription.db"
LOG_FILE = "/Users/kayoko.namba/Desktop/transcription/batch_process.log"

def check_status():
    """処理状況を確認"""
    print("="*60)
    print("バッチ処理の進行状況")
    print("="*60)
    
    # データベースの確認
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # ファイル一覧
        cursor.execute("""
            SELECT filename, status, duration, processed_at, error_message
            FROM files
            ORDER BY processed_at DESC
        """)
        
        files = cursor.fetchall()
        
        print(f"\n登録ファイル数: {len(files)}件\n")
        
        completed = 0
        processing = 0
        error = 0
        
        for filename, status, duration, processed_at, error_msg in files:
            status_icon = "✅" if status == "completed" else "⏳" if status == "processing" else "❌"
            duration_str = f"{duration:.1f}秒" if duration else "処理中..."
            
            print(f"{status_icon} {filename}")
            print(f"   状態: {status}")
            print(f"   長さ: {duration_str}")
            if processed_at:
                print(f"   処理日時: {processed_at}")
            if error_msg:
                print(f"   エラー: {error_msg}")
            print()
            
            if status == "completed":
                completed += 1
            elif status == "processing":
                processing += 1
            elif status == "error":
                error += 1
        
        # セグメント数
        cursor.execute("SELECT COUNT(*) FROM segments")
        segment_count = cursor.fetchone()[0]
        
        print(f"\n統計:")
        print(f"  完了: {completed}件")
        print(f"  処理中: {processing}件")
        print(f"  エラー: {error}件")
        print(f"  セグメント総数: {segment_count}件")
        
        conn.close()
    else:
        print("❌ データベースファイルが見つかりません")
    
    # ログファイルの確認
    if os.path.exists(LOG_FILE):
        print(f"\n最新のログ（最後の10行）:")
        print("-"*60)
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            for line in lines[-10:]:
                print(line.rstrip())
    else:
        print("\n⚠️  ログファイルが見つかりません")

if __name__ == "__main__":
    check_status()

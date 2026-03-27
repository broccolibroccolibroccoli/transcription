"""
データベース検索・確認用ユーティリティ
"""
import sqlite3
import sys
from pathlib import Path


DB_PATH = "/Users/kayoko.namba/Desktop/transcription/transcription.db"


def list_files():
    """登録されているファイル一覧を表示"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, filename, filepath, duration, status, processed_at, error_message
        FROM files
        ORDER BY processed_at DESC
    """)
    
    files = cursor.fetchall()
    
    if not files:
        print("登録されているファイルがありません")
        return
    
    print(f"\n登録ファイル数: {len(files)}件\n")
    print(f"{'ID':<5} {'ファイル名':<30} {'状態':<12} {'長さ(秒)':<12} {'処理日時':<20}")
    print("-" * 100)
    
    for file_id, filename, filepath, duration, status, processed_at, error_msg in files:
        duration_str = f"{duration:.1f}" if duration else "N/A"
        status_str = status or "unknown"
        processed_str = processed_at[:19] if processed_at else "N/A"
        
        print(f"{file_id:<5} {filename:<30} {status_str:<12} {duration_str:<12} {processed_str:<20}")
        
        if error_msg:
            print(f"     エラー: {error_msg}")
    
    conn.close()


def show_segments(filename: str = None, file_id: int = None, speaker: str = None, limit: int = 50):
    """
    セグメント情報を表示
    
    Args:
        filename: ファイル名でフィルタ
        file_id: ファイルIDでフィルタ
        speaker: 話者でフィルタ
        limit: 表示件数の上限
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = """
        SELECT s.id, f.filename, s.segment_index, s.speaker, s.text, s.start_time, s.end_time
        FROM segments s
        JOIN files f ON s.file_id = f.id
        WHERE 1=1
    """
    params = []
    
    if filename:
        query += " AND f.filename LIKE ?"
        params.append(f"%{filename}%")
    
    if file_id:
        query += " AND s.file_id = ?"
        params.append(file_id)
    
    if speaker:
        query += " AND s.speaker = ?"
        params.append(speaker)
    
    query += " ORDER BY f.filename, s.segment_index LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    segments = cursor.fetchall()
    
    if not segments:
        print("該当するセグメントが見つかりませんでした")
        return
    
    print(f"\nセグメント数: {len(segments)}件\n")
    
    current_filename = None
    for seg_id, filename, seg_idx, speaker, text, start_time, end_time in segments:
        if filename != current_filename:
            print(f"\n【ファイル: {filename}】")
            current_filename = filename
        
        speaker_str = speaker or "UNKNOWN"
        time_str = f"{start_time:.1f}-{end_time:.1f}秒"
        text_preview = text[:50] + "..." if len(text) > 50 else text
        
        print(f"  [{speaker_str}] ({time_str}) {text_preview}")
    
    conn.close()


def export_to_text(filename: str = None, file_id: int = None, output_file: str = None):
    """
    データベースからテキストファイルをエクスポート
    
    Args:
        filename: ファイル名でフィルタ
        file_id: ファイルIDでフィルタ
        output_file: 出力ファイル名（指定しない場合は自動生成）
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = """
        SELECT f.filename, s.speaker, s.text
        FROM segments s
        JOIN files f ON s.file_id = f.id
        WHERE 1=1
    """
    params = []
    
    if filename:
        query += " AND f.filename LIKE ?"
        params.append(f"%{filename}%")
    
    if file_id:
        query += " AND s.file_id = ?"
        params.append(file_id)
    
    query += " ORDER BY f.filename, s.segment_index"
    
    cursor.execute(query, params)
    segments = cursor.fetchall()
    
    if not segments:
        print("該当するセグメントが見つかりませんでした")
        return
    
    if not output_file:
        if filename:
            base_name = Path(filename).stem
            output_file = f"{base_name}_export.txt"
        elif file_id:
            output_file = f"file_{file_id}_export.txt"
        else:
            output_file = "all_transcriptions_export.txt"
    
    with open(output_file, 'w', encoding='UTF-8') as f:
        current_filename = None
        for db_filename, speaker, text in segments:
            if db_filename != current_filename:
                if current_filename is not None:
                    f.write("\n")
                f.write(f"=== {db_filename} ===\n\n")
                current_filename = db_filename
            
            speaker_str = speaker or "UNKNOWN"
            f.write(f"[{speaker_str}] {text}\n")
    
    print(f"✅ エクスポート完了: {output_file} ({len(segments)}セグメント)")


def get_statistics():
    """データベースの統計情報を表示"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # ファイル統計
    cursor.execute("SELECT COUNT(*) FROM files")
    file_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM files WHERE status = 'completed'")
    completed_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM files WHERE status = 'error'")
    error_count = cursor.fetchone()[0]
    
    # セグメント統計
    cursor.execute("SELECT COUNT(*) FROM segments")
    segment_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT speaker) FROM segments WHERE speaker IS NOT NULL")
    speaker_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(duration) FROM files WHERE duration IS NOT NULL")
    total_duration = cursor.fetchone()[0] or 0
    
    print("\n" + "="*60)
    print("データベース統計情報")
    print("="*60)
    print(f"登録ファイル数: {file_count}件")
    print(f"  完了: {completed_count}件")
    print(f"  エラー: {error_count}件")
    print(f"セグメント総数: {segment_count}件")
    print(f"話者数: {speaker_count}人")
    print(f"総音声時間: {total_duration:.1f}秒 ({total_duration/60:.1f}分)")
    
    # 話者別統計
    cursor.execute("""
        SELECT speaker, COUNT(*) as count
        FROM segments
        WHERE speaker IS NOT NULL
        GROUP BY speaker
        ORDER BY count DESC
    """)
    
    speaker_stats = cursor.fetchall()
    if speaker_stats:
        print("\n話者別セグメント数:")
        for speaker, count in speaker_stats:
            print(f"  {speaker}: {count}件")
    
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python db_query.py list                    # ファイル一覧")
        print("  python db_query.py stats                    # 統計情報")
        print("  python db_query.py segments [filename]      # セグメント表示")
        print("  python db_query.py export [filename]        # テキストエクスポート")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "list":
        list_files()
    elif command == "stats":
        get_statistics()
    elif command == "segments":
        filename = sys.argv[2] if len(sys.argv) > 2 else None
        show_segments(filename=filename)
    elif command == "export":
        filename = sys.argv[2] if len(sys.argv) > 2 else None
        output_file = sys.argv[3] if len(sys.argv) > 3 else None
        export_to_text(filename=filename, output_file=output_file)
    else:
        print(f"不明なコマンド: {command}")

#!/usr/bin/env python3
"""
transcription.db を開くためのコマンドラインアプリケーション
tkinterが使えない環境でも動作します
"""
import sqlite3
import os
import sys
from pathlib import Path

DB_PATH = "/Users/kayoko.namba/Desktop/transcription/transcription.db"


def print_separator():
    print("=" * 60)


def show_tables(conn):
    """テーブル一覧を表示"""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    
    print_separator()
    print("テーブル一覧")
    print_separator()
    for i, (table_name,) in enumerate(tables, 1):
        # レコード数を取得
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"{i}. {table_name} ({count}件)")
    print()


def show_table_data(conn, table_name, limit=20):
    """テーブルのデータを表示"""
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
    
    # 列名を取得
    columns = [description[0] for description in cursor.description]
    
    print_separator()
    print(f"テーブル: {table_name}")
    print_separator()
    
    # ヘッダーを表示
    header = " | ".join([f"{col:<20}" for col in columns])
    print(header)
    print("-" * len(header))
    
    # データを表示
    rows = cursor.fetchall()
    for row in rows:
        values = [str(val)[:20] if val is not None else "NULL" for val in row]
        print(" | ".join([f"{val:<20}" for val in values]))
    
    if len(rows) == limit:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        total = cursor.fetchone()[0]
        print(f"\n... (表示: {limit}件 / 全{total}件)")
    print()


def show_statistics(conn):
    """統計情報を表示"""
    cursor = conn.cursor()
    
    print_separator()
    print("データベース統計情報")
    print_separator()
    
    # ファイル統計
    cursor.execute("SELECT COUNT(*) FROM files")
    file_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM files WHERE status = 'completed'")
    completed_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM files WHERE status = 'error'")
    error_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM files WHERE status = 'processing'")
    processing_count = cursor.fetchone()[0]
    
    # セグメント統計
    cursor.execute("SELECT COUNT(*) FROM segments")
    segment_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT speaker) FROM segments WHERE speaker IS NOT NULL")
    speaker_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(duration) FROM files WHERE duration IS NOT NULL")
    total_duration = cursor.fetchone()[0] or 0
    
    print(f"【ファイル情報】")
    print(f"  登録ファイル数: {file_count}件")
    print(f"  完了: {completed_count}件")
    print(f"  処理中: {processing_count}件")
    print(f"  エラー: {error_count}件")
    print()
    
    print(f"【セグメント情報】")
    print(f"  セグメント総数: {segment_count}件")
    print(f"  話者数: {speaker_count}人")
    print(f"  総音声時間: {total_duration:.1f}秒 ({total_duration/60:.1f}分)")
    print()
    
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
        print("【話者別セグメント数】")
        for speaker, count in speaker_stats:
            print(f"  {speaker}: {count}件")
        print()
    
    # ファイル一覧
    cursor.execute("""
        SELECT filename, status, duration, processed_at
        FROM files
        ORDER BY processed_at DESC
    """)
    
    files = cursor.fetchall()
    if files:
        print("【ファイル一覧】")
        for filename, status, duration, processed_at in files:
            duration_str = f"{duration:.1f}秒" if duration else "処理中"
            print(f"  {filename}")
            print(f"    状態: {status}")
            print(f"    長さ: {duration_str}")
            if processed_at:
                print(f"    処理日時: {processed_at}")
            print()


def interactive_mode(conn):
    """対話モード"""
    print_separator()
    print("transcription.db ビューアー（対話モード）")
    print_separator()
    print()
    
    while True:
        print("\n操作を選択してください:")
        print("  1. テーブル一覧を表示")
        print("  2. テーブルのデータを表示")
        print("  3. 統計情報を表示")
        print("  4. SQLクエリを実行")
        print("  5. 終了")
        print()
        
        try:
            choice = input("選択 (1-5): ").strip()
            
            if choice == "1":
                show_tables(conn)
            
            elif choice == "2":
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                tables = [row[0] for row in cursor.fetchall()]
                
                if not tables:
                    print("テーブルが見つかりません")
                    continue
                
                print("\nテーブルを選択してください:")
                for i, table in enumerate(tables, 1):
                    print(f"  {i}. {table}")
                
                try:
                    table_idx = int(input("番号: ")) - 1
                    if 0 <= table_idx < len(tables):
                        limit = input("表示件数 (デフォルト: 20): ").strip()
                        limit = int(limit) if limit else 20
                        show_table_data(conn, tables[table_idx], limit)
                    else:
                        print("無効な番号です")
                except ValueError:
                    print("無効な入力です")
            
            elif choice == "3":
                show_statistics(conn)
            
            elif choice == "4":
                sql = input("\nSQLクエリを入力: ").strip()
                if sql:
                    try:
                        cursor = conn.cursor()
                        cursor.execute(sql)
                        
                        if sql.strip().upper().startswith("SELECT"):
                            columns = [desc[0] for desc in cursor.description]
                            rows = cursor.fetchall()
                            
                            print_separator()
                            print("結果")
                            print_separator()
                            
                            # ヘッダー
                            header = " | ".join([f"{col:<20}" for col in columns])
                            print(header)
                            print("-" * len(header))
                            
                            # データ
                            for row in rows:
                                values = [str(val)[:20] if val is not None else "NULL" for val in row]
                                print(" | ".join([f"{val:<20}" for val in values]))
                            
                            print(f"\n{len(rows)}件の結果")
                        else:
                            conn.commit()
                            print(f"✅ クエリが実行されました（影響を受けた行数: {cursor.rowcount}）")
                    except Exception as e:
                        print(f"❌ エラー: {str(e)}")
            
            elif choice == "5":
                print("終了します")
                break
            
            else:
                print("無効な選択です")
        
        except KeyboardInterrupt:
            print("\n\n終了します")
            break
        except EOFError:
            print("\n\n終了します")
            break


def main():
    """メイン処理"""
    if not os.path.exists(DB_PATH):
        print(f"❌ エラー: データベースファイルが見つかりません: {DB_PATH}")
        sys.exit(1)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # コマンドライン引数がある場合
        if len(sys.argv) > 1:
            command = sys.argv[1].lower()
            
            if command == "tables" or command == "list":
                show_tables(conn)
            
            elif command == "stats" or command == "statistics":
                show_statistics(conn)
            
            elif command == "show" and len(sys.argv) > 2:
                table_name = sys.argv[2]
                limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20
                show_table_data(conn, table_name, limit)
            
            else:
                print("使用方法:")
                print("  python3 open_db_cli.py                    # 対話モード")
                print("  python3 open_db_cli.py tables            # テーブル一覧")
                print("  python3 open_db_cli.py stats              # 統計情報")
                print("  python3 open_db_cli.py show <table_name> # テーブルデータ")
        else:
            # 対話モード
            interactive_mode(conn)
        
        conn.close()
    
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()

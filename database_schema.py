"""
データベーススキーマ定義
SQLiteデータベースのテーブル構造を定義します。
"""
import sqlite3
from datetime import datetime
from pathlib import Path


def migrate_to_projects(db_path: str) -> None:
    """
    既存DBにプロジェクト機能を追加するマイグレーション
    """
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    try:
        # projectsテーブルが既に存在するか確認
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
        )
        if cursor.fetchone():
            conn.close()
            return

        # 1. projectsテーブルを作成
        cursor.execute("""
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("INSERT INTO projects (id, name) VALUES (1, '未分類')")

        # 2. filesテーブルの存在確認（新規DBの場合はスキップ）
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files'")
        if not cursor.fetchone():
            conn.commit()
            conn.close()
            return

        # 3. filesテーブルにproject_idカラムを追加
        cursor.execute("PRAGMA table_info(files)")
        cols = [r[1] for r in cursor.fetchall()]
        if "project_id" not in cols:
            cursor.execute("ALTER TABLE files ADD COLUMN project_id INTEGER DEFAULT 1")
            cursor.execute("UPDATE files SET project_id = 1 WHERE project_id IS NULL")

        # 4. ユニーク制約を(project_id, filename)に変更（テーブル再作成）
        cursor.execute("PRAGMA table_info(files)")
        if "project_id" in [r[1] for r in cursor.fetchall()]:
            cursor.execute(
                "SELECT id, filename, filepath, file_size, duration, processed_at, "
                "status, error_message, created_at, updated_at, project_id FROM files"
            )
            rows = cursor.fetchall()
            cursor.execute("CREATE TABLE files_new ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "filename TEXT NOT NULL, "
                "filepath TEXT NOT NULL, "
                "file_size INTEGER, "
                "duration REAL, "
                "processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
                "status TEXT DEFAULT 'pending', "
                "error_message TEXT, "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
                "project_id INTEGER NOT NULL DEFAULT 1 REFERENCES projects(id), "
                "UNIQUE(project_id, filename)"
            ")")
            for r in rows:
                cursor.execute(
                    "INSERT INTO files_new (id, filename, filepath, file_size, "
                    "duration, processed_at, status, error_message, created_at, "
                    "updated_at, project_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    r,
                )
            cursor.execute("DROP TABLE files")
            cursor.execute("ALTER TABLE files_new RENAME TO files")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_project_id ON files(project_id)")
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_project_summaries_cursor(cursor: sqlite3.Cursor) -> None:
    """同一接続上で project_summaries テーブルを追加（別接続を開かない＝ロック回避）。"""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='project_summaries'"
    )
    if cursor.fetchone():
        return
    cursor.execute("""
        CREATE TABLE project_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            model_used TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_summaries_project_id "
        "ON project_summaries(project_id)"
    )


def migrate_project_summaries(db_path: str) -> None:
    """単体実行・テスト用: 専用接続で project_summaries を作成。"""
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        migrate_project_summaries_cursor(conn.cursor())
        conn.commit()
    finally:
        conn.close()


def create_database_schema(db_path: str = "transcription.db"):
    """
    データベーススキーマを作成します。
    
    Args:
        db_path: データベースファイルのパス
    """
    # プロジェクトテーブル（既存DBのマイグレーション）— 自前で接続を閉じる
    migrate_to_projects(db_path)

    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()

    # projectsテーブル（新規作成時用）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(
        "INSERT OR IGNORE INTO projects (id, name) VALUES (1, '未分類')"
    )

    # ファイル情報テーブル（projectsが存在する場合のみproject_id付きで作成）
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                file_size INTEGER,
                duration REAL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                project_id INTEGER NOT NULL DEFAULT 1 REFERENCES projects(id),
                UNIQUE(project_id, filename)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_project_id ON files(project_id)")
    
    # セグメント情報テーブル（文字起こし結果）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            segment_index INTEGER NOT NULL,
            speaker TEXT,
            text TEXT NOT NULL,
            start_time REAL NOT NULL,
            end_time REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
            UNIQUE(file_id, segment_index)
        )
    """)
    
    # 要約テーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            summary_type TEXT DEFAULT 'full',
            content TEXT NOT NULL,
            model_used TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        )
    """)
    
    # インデックスの作成
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_segments_file_id ON segments(file_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_segments_speaker ON segments(speaker)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_segments_start_time ON segments(start_time)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_filename ON files(filename)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_file_id ON summaries(file_id)")

    # プロジェクト単位の要約（同一 conn 上で実行し database is locked を防ぐ）
    migrate_project_summaries_cursor(cursor)

    conn.commit()
    conn.close()
    print(f"✅ データベーススキーマを作成しました: {db_path}")


if __name__ == "__main__":
    create_database_schema()

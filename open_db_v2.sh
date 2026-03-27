#!/bin/bash
# transcription.db を開くためのスクリプト（改良版）

SCRIPT_DIR="/Users/kayoko.namba/Desktop/transcription"
DB_PATH="${SCRIPT_DIR}/transcription.db"
VENV_PATH="/Users/kayoko.namba/venvs/whisperx"

cd "$SCRIPT_DIR" || exit 1

# データベースファイルの存在確認
if [ ! -f "$DB_PATH" ]; then
    echo "❌ エラー: データベースファイルが見つかりません: $DB_PATH"
    exit 1
fi

echo "📊 transcription.db を開いています..."

# 方法1: DB Browser for SQLiteがインストールされている場合
if command -v "DB Browser for SQLite" &> /dev/null || [ -d "/Applications/DB Browser for SQLite.app" ]; then
    echo "✅ DB Browser for SQLiteを使用します"
    open -a "DB Browser for SQLite" "$DB_PATH"
    exit 0
fi

# 方法2: 仮想環境のPythonでGUIアプリを起動
if [ -f "$VENV_PATH/bin/activate" ]; then
    echo "✅ 仮想環境のPythonを使用します"
    source "$VENV_PATH/bin/activate"
    python3 "${SCRIPT_DIR}/open_db.py" 2>/dev/null
    if [ $? -eq 0 ]; then
        exit 0
    fi
    echo "⚠️  GUIアプリの起動に失敗しました。コマンドライン版を使用します。"
fi

# 方法3: コマンドラインで開く
if command -v sqlite3 &> /dev/null; then
    echo "✅ コマンドライン版（sqlite3）を使用します"
    echo ""
    echo "便利なコマンド:"
    echo "  .tables              - テーブル一覧"
    echo "  .schema files        - filesテーブルの構造"
    echo "  SELECT * FROM files; - filesテーブルの全データ"
    echo "  .quit                - 終了"
    echo ""
    sqlite3 "$DB_PATH"
    exit 0
fi

# 方法4: Pythonで簡単なCLIビューアーを起動
echo "✅ Python CLIビューアーを使用します"
python3 "${SCRIPT_DIR}/open_db_cli.py"

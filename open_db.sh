#!/bin/bash
# transcription.db を開くためのスクリプト

SCRIPT_DIR="/Users/kayoko.namba/Desktop/transcription"
DB_PATH="${SCRIPT_DIR}/transcription.db"

cd "$SCRIPT_DIR" || exit 1

# データベースファイルの存在確認
if [ ! -f "$DB_PATH" ]; then
    echo "❌ エラー: データベースファイルが見つかりません: $DB_PATH"
    exit 1
fi

# Python GUIアプリケーションを起動
if command -v python3 &> /dev/null; then
    echo "🚀 transcription.db ビューアーを起動しています..."
    python3 "${SCRIPT_DIR}/open_db.py"
else
    echo "❌ エラー: python3 が見つかりません"
    echo ""
    echo "代替方法:"
    echo "1. DB Browser for SQLiteをインストール:"
    echo "   brew install --cask db-browser-for-sqlite"
    echo ""
    echo "2. コマンドラインで開く:"
    echo "   sqlite3 \"$DB_PATH\""
    exit 1
fi

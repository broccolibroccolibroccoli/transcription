#!/bin/bash
# 輪読会ファイルのバッチ処理実行スクリプト

# 仮想環境のパス
VENV_PATH="/Users/kayoko.namba/venvs/whisperx"

# プロジェクトディレクトリ
PROJECT_DIR="/Users/kayoko.namba/Desktop/transcription"

# 仮想環境のアクティベート
if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
    echo "✅ 仮想環境をアクティベートしました"
else
    echo "❌ エラー: 仮想環境が見つかりません: $VENV_PATH"
    exit 1
fi

# プロジェクトディレクトリに移動
cd "$PROJECT_DIR" || exit 1

# データベーススキーマの作成（初回のみ）
echo "📊 データベーススキーマを確認中..."
python database_schema.py

# バッチ処理の実行
echo ""
echo "🚀 バッチ処理を開始します..."
python batch_process.py

# 処理結果の確認
echo ""
echo "📈 処理結果を確認中..."
python db_query.py stats

echo ""
echo "✅ 処理が完了しました"

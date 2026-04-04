# データベース拡張スキーマ

## 追加テーブル: summaries

要約結果を保存するためのテーブル。

| カラム名 | 型 | 説明 |
|---------|-----|------|
| id | INTEGER | 主キー |
| file_id | INTEGER | ファイルID（外部キー → files.id） |
| summary_type | TEXT | 要約タイプ（'overview', 'points', 'qa' など） |
| content | TEXT | 要約本文 |
| model_used | TEXT | 使用したLLM（例: gpt-4o-mini） |
| created_at | TIMESTAMP | 作成日時 |

### 作成SQL

```sql
CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    summary_type TEXT DEFAULT 'full',
    content TEXT NOT NULL,
    model_used TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_summaries_file_id ON summaries(file_id);
```

## 既存テーブルの変更

`files` テーブルは現状のままで問題なし。  
ファイルパターン（`輪読会*`）の制限を外す場合は、`batch_process.py` の `get_audio_files()` を拡張し、`uploads/` 配下も対象にする。

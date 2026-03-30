# Streamlit Cloud デプロイ（AssemblyAI）

## Secrets（必須）

アプリ設定 → Secrets に以下を追加する。

```toml
ASSEMBLYAI_API_KEY = "あなたのAPIキー"
```

キーは [AssemblyAI Dashboard](https://www.assemblyai.com/dashboard) から取得する。

## 依存関係

- リポジトリ直下の `requirements.txt` を使用（`assemblyai`, `streamlit`, `yt-dlp`, `mutagen` など）。
- Python バージョンは `runtime.txt`（例: 3.11）に合わせる。

## 以前の WhisperX / torch 向けトラブルシュート

本リポジトリは **AssemblyAI API** に切り替えたため、WhisperX・PyTorch・HF_TOKEN 関連の記述は過去版のものです。新規デプロイでは `requirements.txt` と Secrets の **ASSEMBLYAI_API_KEY** のみを確認すればよいです。

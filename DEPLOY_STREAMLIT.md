# Streamlit Community Cloud でのデプロイ（トラブルシュート）

## 「Error installing requirements」が出るとき

1. **Manage app → Logs（または Build）** を開き、**pip のエラー全文**を確認する。  
   - バージョン衝突、`No matching distribution`、メモリ・ディスク不足などが分かります。

2. **Python バージョン**  
   アプリ設定の **Advanced settings** で **Python 3.10 または 3.11** を試す（3.12 は一部パッケージで未対応のことがあります）。

3. **WhisperX + PyTorch は非常に大きい**  
   無料枠では **ビルドのメモリ・ディスク・時間制限**で `pip install` 自体が失敗することがあります。  
   その場合は次のいずれかが必要になることが多いです。  
   - Streamlit の **有料プラン**（リソース増）  
   - **自前 VPS / Docker / Railway / Render** など別ホストで `requirements.txt` をインストール

4. **それでも pip だけ失敗する場合（torch の取得を CPU 向けに限定）**  
   リポジトリ直下に `requirements-cpu.txt` のような別ファイルを用意し、中身の例:

```text
streamlit>=1.36.0
python-dotenv>=1.0.0
openai>=1.0.0
yt-dlp>=2024.1.0

--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.4.1+cpu
torchaudio==2.4.1+cpu

whisperx==3.2.0
```

   Streamlit Cloud の **Deploy → Advanced settings → Requirements file** で  
   `requirements-cpu.txt` を指定して再デプロイする。

## YouTube 利用時

`yt-dlp` の音声変換に **FFmpeg** が必要な場合があります。リポジトリ直下に `packages.txt` を置き、1 行だけ:

```text
ffmpeg
```

（`packages.txt` の記述ミスで apt が失敗すると、デプロイ全体が落ちることがあるので、問題が続くときだけ追加してください。）

## Secrets

話者分離には **Hugging Face のトークン**が必要です。Secrets に例:

```toml
HF_TOKEN = "hf_..."
```

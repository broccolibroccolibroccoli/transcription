# Streamlit Community Cloud でのデプロイ（トラブルシュート）

## `pkg-config is required for building PyAV` / `av==11.0.0` ビルド失敗

`faster-whisper`（WhisperX 経由）が **`av`（PyAV）** を必要とし、**`av==11.*` に cp312 用のホイールが無い**環境ではソースビルドになります。その際 **`pkg-config` と FFmpeg 関連の開発パッケージ**が無いと失敗します。

**対処**

1. リポジトリ直下の **`packages.txt`**（apt 用）がデプロイに含まれていることを確認する（本リポジトリに同梱）。  
2. 変更を push して再デプロイする。  
3. それでもビルドがタイムアウト・失敗する場合は、**無料枠のビルド時間・メモリ不足**の可能性があります。その場合は **メモリの大きいプラン**や **自前 Docker / VPS** を検討してください。

---

## `ctranslate2==4.4.0` / `No matching distribution` / `whisperx cannot be used`（Python 3.14）

ログに **`Using Python 3.14.x`** と出て、`ctranslate2==4.4.0` が解決できない／**`No wheels with a matching Python ABI`** となるのは、**WhisperX 3.2.0 が要求する ctranslate2 4.4.0 に Python 3.14 用のホイールが無い**ためです。

**対処（必須）**

1. Streamlit Cloud の **Manage app → Settings（または Deploy の Advanced settings）** を開く。  
2. **Python version** を **3.11** または **3.12** に変更して保存する。  
3. バージョン変更ができない／反映されない場合は、アプリを **削除して同じリポジトリから再デプロイ**し、**最初から 3.11 / 3.12 を選ぶ**（公式の挙動は [Upgrade Python](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/upgrade-python) を参照）。

リポジトリ直下の **`runtime.txt`**（`python-3.11.9`）は、環境によって参照されますが、**必ずしも Cloud で強制されない**ため、**画面上の Python 選択が確実**です。

---

## 「Oh no. Error running app」が出るとき（Reboot 直後など）

アプリの Python が**起動直後に例外で止まっている**ときに表示されます（原因はログに出ます）。

1. **Manage app → Logs（アプリのログ）** を開き、**赤い Traceback（最後の方）** を確認する。  
   - `ModuleNotFoundError` → `requirements.txt` のインストール失敗または不足。  
   - `PermissionError` / `Read-only file system` → 書き込み先パスの問題（通常はリポジトリ直下で解消）。  
   - `MemoryError` / `Killed` → メモリ不足（WhisperX 実行時に多い）。

2. **Python バージョン** を **3.10 または 3.11** に変更して再デプロイ（Advanced settings）。

3. リポジトリの **`app.py` は `st.set_page_config` を先に実行**し、DB 初期化失敗時は画面上に `st.exception` で表示するようになっているので、**最新版を push** してから再度 Reboot する。

4. ログに何も出ない・すぐ落ちる場合は、Streamlit の **フォーラム**や **ステータスページ**も確認。

---

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

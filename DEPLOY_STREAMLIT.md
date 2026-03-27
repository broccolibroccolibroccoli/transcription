# Streamlit Community Cloud でのデプロイ（トラブルシュート）

## `libctranslate2-...so: cannot enable executable stack` / `Invalid argument`

**glibc 2.41 以降**では、古い **ctranslate2** の共有ライブラリに付いた **executable stack** が読み込み拒否されることがあります（実行時、`batch_process` で `import whisperx` した直後に出る）。

**対処:** リポジトリの **`pyproject.toml`** で **`ctranslate2>=4.6.1,<5`** に **override** している（修正ビルド）。変更を push して再デプロイする。

参考: [OpenNMT/CTranslate2 #1849](https://github.com/OpenNMT/CTranslate2/issues/1849)

---

## `torchaudio.set_audio_backend` / `AttributeError`（pyannote.audio）

**pyannote.audio 3.1.1** が **`torchaudio.set_audio_backend("soundfile")`** を呼ぶが、**torchaudio 2.4 以降で当該 API が削除**されていると `AttributeError` になる。

**対処:** `pyproject.toml` の override で **`torch==2.3.1`** と **`torchaudio==2.3.1`** に固定（当該 API が残る組み合わせ）。変更を push して再デプロイする。

参考: [pyannote/pyannote-audio#1576](https://github.com/pyannote/pyannote-audio/issues/1576)

---

## `np.NaN` / `AttributeError`（pyannote.audio × NumPy 2）

**NumPy 2.0** 以降で **`np.NaN`** が削除され、**pyannote.audio** の `Inference` などが **`missing: float = np.NaN`** のようにクラス定義で参照していると、**import 時に `AttributeError`** になる。

**対処:** **`numpy>=1.26,<2`** を **`requirements.txt`** に明示し、**`pyproject.toml` の override-dependencies** にも **`numpy>=1.26,<2`** を入れてある。push して再デプロイする。

---

## `AV_OPT_TYPE_CHANNEL_LAYOUT` / `av` のビルド失敗（gcc）

`av==11` をソースビルドすると、**OS の FFmpeg ライブラリのバージョン**と PyAV 11 の C コードが合わず（例: `AV_OPT_TYPE_CHANNEL_LAYOUT` 未定義）、**gcc で失敗**することがあります。

**対処（本リポジトリの方針）**

- **`pyproject.toml` の `[tool.uv] override-dependencies`** で **`faster-whisper==1.0.3`** と **`av==12.3.0`** に上書きし、**cp312 用の事前ビルドホイール**だけを使う（ソースビルドしない）。  
- Streamlit Cloud は **`uv pip install`** を先に実行するため、この設定が効く想定です。  
- **`packages.txt`** は **`ffmpeg` のみ**（yt-dlp 向け）。以前の `libav*-dev` 大量インストールは、逆に **新しすぎるヘッダで PyAV 11 のビルドを壊す**ことがあったため削減しています。

`uv` が override を読まない経路だけ `pip` が動く場合は、同じ衝突が再発する可能性があります。そのときはログを確認し、**Streamlit / uv のバージョン**や **別ホスト**を検討してください。

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

`yt-dlp` の音声変換に **FFmpeg** が必要な場合があります。リポジトリ直下の **`packages.txt`** に **`ffmpeg`** を 1 行で書きます。

**注意:** `packages.txt` は **コメント不可**（`#` や日本語の行はパッケージ名として解釈され、`Unable to locate package` で失敗します）。**パッケージ名のみ、1 行に 1 つ**だけ書いてください。

## Secrets

話者分離には **Hugging Face のトークン**が必要です。Secrets に例:

```toml
HF_TOKEN = "hf_..."
```

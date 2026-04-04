# Streamlit Cloud で「Oh no. Error running app.」が出る場合（logs.md 調査メモ）

## 1. logs.md に含まれていた内容

- **apt / uv による依存関係のインストールは成功**している（`torch==2.4.1`、`whisperx==3.2.0` など）。
- **末尾に出ているのは `pyannote.audio` / `speechbrain` の `UserWarning` のみ**である。
- **`Traceback` や `Error running app` に直結する Python 例外メッセージは、提供された logs.md には含まれていない。**

## 2. UserWarning は「原因」とは限らない

ログ例:

- `torchaudio._backend.set_audio_backend has been deprecated`
- `speechbrain.pretrained was deprecated`
- `AudioMetaData has been moved`

これらは **非推奨 API の警告**であり、**通常は処理を止めない**。  
**UI の「Oh no」との因果関係は logs.md だけでは断定できない**（警告の直後に別の致命的エラーが出ていても、**その行がログに貼られていない**可能性がある）。

## 3. 「Oh no」が出る代表的な理由（Streamlit Community Cloud）

Streamlit はクラウド上で **例外メッセージをマスク**することがあり、ブラウザには汎用文しか出ない。**真因はホスト側ログ**に書かれる。

| 要因 | 説明 |
|------|------|
| **メモリ不足（OOM）** | `whisperx.load_model("large-v3", ...)` は **CPU でも数 GB 級**になりやすい。無料枠など **約 1GB 前後**の環境では **プロセスが Kill され、Python の Traceback が残らない**ことがある。 |
| **未処理の Python 例外** | DB・ファイル・モデル読み込み・HF API などで失敗。**Manage app → Logs** の **アプリ実行ログ**に `Traceback` が出ることが多い。 |
| **話者分離と Hugging Face** | `HF_TOKEN` 未設定やトークン無効で、**ダウンロードや認可に失敗**する（通常は例外としてログに出る）。 |
| **起動・実行タイムアウト** | 初回の重い import やモデル取得で **時間切れ**になる場合がある。 |

## 4. まず実施すべき確認（対策の前に）

1. **Streamlit Cloud の「Manage app」→ ログを開き、logs.md に無い **その後の行** を確認する**  
   - **「Script execution error」「Traceback」「Killed」「Out of memory」** などを探す。
2. **Secrets（または環境変数）に `HF_TOKEN` を設定**しているか確認する（話者分離を使う場合）。  
   - トークンは [Hugging Face Settings](https://huggingface.co/settings/tokens) で作成。
3. **メモリが疑わしい場合**  
   - リポジトリでは **`WHISPERX_ASR_MODEL`** で ASR モデルを変更できる（例: `base` / `small`）。**Cloud の Secrets に `WHISPERX_ASR_MODEL=base` 等を追加**して再デプロイし、落ちなくなるか試す。

## 5. 本リポジトリで入れた・使える緩和策

- **`WHISPERX_ASR_MODEL`**（既定は `large-v3`）  
  - **メモリが厳しい環境では `base` や `small` を指定**すると、OOM を避けやすい（精度は下がる）。
- **`TRANSCRIPTION_SKIP_DIARIZATION`**（例: Secrets で `"true"`）  
  - **話者分離（pyannote / Lightning チェックポイント）をスキップ**する。メモリを大きく使うため、**「Lightning automatically upgraded your loaded checkpoint…」の直後に Oh no** となる場合に有効。**全セグメントが同一話者ラベル**になる（用途に応じて可）。
- **`.env.example`** に上記の説明を追記済み。

## 6. logs.md だけでは結論できない点（まとめ）

- 提示された **logs.md はビルド成功と警告まで**で、**アプリ実行時の致命的エラー行が無い**。
- そのため **「警告が原因で Oh no」** と決めつけず、**Cloud 上の最新のフルログ**と **Secrets / メモリ / モデルサイズ** をセットで確認するのがよい。

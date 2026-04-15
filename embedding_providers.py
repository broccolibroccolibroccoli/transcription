"""
ベクトル検索用の埋め込み取得（バックエンド切り替え）。

環境変数 TRANSCRIPTION_EMBEDDING_BACKEND:
  - openai      : OpenAI API（従量課金）
  - ollama      : ローカル Ollama（無料・オフライン）
  - huggingface : Hugging Face Inference API（無料枠あり・HF_TOKEN 推奨）
  - gemini      : Google Gemini Embeddings API（無料枠あり）

次元は DB の VECTOR(n) と TRANSCRIPTION_EMBEDDING_DIMENSIONS を一致させること。
"""
from __future__ import annotations

import os
from typing import Any

EMBED_BACKEND_ENV = "TRANSCRIPTION_EMBEDDING_BACKEND"
EMBED_DIM_ENV = "TRANSCRIPTION_EMBEDDING_DIMENSIONS"

# OpenAI
EMBED_MODEL_ENV = "TRANSCRIPTION_EMBEDDING_MODEL"
DEFAULT_OPENAI_MODEL = "text-embedding-3-small"
DEFAULT_OPENAI_DIM = 1536

# Ollama
OLLAMA_BASE_ENV = "OLLAMA_BASE_URL"
DEFAULT_OLLAMA_BASE = "http://127.0.0.1:11434"
OLLAMA_MODEL_ENV = "TRANSCRIPTION_OLLAMA_EMBED_MODEL"
DEFAULT_OLLAMA_MODEL = "nomic-embed-text"
DEFAULT_OLLAMA_DIM = 768


def _normalize_ollama_base(raw: str) -> str:
    """OLLAMA_BASE_URL を Ollama ルート（ホスト:11434）に正規化する。

    末尾にだけ付いた /v1 や /api は取り除く（例: .../api + /api/embeddings → 404）。
    """
    base = raw.strip().rstrip("/")
    while base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    while base.endswith("/api"):
        base = base[:-4].rstrip("/")
    while base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base or DEFAULT_OLLAMA_BASE

# Hugging Face
HF_MODEL_ENV = "TRANSCRIPTION_HF_EMBED_MODEL"
DEFAULT_HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_HF_DIM = 384
HF_TOKEN_ENV = "HF_EMBEDDING_API_TOKEN"
HF_INFERENCE_BASE = "https://api-inference.huggingface.co/models"

# Gemini
GEMINI_KEY_ENV = "GEMINI_API_KEY"
GEMINI_KEY_ALT = "GOOGLE_API_KEY"
GEMINI_MODEL_ENV = "TRANSCRIPTION_GEMINI_EMBED_MODEL"
DEFAULT_GEMINI_MODEL = "text-embedding-004"
DEFAULT_GEMINI_DIM = 768

EMBED_BATCH_SIZE = 64


def get_embedding_backend() -> str:
    return (os.environ.get(EMBED_BACKEND_ENV) or "openai").strip().lower()


def get_expected_dimensions() -> int:
    try:
        return int((os.environ.get(EMBED_DIM_ENV) or _default_dim_for_backend()).strip())
    except ValueError:
        return _default_dim_for_backend()


def _default_dim_for_backend() -> int:
    b = get_embedding_backend()
    if b == "ollama":
        return DEFAULT_OLLAMA_DIM
    if b == "huggingface":
        return DEFAULT_HF_DIM
    if b == "gemini":
        return DEFAULT_GEMINI_DIM
    return DEFAULT_OPENAI_DIM


def embed_texts(texts: list[str]) -> list[list[float]]:
    """テキスト列を同じ順序で埋め込みベクトル列に変換する。"""
    if not texts:
        return []
    b = get_embedding_backend()
    if b == "ollama":
        return _embed_ollama(texts)
    if b == "huggingface":
        return _embed_hf(texts)
    if b == "gemini":
        return _embed_gemini(texts)
    return _embed_openai(texts)


def _embed_openai(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    model = (os.environ.get(EMBED_MODEL_ENV) or DEFAULT_OPENAI_MODEL).strip()
    dimensions = get_expected_dimensions()
    client = OpenAI()
    all_emb: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        kwargs: dict[str, Any] = {"model": model, "input": batch}
        if model.startswith("text-embedding-3"):
            kwargs["dimensions"] = dimensions
        resp = client.embeddings.create(**kwargs)
        for d in resp.data:
            vec = list(d.embedding)
            if len(vec) != dimensions:
                raise ValueError(
                    f"埋め込み次元 {len(vec)} が TRANSCRIPTION_EMBEDDING_DIMENSIONS={dimensions} と一致しません"
                )
            all_emb.append(vec)
    return all_emb


def _ollama_connection_help(
    exc: BaseException,
    *,
    base: str,
    endpoint: str,
    model: str,
) -> ConnectionError:
    """Connection refused 等をユーザー向けメッセージに変える。"""
    import errno

    msg = str(exc)
    reason = getattr(exc, "reason", None)
    refused = "Connection refused" in msg or "Errno 61" in msg
    if isinstance(reason, OSError) and reason.errno == errno.ECONNREFUSED:
        refused = True
    if refused:
        return ConnectionError(
            "Ollama に接続できません（Connection refused）。次を確認してください。\n"
            "1. Ollama アプリを起動するか、ターミナルで `ollama serve` が動いていること\n"
            f"2. `.env` の `OLLAMA_BASE_URL`（現在: {base}）が実際の待ち受けと一致すること\n"
            f"3. 埋め込みモデルを取得済みであること: `ollama pull {model}`\n"
            f"（接続先: {endpoint}）"
        )
    return ConnectionError(
        f"Ollama への HTTP リクエストに失敗しました: {exc}\n（接続先: {endpoint}）"
    )


def _embed_ollama(texts: list[str]) -> list[list[float]]:
    import json
    import urllib.error
    import urllib.request

    base = _normalize_ollama_base(os.environ.get(OLLAMA_BASE_ENV) or DEFAULT_OLLAMA_BASE)
    model = (os.environ.get(OLLAMA_MODEL_ENV) or DEFAULT_OLLAMA_MODEL).strip()
    dimensions = get_expected_dimensions()
    url = f"{base}/api/embeddings"
    out: list[list[float]] = []
    for t in texts:
        body = json.dumps({"model": model, "prompt": t}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise _ollama_connection_help(e, base=base, endpoint=url, model=model) from e
        emb = data.get("embedding")
        if not isinstance(emb, list):
            raise ValueError(f"Ollama 応答に embedding がありません: {data!r}")
        vec = [float(x) for x in emb]
        if len(vec) != dimensions:
            raise ValueError(
                f"Ollama 埋め込み次元 {len(vec)} が TRANSCRIPTION_EMBEDDING_DIMENSIONS={dimensions} と一致しません。"
                f"モデル {model} の次元に合わせて .env の次元と DB の VECTOR(n) を変更してください。"
            )
        out.append(vec)
    return out


def _parse_hf_embedding(raw: object) -> list[float]:
    """Inference API の応答を1本のベクトルに正規化する。"""
    if isinstance(raw, list):
        if not raw:
            raise ValueError("HF 応答が空です")
        if isinstance(raw[0], (int, float)):
            return [float(x) for x in raw]
        if isinstance(raw[0], list):
            return [float(x) for x in raw[0]]
    raise ValueError(f"HF 応答の形式が不正です: {type(raw)}")


def _embed_hf(texts: list[str]) -> list[list[float]]:
    import urllib.request
    import json
    from urllib.parse import quote

    model_id = (os.environ.get(HF_MODEL_ENV) or DEFAULT_HF_MODEL).strip()
    token = (os.environ.get(HF_TOKEN_ENV) or "").strip()
    dimensions = get_expected_dimensions()
    path = quote(model_id, safe="")
    url = f"{HF_INFERENCE_BASE}/{path}"
    all_emb: list[list[float]] = []
    for t in texts:
        body = json.dumps({"inputs": t}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        vec = _parse_hf_embedding(raw)
        if len(vec) != dimensions:
            raise ValueError(
                f"HF 埋め込み次元 {len(vec)} が TRANSCRIPTION_EMBEDDING_DIMENSIONS={dimensions} と一致しません。"
                "モデルに合わせて次元と DB の VECTOR(n) を揃えてください。"
            )
        all_emb.append(vec)
    return all_emb


def _embed_gemini(texts: list[str]) -> list[list[float]]:
    import urllib.request
    import json

    key = (os.environ.get(GEMINI_KEY_ENV) or os.environ.get(GEMINI_KEY_ALT) or "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY または GOOGLE_API_KEY を設定してください")
    model = (os.environ.get(GEMINI_MODEL_ENV) or DEFAULT_GEMINI_MODEL).strip()
    dimensions = get_expected_dimensions()
    name = model.replace("models/", "") if model.startswith("models/") else model
    base = "https://generativelanguage.googleapis.com/v1beta"
    all_emb: list[list[float]] = []
    for t in texts:
        url = f"{base}/models/{name}:embedContent?key={key}"
        body = json.dumps({"content": {"parts": [{"text": t}]}}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        emb = data.get("embedding") or {}
        vals = emb.get("values")
        if not isinstance(vals, list):
            raise ValueError(f"Gemini 応答に embedding.values がありません: {data!r}")
        vec = [float(x) for x in vals]
        if len(vec) != dimensions:
            raise ValueError(
                f"Gemini 埋め込み次元 {len(vec)} が TRANSCRIPTION_EMBEDDING_DIMENSIONS={dimensions} と一致しません"
            )
        all_emb.append(vec)
    return all_emb


def embedding_backend_label() -> str:
    return get_embedding_backend()


def has_embedding_credentials() -> bool:
    """環境変数だけで認証が揃っているか（OpenAI は .env のキーのみ判定）。"""
    b = get_embedding_backend()
    if b == "openai":
        return bool(os.environ.get("OPENAI_API_KEY", "").strip())
    if b == "ollama":
        return True
    if b == "huggingface":
        return True
    if b == "gemini":
        return bool(
            (os.environ.get(GEMINI_KEY_ENV) or os.environ.get(GEMINI_KEY_ALT) or "").strip()
        )
    return False

"""
YouTube URL から音声をダウンロードするユーティリティ
公開動画のみ対応します。
"""
import os
import re
from pathlib import Path
from typing import Tuple


# 対応するYouTube URLパターン
YOUTUBE_PATTERNS = [
    r"^https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+",
    r"^https?://(?:www\.)?youtube\.com/shorts/[\w-]+",
    r"^https?://youtu\.be/[\w-]+",
]


def is_youtube_url(url: str) -> bool:
    """文字列がYouTubeのURLかどうかを判定"""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    for pattern in YOUTUBE_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return True
    return False


def _sanitize_filename(name: str, max_length: int = 200) -> str:
    """ファイル名に使えない文字を除去"""
    # Windows/Linux/Macで問題になり得る文字を除去
    invalid = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid, "_", name)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized[:max_length] if len(sanitized) > max_length else sanitized


def download_youtube_audio(url: str, output_dir: str) -> Tuple[str, str]:
    """
    YouTube URLから音声をダウンロードし、WAV形式で保存する。

    Args:
        url: YouTubeの動画URL（公開動画のみ）
        output_dir: 保存先ディレクトリ

    Returns:
        (保存したファイルの絶対パス, 動画タイトル)

    Raises:
        ImportError: yt-dlpがインストールされていない
        Exception: ダウンロード失敗（非公開、削除済みなど）
    """
    try:
        import yt_dlp
    except ImportError:
        raise ImportError(
            "yt-dlp がインストールされていません。"
            "pip install yt-dlp を実行してください。"
        )

    os.makedirs(output_dir, exist_ok=True)
    # 動画IDでファイル名を固定し、確実にパスを特定できるようにする
    output_template = os.path.join(output_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "0",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            meta = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as e:
            raise Exception(
                f"ダウンロードに失敗しました。動画が公開されているか、URLを確認してください。\n詳細: {str(e)}"
            )

    video_id = meta.get("id", "unknown")
    title = meta.get("title", "unknown")
    # FFmpegExtractAudio により .wav に変換されている
    out_path = os.path.join(output_dir, f"{video_id}.wav")

    if not os.path.isfile(out_path):
        raise Exception("音声ファイルの保存に失敗しました。")

    # 一覧で分かりやすいよう、タイトル付きのファイル名にリネーム
    safe_title = _sanitize_filename(title)[:150]
    new_name = f"{safe_title}_{video_id}.wav"
    new_path = os.path.join(output_dir, new_name)
    if new_path != out_path:
        os.rename(out_path, new_path)
        out_path = new_path

    return os.path.abspath(out_path), title

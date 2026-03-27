"""
インタビュー音声 文字起こし・要約アプリ
Streamlit ベースのWebアプリ
"""
import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import os
import html
import csv
import io
from datetime import datetime, timedelta

# 設定（デプロイ時はリポジトリ直下。環境変数 TRANSCRIPTION_BASE_DIR で上書き可）
BASE_DIR = os.environ.get("TRANSCRIPTION_BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "transcription.db")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")

# True にするとサイドバーに YouTube URL 入力タブを表示
SHOW_YOUTUBE_UPLOAD = True

# アップロード用ディレクトリを作成
os.makedirs(UPLOADS_DIR, exist_ok=True)

# データベーススキーマを確実に作成
from database_schema import create_database_schema
create_database_schema(DB_PATH)

# ページ設定
st.set_page_config(
    page_title="音声文字起こしアプリ",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# KARTE サポートサイト（https://support.karte.io/）トンマナ参考
# アクセントカラー: ティール #2aab9f
KARTE_ACADEMY_CSS = """
<style>
/* KARTE サポートサイト風カラーパレット */
:root {
    --accent: #2aab9f;
    --accent-hover: #23998f;
    --accent-soft: rgba(42, 171, 159, 0.08);
    --academy-slate: #334155;
    --academy-slate-light: #475569;
    --academy-indigo: #6366F1;
    --academy-indigo-soft: rgba(99, 102, 241, 0.08);
    --academy-bg: #FAFBFC;
    --academy-card: #FFFFFF;
    --academy-border: #E2E8F0;
    --academy-text: #334155;
    --academy-text-muted: #64748B;
}

/* メインコンテンツ背景 */
.stApp {
    background: var(--academy-bg) !important;
}

/* ヘッダー - アクセントカラー下線 */
.stApp header[data-testid="stHeader"] {
    background: var(--academy-card) !important;
    border-bottom: 3px solid var(--accent) !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05) !important;
}

/* サイドバー */
[data-testid="stSidebar"] {
    background: var(--academy-card) !important;
    border-right: 1px solid var(--academy-border) !important;
    box-shadow: 2px 0 8px rgba(0, 0, 0, 0.03) !important;
}

/* サイドバーヘッダー - transcriptionロゴ */
[data-testid="stSidebar"] > div:first-child {
    padding-top: 0 !important;
}
[data-testid="stSidebar"]::before {
    content: "transcription" !important;
    display: block !important;
    color: #2aab9f !important;
    font-size: 1.1rem !important;
    font-weight: 600 !important;
    padding: 1rem 1.25rem 1rem !important;
    border-bottom: 1px solid var(--academy-border) !important;
}

[data-testid="stSidebar"] .stMarkdown h2 {
    color: var(--academy-slate) !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    padding: 0.5rem 0 !important;
    margin-bottom: 0.75rem !important;
    border-left: 3px solid var(--accent) !important;
    padding-left: 12px !important;
}

/* タイトル - Academy風の読みやすい見出し */
.main .block-container h1 {
    color: var(--academy-slate) !important;
    font-weight: 700 !important;
    font-size: 1.75rem !important;
    letter-spacing: -0.02em !important;
    margin-bottom: 0.25rem !important;
}

/* サブヘッダー */
h2, h3 {
    color: var(--academy-slate) !important;
    font-weight: 600 !important;
    font-size: 1.1rem !important;
}

/* メインコンテンツエリアのパディング */
.main .block-container {
    padding-top: 2rem !important;
    padding-bottom: 3rem !important;
    max-width: 900px !important;
}

/* ボタン - アクセントカラー CTA */
.stButton > button[kind="primary"] {
    background: linear-gradient(180deg, #3bc4b8 0%, var(--accent) 100%) !important;
    border: none !important;
    font-weight: 600 !important;
    border-radius: 6px !important;
    padding: 0.5rem 1.25rem !important;
    box-shadow: 0 2px 4px rgba(42, 171, 159, 0.25) !important;
}

.stButton > button[kind="primary"]:hover {
    background: var(--accent-hover) !important;
    box-shadow: 0 4px 8px rgba(42, 171, 159, 0.35) !important;
}

/* エクスパンダー - Academy風コースカードスタイル */
.streamlit-expanderHeader {
    background: var(--academy-card) !important;
    border: 1px solid var(--academy-border) !important;
    border-radius: 12px !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05) !important;
    padding: 1rem 1.25rem !important;
}

.streamlit-expanderContent {
    background: var(--academy-card) !important;
    border: 1px solid var(--academy-border) !important;
    border-top: none !important;
    border-radius: 0 0 12px 12px !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04) !important;
}

/* セクション区切り - Academy風 */
hr {
    border: none !important;
    height: 1px !important;
    background: var(--academy-border) !important;
    margin: 1.5rem 0 !important;
}

/* アラート・メッセージ */
.stAlert {
    border-radius: 8px !important;
}

/* ファイルアップローダー - 文字起こしさん風（https://mojiokoshi3.com/ja/） */
/* 波線の枠をサイドバー幅100%に */
[data-testid="stSidebar"] .stFileUploader,
[data-testid="stSidebar"] [data-testid="stFileUploader"],
[data-testid="stSidebar"] [data-testid="stFileUploader"] > div,
[data-testid="stSidebar"] [data-testid="stFileUploader"] section,
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"],
[data-testid="stSidebar"] .st-key-sidebar-file-uploader,
[data-testid="stSidebar"] .st-key-sidebar_file_uploader {
    width: 100% !important;
    max-width: 100% !important;
}

[data-testid="stFileUploader"] {
    background: var(--accent-soft) !important;
    border: 2px dashed var(--accent) !important;
    border-radius: 12px !important;
}

/* ①音声ファイルを選択のラベルを非表示 */
[data-testid="stSidebar"] [data-testid="stFileUploader"] label,
[data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderLabel"] {
    display: none !important;
}

/* ②③Drag and drop → ファイルをドラッグ&ドロップ + または */
[data-testid="stFileUploaderDropzoneInstructions"],
[data-testid="stFileUploader"] [class*="Instructions"] {
    font-size: 0 !important;
}

[data-testid="stFileUploaderDropzoneInstructions"]::before,
[data-testid="stFileUploader"] [class*="Instructions"]::before {
    content: "ファイルをドラッグ&ドロップ\A\Aまたは" !important;
    white-space: pre !important;
    font-size: 0.95rem !important;
    display: block !important;
    text-align: center !important;
}

/* 波線枠をwidth100%に、内部は中央揃え */
[data-testid="stFileUploader"] {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    width: 100% !important;
    box-sizing: border-box !important;
}

[data-testid="stFileUploader"] section,
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    width: 100% !important;
    box-sizing: border-box !important;
}

/* ファイルを選択ボタン（Browse）のみ。Remove（×）ボタンは除外 */
[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"],
[data-testid="stFileUploader"] button[data-testid="stBaseButton-secondary"],
[data-testid="stFileUploader"] button:not([kind="primary"]):not([data-testid="stBaseButton-minimal"]) {
    font-size: 0 !important;
    line-height: 1 !important;
    background: #2aab9f !important;
    border-color: #2aab9f !important;
    color: #ffffff !important;
}

[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"]:hover,
[data-testid="stFileUploader"] button[data-testid="stBaseButton-secondary"]:hover,
[data-testid="stFileUploader"] button:not([kind="primary"]):not([data-testid="stBaseButton-minimal"]):hover {
    background: #23998f !important;
    border-color: #23998f !important;
}

[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"]::after,
[data-testid="stFileUploader"] button[data-testid="stBaseButton-secondary"]::after,
[data-testid="stFileUploader"] button:not([kind="primary"]):not([data-testid="stBaseButton-minimal"])::after {
    content: "ファイルを選択" !important;
    font-size: 0.9rem !important;
    color: #ffffff !important;
}

/* Remove（×）ボタンに「ファイルを選択」が表示されないよう明示的に空に */
[data-testid="stFileUploader"] [data-testid="stFileUploaderDeleteBtn"] button::after,
[data-testid="stFileUploader"] [data-testid="stBaseButton-minimal"]::after {
    content: none !important;
}

/* キャプション */
.stCaption {
    color: var(--academy-text-muted) !important;
}

/* ファイル一覧 - ファイル名ボタンを左揃え */
.main [data-testid="stHorizontalBlock"] .stButton > button {
    justify-content: flex-start !important;
    text-align: left !important;
}
/* 登録ファイル一覧 - ボタン内のリンクマークを非表示 */
.main [data-testid="stHorizontalBlock"]:not(:has(button[kind="primary"])) > div:first-child button a::after {
    content: none !important;
}

/* サイドバー - 行間を詰めて上に詰める */
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {
    padding-top: 0.25rem !important;
    padding-bottom: 0.25rem !important;
}
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
    margin-bottom: 0 !important;
    padding-bottom: 0.1rem !important;
}
[data-testid="stSidebar"] .stExpander {
    margin-top: 0.25rem !important;
    margin-bottom: 0.25rem !important;
}
[data-testid="stSidebar"] [data-testid="stFileUploader"] {
    margin-top: 0.25rem !important;
    margin-bottom: 0.25rem !important;
}
[data-testid="stSidebar"] hr {
    margin: 0.5rem 0 !important;
}
[data-testid="stSidebar"] .stMarkdown p {
    margin: 0.2rem 0 !important;
}

/* サイドバー 文字起こしを開始ボタン - 左右中央揃え（幅制限解除・改行禁止） */
[data-testid="stSidebar"] [data-testid="column"] {
    flex: 1 1 auto !important;
    min-width: max-content !important;
    width: auto !important;
}
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
    display: flex !important;
    justify-content: center !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
}
[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] [data-testid="stAlert"] p,
[data-testid="stSidebar"] .stSpinner {
    white-space: nowrap !important;
    word-break: keep-all !important;
    width: max-content !important;
    margin: 0 auto !important;
}

/* サイドバー 処理中・完了予定・成功/エラー - 左右中央揃え */
/* アラート（成功/エラー）のアイコンと文字を中央寄せ */
[data-testid="stSidebar"] [data-testid="stAlert"] > div {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    text-align: center !important;
}
/* スピナーのアイコンと文字を縦並びにして中央寄せ */
[data-testid="stSidebar"] [data-testid="stSpinner"],
[data-testid="stSidebar"] .stSpinner {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    width: 100% !important;
}
[data-testid="stSidebar"] [data-testid="stStatusWidget"] {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    width: 100% !important;
}

/* 修正・CSVボタン行 - 右寄せ */
.main [data-testid="stHorizontalBlock"]:has(button[kind="primary"]) > div:nth-child(2),
.main [data-testid="stHorizontalBlock"]:has(button[kind="primary"]) > div:nth-child(3) {
    display: flex !important;
    justify-content: flex-end !important;
}
/* CSVダウンロードボタン - 改行なしで幅をテキストに合わせる */
.main [data-testid="stHorizontalBlock"]:has(button[kind="primary"]) > div:nth-child(2) {
    min-width: 0 !important;
}
.main [data-testid="stHorizontalBlock"]:has(button[kind="primary"]) > div:nth-child(2) button,
.main [data-testid="stHorizontalBlock"]:has(button[kind="primary"]) > div:nth-child(3) button {
    white-space: nowrap !important;
    width: fit-content !important;
    min-width: fit-content !important;
    flex-shrink: 0 !important;
}

/* 文字起こし結果表示 - 修正・ダウンロード・プロジェクト移動・削除ボタンをアイコンのみに */
.main [data-testid="stHorizontalBlock"]:has([data-testid="stDownloadButton"]) .stButton > button,
.main [data-testid="stHorizontalBlock"]:has([data-testid="stDownloadButton"]) [data-testid="stDownloadButton"] a,
.main [data-testid="stHorizontalBlock"]:has([data-testid="stDownloadButton"]) [data-testid="stDownloadButton"] button {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}
.main [data-testid="stHorizontalBlock"]:has([data-testid="stDownloadButton"]) .stButton > button:hover,
.main [data-testid="stHorizontalBlock"]:has([data-testid="stDownloadButton"]) [data-testid="stDownloadButton"] a:hover,
.main [data-testid="stHorizontalBlock"]:has([data-testid="stDownloadButton"]) [data-testid="stDownloadButton"] button:hover {
    background: rgba(42, 171, 159, 0.1) !important;
    border: none !important;
}

/* 文字起こし表示 - マウスオーバーでハイライト */
.transcript-segment {
    padding: 0.5rem 0 !important;
    border-radius: 4px !important;
}
.transcript-segment:hover {
    background-color: rgba(42, 171, 159, 0.08) !important;
}

/* フォント */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif !important;
}
</style>
"""
st.markdown(KARTE_ACADEMY_CSS, unsafe_allow_html=True)



def format_time_mm_ss(seconds):
    """秒数を「X分Y秒」形式に変換（秒以下は表示しない）"""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}分{s}秒"


def get_projects():
    """プロジェクト一覧を取得"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM projects ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return rows


def create_project(name: str) -> tuple[bool, str | None]:
    """新規プロジェクトを作成 Returns: (success, error_message)"""
    name = name.strip()
    if not name:
        return False, "プロジェクト名を入力してください"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO projects (name) VALUES (?)", (name,))
        conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        conn.rollback()
        return False, "そのプロジェクト名は既に存在します"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def get_files_from_db(project_id: int | None = None):
    """データベースからファイル一覧を取得（project_idで絞り込み可能）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if project_id is not None:
        cursor.execute("""
            SELECT id, filename, duration, status, processed_at, error_message
            FROM files
            WHERE project_id = ?
            ORDER BY processed_at DESC
        """, (project_id,))
    else:
        cursor.execute("""
            SELECT id, filename, duration, status, processed_at, error_message
            FROM files
            ORDER BY project_id, processed_at DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_file_by_id(file_id: int) -> tuple | None:
    """ファイルIDで1件取得（プロジェクト情報含む）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.id, f.filename, f.duration, f.status, f.processed_at, f.error_message,
               f.project_id, p.name as project_name
        FROM files f
        JOIN projects p ON f.project_id = p.id
        WHERE f.id = ?
    """, (file_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def get_files_with_projects(project_id: int | None = None):
    """ファイル一覧をプロジェクト情報付きで取得"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if project_id is not None:
        cursor.execute("""
            SELECT f.id, f.filename, f.duration, f.status, f.processed_at, f.error_message,
                   f.project_id, p.name as project_name
            FROM files f
            JOIN projects p ON f.project_id = p.id
            WHERE f.project_id = ?
            ORDER BY f.processed_at DESC
        """, (project_id,))
    else:
        cursor.execute("""
            SELECT f.id, f.filename, f.duration, f.status, f.processed_at, f.error_message,
                   f.project_id, p.name as project_name
            FROM files f
            JOIN projects p ON f.project_id = p.id
            ORDER BY f.project_id, f.processed_at DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def assign_file_to_project(file_id: int, project_id: int) -> tuple[bool, str | None]:
    """ファイルをプロジェクトに割り当て"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE files SET project_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id, file_id),
        )
        conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        conn.rollback()
        return False, "そのプロジェクト内に同じファイル名が存在します"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def get_segments_by_file_id(file_id):
    """ファイルIDからセグメントを取得"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT segment_index, speaker, text, start_time, end_time
        FROM segments
        WHERE file_id = ?
        ORDER BY segment_index
    """, (file_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def segments_to_csv(segments: list) -> bytes:
    """セグメントリストをCSV形式のバイト列に変換（UTF-8 BOM付きでExcel対応）"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["segment_index", "speaker", "start_time_sec", "end_time_sec", "start_time", "end_time", "text"])
    for seg_idx, speaker, text, start, end in segments:
        speaker_str = speaker or "UNKNOWN"
        writer.writerow([
            seg_idx,
            speaker_str,
            f"{start:.2f}",
            f"{end:.2f}",
            format_time_mm_ss(start),
            format_time_mm_ss(end),
            text
        ])
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def update_segment_text(file_id, segment_index, new_text):
    """セグメントのテキストを更新"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE segments SET text = ? WHERE file_id = ? AND segment_index = ?
        """, (new_text.strip(), file_id, segment_index))
        conn.commit()
        return cursor.rowcount > 0
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def update_segment_speaker(file_id, segment_index, new_speaker):
    """セグメントのスピーカーを更新"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # 空の場合は UNKNOWN に
        speaker_val = (new_speaker or "").strip() or "UNKNOWN"
        cursor.execute("""
            UPDATE segments SET speaker = ? WHERE file_id = ? AND segment_index = ?
        """, (speaker_val, file_id, segment_index))
        conn.commit()
        return cursor.rowcount > 0
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def update_filename(file_id: int, new_filename: str) -> tuple[bool, str | None]:
    """
    ファイルの表示名（filename）を更新する
    Returns: (success: bool, error_message: str or None)
    """
    new_filename = new_filename.strip()
    if not new_filename:
        return False, "ファイル名を入力してください"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT filename FROM files WHERE id = ?", (file_id,))
        row = cursor.fetchone()
        if not row:
            return False, "ファイルが見つかりません"
        cursor.execute(
            "UPDATE files SET filename = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_filename, file_id),
        )
        conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        conn.rollback()
        return False, "そのファイル名は既に使用されています"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


@st.dialog("プロジェクトに移動")
def move_to_project_dialog(file_id: int, filename: str):
    """ファイルを別プロジェクトに移動"""
    st.write(f"**{filename}** を移動するプロジェクトを選択してください")
    projects = get_projects()
    options = {p[1]: p[0] for p in projects}
    target = st.selectbox("プロジェクト", options=list(options.keys()), key="move_project_select")
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button("移動", type="primary", key="move_confirm"):
            target_id = options[target]
            ok, err = assign_file_to_project(file_id, target_id)
            if ok:
                st.session_state.pending_move = None
                st.rerun()
            else:
                st.error(err)
    with col_cancel:
        if st.button("キャンセル", key="move_cancel"):
            st.session_state.pending_move = None
            st.rerun()


@st.dialog("ファイル名の変更")
def rename_file_dialog(file_id: int, current_filename: str):
    """ファイル名変更モーダル"""
    new_name = st.text_input(
        "新しいファイル名",
        value=current_filename,
        key=f"rename_input_{file_id}",
        placeholder="ファイル名を入力",
    )
    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button("保存", type="primary", key=f"rename_save_{file_id}"):
            if new_name and new_name.strip():
                success, err = update_filename(file_id, new_name.strip())
                if success:
                    if st.session_state.selected_filename == current_filename:
                        st.session_state.selected_filename = new_name.strip()
                    st.session_state.pending_rename = None
                    st.rerun()
                else:
                    st.error(err)
            else:
                st.warning("ファイル名を入力してください")
    with col_cancel:
        if st.button("キャンセル", key=f"rename_cancel_{file_id}"):
            st.session_state.pending_rename = None
            st.rerun()


@st.dialog("編集内容の確認")
def confirm_exit_edit_dialog(file_id: int, segments: list):
    """編集中の画面遷移時の確認モーダル"""
    st.write("編集内容を保存しますか？")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("保存して終了", type="primary"):
            for seg_idx, speaker, text, start, end in segments:
                key_text = f"edit_{file_id}_{seg_idx}"
                key_speaker = f"edit_speaker_{file_id}_{seg_idx}"
                new_text = st.session_state.get(key_text, text)
                new_speaker = st.session_state.get(key_speaker, speaker or "UNKNOWN")
                if new_text is not None:
                    update_segment_text(file_id, seg_idx, new_text)
                if new_speaker is not None:
                    update_segment_speaker(file_id, seg_idx, new_speaker)
            st.session_state.editing_file_id = None
            st.session_state.selected_file_id = None
            st.session_state.selected_filename = None
            st.session_state.pending_confirm_exit = False
            st.rerun()
    with col2:
        if st.button("保存せずに終了"):
            st.session_state.editing_file_id = None
            st.session_state.selected_file_id = None
            st.session_state.selected_filename = None
            st.session_state.pending_confirm_exit = False
            st.rerun()
    with col3:
        if st.button("キャンセル"):
            st.session_state.pending_confirm_exit = False
            st.rerun()


@st.dialog("削除の確認")
def confirm_delete_dialog(file_id: int, filename: str):
    """削除確認モーダル"""
    # 削除完了後の画面か
    if st.session_state.get("delete_completed"):
        st.success(f"**{st.session_state.delete_completed}** を削除しました")
        if st.button("閉じる", type="primary"):
            st.session_state.delete_completed = None
            st.session_state.pending_delete = None
            if st.session_state.selected_file_id == file_id:
                st.session_state.selected_file_id = None
                st.session_state.selected_filename = None
            if st.session_state.editing_file_id == file_id:
                st.session_state.editing_file_id = None
            st.rerun()
        return

    st.write("本当に削除しますか？")
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("はい", type="primary"):
            success, err = delete_file(file_id)
            if success:
                st.session_state.delete_completed = filename
                st.rerun()  # ダイアログを再描画して完了メッセージ表示
            else:
                st.error(f"削除に失敗しました: {err}")
                if st.button("閉じる", key="delete_error_close"):
                    st.session_state.pending_delete = None
                    st.rerun()
    with col_no:
        if st.button("いいえ"):
            st.session_state.pending_delete = None
            st.rerun()


def delete_file(file_id):
    """
    ファイルをDBとディスクから削除する
    Returns: (success: bool, error_message: str or None)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT filepath FROM files WHERE id = ?", (file_id,))
        row = cursor.fetchone()
        if not row:
            return False, "ファイルが見つかりません"
        filepath = row[0]

        # 関連データを削除（CASCADE が効かない場合に備えて明示的に削除）
        cursor.execute("DELETE FROM segments WHERE file_id = ?", (file_id,))
        try:
            cursor.execute("DELETE FROM summaries WHERE file_id = ?", (file_id,))
        except sqlite3.OperationalError:
            pass  # summariesテーブルが存在しない場合はスキップ
        cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()

        # 物理ファイルを削除
        if filepath and os.path.isfile(filepath):
            try:
                os.remove(filepath)
            except OSError as e:
                pass  # ファイル削除失敗は無視（DBからは削除済み）
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
    return True, None


def get_audio_duration_seconds(audio_path: str) -> float:
    """音声ファイルの長さ（秒）を取得"""
    try:
        import whisperx
        audio = whisperx.load_audio(audio_path)
        return len(audio) / 16000.0
    except ImportError:
        # whisperx未インストール時は wave で代用
        try:
            import wave
            with wave.open(audio_path, "rb") as w:
                return w.getnframes() / w.getframerate()
        except Exception:
            return 0.0
    except Exception:
        return 0.0


def estimate_completion_time(duration_seconds: float) -> datetime:
    """
    音声長から処理完了予定時刻を推定
    WhisperX(CPU)はおおよそ実時間の2〜4倍かかる想定
    """
    if duration_seconds <= 0:
        return datetime.now() + timedelta(minutes=5)
    # 実時間の3倍を目安（CPU想定）
    estimated_minutes = (duration_seconds / 60) * 3
    return datetime.now() + timedelta(minutes=min(estimated_minutes, 120))


def process_uploaded_file(uploaded_file, project_id: int = 1):
    """アップロードされたファイルを保存して処理"""
    # ファイルを保存
    save_path = os.path.join(UPLOADS_DIR, uploaded_file.name)
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getvalue())
    
    try:
        from batch_process import process_audio_file, DB_PATH
    except ImportError:
        return {
            "success": False,
            "error": "whisperx がインストールされていません。文字起こしには whisperx が必要です。"
            "仮想環境で pip install whisperx を実行するか、"
            "既存の whisperx 環境（例: ~/venvs/whisperx）でアプリを起動してください。",
        }
    from database_schema import create_database_schema

    create_database_schema(DB_PATH)
    return process_audio_file(save_path, DB_PATH, project_id=project_id)


def process_youtube_url(url: str, project_id: int = 1):
    """YouTube URLから音声をダウンロードして処理"""
    from youtube_utils import is_youtube_url, download_youtube_audio

    if not is_youtube_url(url):
        return {"success": False, "error": "有効なYouTubeのURLを入力してください。"}

    try:
        audio_path, title = download_youtube_audio(url, UPLOADS_DIR)
    except ImportError as e:
        return {
            "success": False,
            "error": f"yt-dlp がインストールされていません。pip install yt-dlp を実行してください。\n{e}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

    try:
        from batch_process import process_audio_file, DB_PATH
    except ImportError:
        return {
            "success": False,
            "error": "whisperx がインストールされていません。文字起こしには whisperx が必要です。",
        }
    from database_schema import create_database_schema

    create_database_schema(DB_PATH)
    return process_audio_file(audio_path, DB_PATH, project_id=project_id)


# ドラッグオーバー用オーバーレイ
DRAG_OVERLAY_HTML = """
<div></div>
<script>
(function() {
    var doc = (window.parent && window.parent.document) ? window.parent.document : document;
    var overlay;
    function waitSidebar() {
        var sidebar = doc.querySelector('[data-testid="stSidebar"]');
        if (!sidebar) { setTimeout(waitSidebar, 100); return; }
        var existing = doc.getElementById('transcription-drop-overlay');
        if (existing) { overlay = existing; bindDropzone(); return; }
        if (getComputedStyle(sidebar).position === 'static') sidebar.style.position = 'relative';
        overlay = doc.createElement('div');
        overlay.id = 'transcription-drop-overlay';
        overlay.style.cssText = 'display:none;position:absolute;inset:0;background:rgba(42,171,159,0.9);z-index:99999;align-items:center;justify-content:center;pointer-events:none;';
        overlay.innerHTML = '<div style="font-size:1.1rem;font-weight:600;color:#fff;text-shadow:0 1px 3px rgba(0,0,0,0.5);text-align:center;">ここにファイルをドロップ</div>';
        sidebar.appendChild(overlay);
        bindDropzone();
    }
    waitSidebar();

    function showO() { if(overlay) overlay.style.display = 'flex'; }
    function hideO() { if(overlay) overlay.style.display = 'none'; }

    function bindDropzone() {
        var dz = doc.querySelector('[data-testid="stFileUploaderDropzone"]');
        if (!dz) { setTimeout(bindDropzone, 100); return; }
        dz.addEventListener('dragenter', function(e) {
            if (e.dataTransfer && e.dataTransfer.types.indexOf('Files') >= 0) showO();
        });
        dz.addEventListener('dragleave', function(e) {
            var n = e.relatedTarget;
            if (!n || !dz.contains(n)) hideO();
        });
        dz.addEventListener('drop', hideO);
    }
})();
</script>
"""

# セッション状態の初期化（サイドバーより前に実行）
if "selected_project_id" not in st.session_state:
    st.session_state.selected_project_id = 1

# サイドバー: プロジェクト選択・アップロード
with st.sidebar:
    st.markdown("**📁 プロジェクト**")
    projects = get_projects()
    options_with_all = [("すべて", None)] + [(p[1], p[0]) for p in projects]
    default_idx = 0
    for i, (label, pid) in enumerate(options_with_all):
        if pid == st.session_state.selected_project_id or (pid is None and st.session_state.selected_project_id is None):
            default_idx = i
            break
    selected_label = st.selectbox(
        "プロジェクト",
        options=[o[0] for o in options_with_all],
        index=default_idx,
        key="sidebar_project_select",
        label_visibility="collapsed",
    )
    st.session_state.selected_project_id = next(
        (o[1] for o in options_with_all if o[0] == selected_label), 1
    )

    with st.expander("➕ 新規プロジェクト作成"):
        new_proj_name = st.text_input("プロジェクト名", key="new_project_name", placeholder="例: 第1回インタビュー")
        if st.button("作成", key="create_project_btn"):
            if new_proj_name and new_proj_name.strip():
                ok, err = create_project(new_proj_name.strip())
                if ok:
                    st.success("プロジェクトを作成しました")
                    st.rerun()
                else:
                    st.error(err)
            else:
                st.warning("プロジェクト名を入力してください")

    st.divider()

    def _render_file_uploader_sidebar():
        uploaded = st.file_uploader(
            " ",
            type=["mp4", "wav", "mp3", "m4a", "flac"],
            label_visibility="collapsed",
            help="mp4, wav, mp3, m4a, flac 形式に対応",
            key="sidebar_file_uploader"
        )
        components.html(DRAG_OVERLAY_HTML, height=0)
        st.markdown(
            '<p style="text-align: center; color: #64748B; font-size: 0.8rem; margin: 0.2rem 0;">'
            '1ファイル最大30分、200MBまで</p>'
            '<p style="text-align: center; color: #64748B; font-size: 0.8rem; margin: 0.1rem 0;">'
            'mp4, wav, mp3, m4a, flacなどの音声ファイルに対応</p>',
            unsafe_allow_html=True
        )
        if uploaded is not None:
            _, col_btn, _ = st.columns([1, 2, 1])
            with col_btn:
                if st.button("🚀 文字起こしを開始", type="primary", key="sidebar_transcription_start"):
                    save_path = os.path.join(UPLOADS_DIR, uploaded.name)
                    with open(save_path, "wb") as f:
                        f.write(uploaded.getvalue())
                    duration_sec = get_audio_duration_seconds(save_path)
                    expected_end = estimate_completion_time(duration_sec)
                    expected_str = expected_end.strftime("%Y/%m/%d %H:%M頃")
                    spinner_msg = f"処理中...\n\n完了予定: {expected_str}"
                    with st.spinner(spinner_msg):
                        result = process_uploaded_file(uploaded, project_id=st.session_state.selected_project_id)
                    if result.get("success"):
                        st.success(f"✅ {result.get('filename')} の処理が完了しました")
                        st.rerun()
                    else:
                        st.error(f"❌ エラー: {result.get('error', 'Unknown error')}")

    if SHOW_YOUTUBE_UPLOAD:
        tab_file, tab_youtube = st.tabs(["📁 ファイル", "▶️ YouTube URL"])
        with tab_file:
            _render_file_uploader_sidebar()
        with tab_youtube:
            youtube_url = st.text_input(
                "YouTube URL",
                placeholder="https://www.youtube.com/watch?v=...",
                key="sidebar_youtube_url",
                label_visibility="collapsed",
            )
            st.markdown(
                '<p style="text-align: center; color: #64748B; font-size: 0.8rem; margin: 0.2rem 0;">'
                '公開されているYouTube動画のURLを入力</p>',
                unsafe_allow_html=True
            )
            if youtube_url and youtube_url.strip():
                _, col_btn, _ = st.columns([1, 2, 1])
                with col_btn:
                    if st.button("🚀 文字起こしを開始", type="primary", key="sidebar_youtube_start"):
                        with st.spinner("YouTubeから音声をダウンロードし、文字起こし処理中..."):
                            result = process_youtube_url(
                                youtube_url.strip(),
                                project_id=st.session_state.selected_project_id,
                            )
                        if result.get("success"):
                            st.success(f"✅ {result.get('filename')} の処理が完了しました")
                            st.rerun()
                        else:
                            st.error(f"❌ エラー: {result.get('error', 'Unknown error')}")
    else:
        _render_file_uploader_sidebar()

# メイン: ファイル一覧と詳細
selected_proj = st.session_state.get("selected_project_id")
files = get_files_with_projects(project_id=selected_proj)

if "selected_file_id" not in st.session_state:
    st.session_state.selected_file_id = None
if "selected_filename" not in st.session_state:
    st.session_state.selected_filename = None
if "pending_delete" not in st.session_state:
    st.session_state.pending_delete = None
if "pending_rename" not in st.session_state:
    st.session_state.pending_rename = None
if "pending_move" not in st.session_state:
    st.session_state.pending_move = None
if "editing_file_id" not in st.session_state:
    st.session_state.editing_file_id = None
if "pending_confirm_exit" not in st.session_state:
    st.session_state.pending_confirm_exit = False

# ファイルが選択されている場合: 別ページで文字起こしを表示
if st.session_state.selected_file_id is not None:
    file_id = st.session_state.selected_file_id
    filename = st.session_state.selected_filename or ""

    # 選択中ファイルの情報を取得（プロジェクト選択に関係なく取得）
    file_info = get_file_by_id(file_id)
    if file_info:
        _, filename, duration, status, processed_at, error_msg, *_ = file_info

        if st.button("← 一覧に戻る", key="back_to_list"):
            if st.session_state.editing_file_id == file_id:
                st.session_state.pending_confirm_exit = True
                st.rerun()
            else:
                st.session_state.selected_file_id = None
                st.session_state.selected_filename = None
                st.rerun()

        # 編集中の画面遷移確認モーダル
        if st.session_state.pending_confirm_exit and st.session_state.editing_file_id == file_id:
            segments_for_modal = get_segments_by_file_id(file_id)
            confirm_exit_edit_dialog(file_id, segments_for_modal)

        st.subheader(f"📄 {filename}")
        if error_msg:
            st.error(error_msg)
        if status == "completed":
            segments = get_segments_by_file_id(file_id)
            if segments:
                is_editing = st.session_state.editing_file_id == file_id

                # 修正 / CSV / プロジェクト移動 / 削除（右寄せ、アイコンのみ）
                _, col_btns = st.columns([4, 1])
                with col_btns:
                    sub1, sub2, sub3, sub4 = st.columns(4, gap="xsmall")
                with sub1:
                    if is_editing:
                        if st.button("🔄", key=f"save_and_exit_{file_id}", type="primary", help="編集内容を保存"):
                            for seg_idx, speaker, text, start, end in segments:
                                key_text = f"edit_{file_id}_{seg_idx}"
                                key_speaker = f"edit_speaker_{file_id}_{seg_idx}"
                                new_text = st.session_state.get(key_text, text)
                                new_speaker = st.session_state.get(key_speaker, speaker or "UNKNOWN")
                                if new_text is not None:
                                    update_segment_text(file_id, seg_idx, new_text)
                                if new_speaker is not None:
                                    update_segment_speaker(file_id, seg_idx, new_speaker)
                            st.session_state.editing_file_id = None
                            st.success("✓ 修正を保存しました")
                            st.rerun()
                    else:
                        if st.button("✏️", key=f"start_edit_{file_id}", help="修正"):
                            st.session_state.editing_file_id = file_id
                            st.rerun()
                with sub2:
                    # 表示時はDBから、編集時は編集中の内容を使用
                    if is_editing:
                        segs_for_csv = []
                        for seg_idx, speaker, text, start, end in segments:
                            key_text = f"edit_{file_id}_{seg_idx}"
                            key_speaker = f"edit_speaker_{file_id}_{seg_idx}"
                            text_val = st.session_state.get(key_text, text)
                            speaker_val = st.session_state.get(key_speaker, speaker or "UNKNOWN")
                            segs_for_csv.append((seg_idx, speaker_val or "UNKNOWN", text_val or text, start, end))
                    else:
                        segs_for_csv = [(i, s or "UNKNOWN", t, st, e) for i, s, t, st, e in segments]
                    csv_content = segments_to_csv(segs_for_csv)
                    base_name = os.path.splitext(filename)[0]
                    dl_filename = f"{base_name}_文字起こし.csv"
                    st.download_button(
                        "📥",
                        data=csv_content,
                        file_name=dl_filename,
                        mime="text/csv",
                        key=f"csv_dl_{file_id}",
                        use_container_width=False,
                        help="CSV形式でダウンロード"
                    )
                with sub3:
                    if st.button("📂", key=f"move_detail_{file_id}", help="プロジェクトに移動"):
                        st.session_state.pending_move = (file_id, filename)
                        st.rerun()
                with sub4:
                    if st.button("🗑️", key=f"delete_detail_{file_id}", help="削除"):
                        st.session_state.pending_delete = (file_id, filename)
                        st.rerun()

                if is_editing:
                    # 選択中（フォーカス中）のテキストエリアのみ枠をprimaryColorで強調
                    st.markdown("""
                    <style>
                        [data-testid="stTextArea"] textarea:focus {
                            border: 2px solid #2aab9f !important;
                            border-radius: 6px !important;
                            box-shadow: 0 0 0 2px rgba(42, 171, 159, 0.3) !important;
                        }
                    </style>
                    """, unsafe_allow_html=True)
                    # 1発言単位で編集可能なテキスト入力（話者・テキスト両方）
                    st.caption("話者名やテキストを修正して「🔄」を押してください。")
                    for seg_idx, speaker, text, start, end in segments:
                        speaker_str = speaker or "UNKNOWN"
                        key_text = f"edit_{file_id}_{seg_idx}"
                        key_speaker = f"edit_speaker_{file_id}_{seg_idx}"
                        time_label = f"({format_time_mm_ss(start)}-{format_time_mm_ss(end)})"
                        with st.container():
                            col_speaker, col_time = st.columns([2, 1])
                            with col_speaker:
                                st.text_input(
                                    "話者",
                                    value=speaker_str,
                                    key=key_speaker,
                                    label_visibility="visible",
                                    placeholder="例: 山田、SPEAKER_00",
                                )
                            with col_time:
                                st.caption(time_label)
                            st.text_area(
                                "発言内容",
                                value=text,
                                key=key_text,
                                label_visibility="visible",
                                height=80,
                            )
                            st.divider()
                else:
                    # 表示モード（マウスオーバーでハイライト）
                    for seg_idx, speaker, text, start, end in segments:
                        speaker_str = speaker or "UNKNOWN"
                        time_range = f"{format_time_mm_ss(start)}-{format_time_mm_ss(end)}"
                        text_escaped = html.escape(text).replace("\n", "<br>")
                        seg_html = (
                            f'<div class="transcript-segment">'
                            f'<span style="color: #64748B; font-size: 0.9rem;">[{speaker_str}] ({time_range})</span> '
                            f'{text_escaped}</div>'
                        )
                        st.markdown(seg_html, unsafe_allow_html=True)
            else:
                st.warning("セグメントが見つかりませんでした")
        else:
            st.caption(f"ステータス: {status}")

        # プロジェクト移動モーダル（詳細画面から）
        if st.session_state.pending_move:
            mid, mname = st.session_state.pending_move
            move_to_project_dialog(mid, mname)
        # 削除確認モーダル（詳細画面から削除ボタンを押した場合）
        if st.session_state.pending_delete:
            del_file_id, del_filename = st.session_state.pending_delete
            confirm_delete_dialog(del_file_id, del_filename)
    else:
        # ファイルが削除された場合など
        st.session_state.selected_file_id = None
        st.session_state.selected_filename = None
        st.rerun()

# 一覧表示
elif not files:
    st.header("📋 登録ファイル一覧")
    st.info("まだファイルが登録されていません。サイドバーから音声ファイルをアップロードしてください。")
else:
    st.header("📋 登録ファイル一覧")

    # プロジェクトごとにグループ化（「すべて」表示時）
    current_project_name = None
    for row in files:
        file_id, filename, duration, status, processed_at, error_msg, project_id, project_name = row
        if selected_proj is None and project_name != current_project_name:
            current_project_name = project_name
            st.subheader(f"📁 {project_name}", divider="gray")
        # ファイル行: ファイル名（クリックで別ページへ）| 3点リーダーメニュー
        col_name, col_menu = st.columns([10, 1])
        with col_name:
            duration_str = f"{duration:.1f}秒" if duration else "N/A"
            label = f"{filename} — {status} ({duration_str})"
            if st.button(label, key=f"select_{file_id}", use_container_width=True):
                st.session_state.selected_file_id = file_id
                st.session_state.selected_filename = filename
                st.rerun()
        with col_menu:
            with st.popover("⋯", key=f"menu_{file_id}", help="メニュー"):
                if st.button("名前変更", key=f"menu_rename_{file_id}"):
                    st.session_state.pending_rename = (file_id, filename)
                    st.rerun()
                if st.button("プロジェクトに移動", key=f"menu_move_{file_id}"):
                    st.session_state.pending_move = (file_id, filename)
                    st.rerun()
                if st.button("削除", key=f"menu_delete_{file_id}"):
                    st.session_state.pending_delete = (file_id, filename)
                    st.rerun()

    # プロジェクト移動モーダル
    if st.session_state.pending_move:
        mid, mname = st.session_state.pending_move
        move_to_project_dialog(mid, mname)
    # 名前変更モーダル
    if st.session_state.pending_rename:
        rid, rname = st.session_state.pending_rename
        rename_file_dialog(rid, rname)
    # 削除確認モーダルを表示（ループ後に呼び出し）
    if st.session_state.pending_delete:
        del_file_id, del_filename = st.session_state.pending_delete
        confirm_delete_dialog(del_file_id, del_filename)

# CSS読み込み順を最後に（Streamlitデフォルトより後で確実に適用）
st.markdown("""
<style>
/* サイドバー内ボタン中央揃え・改行禁止 - 最終オーバーライド */
[data-testid="stSidebar"] [data-testid="column"] {
    flex: 1 1 auto !important;
    min-width: max-content !important;
    width: auto !important;
}
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
    display: flex !important;
    justify-content: center !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
}
[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] [data-testid="stAlert"] p,
[data-testid="stSidebar"] .stSpinner {
    white-space: nowrap !important;
    word-break: keep-all !important;
    width: max-content !important;
    margin: 0 auto !important;
}
</style>
""", unsafe_allow_html=True)

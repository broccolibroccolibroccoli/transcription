"""Streamlit: 検索パネルとヘッダー虫眼鏡（親ドキュメントへ注入）。"""
from __future__ import annotations

import html
import os

import streamlit as st

_LBL_CLOSE = "\u9589\u3058\u308b"
_LBL_PANEL_CLOSE = "\u30d1\u30cd\u30eb\u3092\u9589\u3058\u308b"
_LBL_KEYWORD = "\u30ad\u30fc\u30ef\u30fc\u30c9\u30fb\u8cea\u554f\uff08\u81ea\u7136\u6587\uff09"
_LBL_PLACEHOLDER = (
    "\u4f8b: \u30ab\u30b9\u30bf\u30de\u30fc\u30b8\u30e3\u30fc\u30cb\u30fc\u306b\u3064\u3044\u3066"
    "\u8a71\u3057\u3066\u3044\u308b\u7b87\u6240"
)


def has_embedding_for_search() -> bool:
    """TRANSCRIPTION_EMBEDDING_BACKEND に応じた認証が揃っているか。"""
    try:
        from embedding_providers import get_embedding_backend, has_embedding_credentials

        b = get_embedding_backend()
        if b == "openai":
            if has_embedding_credentials():
                return True
            try:
                return bool(str(st.secrets.get("OPENAI_API_KEY", "") or "").strip())
            except Exception:
                return False
        if b == "gemini":
            if has_embedding_credentials():
                return True
            try:
                return bool(
                    str(
                        st.secrets.get("GEMINI_API_KEY", "")
                        or st.secrets.get("GOOGLE_API_KEY", "")
                        or ""
                    ).strip()
                )
            except Exception:
                return False
        return has_embedding_credentials()
    except ImportError:
        return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def pg_sync_sqlite_file(file_id: int, db_path: str) -> None:
    try:
        from transcription_pg_search import sync_file_from_sqlite

        ok, err = sync_file_from_sqlite(file_id, db_path)
        if not ok and err and "\u672a\u8a2d\u5b9a" not in err and "\u30bb\u30b0\u30e1\u30f3\u30c8\u304c\u3042\u308a\u307e\u305b\u3093" not in err:
            pass
    except Exception:
        pass


def setup_main_search_layout():
    if not st.session_state.get("search_panel_open"):
        return st.container(), None
    if st.session_state.get("search_panel_minimized"):
        cols = st.columns([6.0, 0.48], gap="small")
    else:
        cols = st.columns([2.05, 1.0], gap="medium")
    return cols[0], cols[1]


def render_inline_search_toggle() -> None:
    """ヘッダー注入が効かない環境用。メイン右上に Streamlit ネイティブの検索トグル。"""
    row = st.columns([1, 0.09])
    with row[0]:
        st.empty()
    with row[1]:
        if st.button(
            "\U0001F50D",
            key="inline_pgai_search_toggle",
            help="\u691c\u7d22\u30d1\u30cd\u30eb\u3092\u958b\u304f",
            use_container_width=True,
        ):
            st.session_state.search_panel_open = True
            st.session_state.search_panel_minimized = False
            st.rerun()


def render_vector_search_drawer() -> None:
    st.markdown(
        '<div class="ts-search-drawer-inner">',
        unsafe_allow_html=True,
    )
    if st.session_state.get("search_panel_minimized"):
        st.caption("\u691c\u7d22\uff08\u6700\u5c0f\u5316\uff09")
        if st.button("\u00bb \u5e83\u3052\u308b", key="search_drawer_expand", use_container_width=True):
            st.session_state.search_panel_minimized = False
            st.rerun()
        if st.button(_LBL_CLOSE, key="search_drawer_close_mini", help=_LBL_PANEL_CLOSE):
            st.session_state.search_panel_open = False
            st.session_state.search_panel_minimized = False
            st.rerun()
        return

    st.markdown("##### \u691c\u7d22")
    st.caption(
        "\u5168\u30d5\u30a1\u30a4\u30eb\u306e\u6587\u5b57\u8d77\u3053\u3057\u30fb\u8a71\u8005\u4ed8\u304d\u767a\u8a00\u304b\u3089\u610f\u5473\u691c\u7d22\u3057\u307e\u3059\u3002"
    )
    hdr = st.columns([1, 0.14])
    with hdr[1]:
        if st.button("\u00ab", key="search_drawer_min", help="\u6700\u5c0f\u5316"):
            st.session_state.search_panel_minimized = True
            st.rerun()

    try:
        from transcription_pg_search import (
            count_transcript_vector_chunks,
            get_pg_dsn,
            search_transcripts,
        )
    except ImportError:
        st.error("transcription_pg_search \u3092\u8aad\u307f\u8fbc\u3081\u307e\u305b\u3093\u3002")
        return

    if not get_pg_dsn():
        st.warning(
            "PostgreSQL \u304c\u672a\u8a2d\u5b9a\u3067\u3059\u3002`.env` \u306b `TRANSCRIPTION_DATABASE_URL` \u3092\u8a2d\u5b9a\u3057\u3001"
            "`sql/vector_transcript_setup.sql` \u3092\u5b9f\u884c\u3057\u3066\u30c6\u30fc\u30d6\u30eb\u3092\u4f5c\u6210\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
        )
        if st.button(_LBL_PANEL_CLOSE, key="search_drawer_close_nopg"):
            st.session_state.search_panel_open = False
            st.session_state.search_panel_minimized = False
            st.rerun()
        return

    n_chunks = count_transcript_vector_chunks()
    if n_chunks is not None and n_chunks == 0:
        st.warning(
            "PostgreSQL \u306e\u30d9\u30af\u30c8\u30eb\u30c6\u30fc\u30d6\u30eb\u306b\u307e\u3060\u30c7\u30fc\u30bf\u304c\u3042\u308a\u307e\u305b\u3093\uff080 \u4ef6\uff09\u3002"
            "\u6587\u5b57\u8d77\u3053\u3057\u5b8c\u4e86\u5f8c\u306b\u540c\u671f\u3055\u308c\u307e\u3059\u3002\u65e2\u5b58\u30d5\u30a1\u30a4\u30eb\u306f\u8a73\u7d30\u3092\u958b\u3044\u3066\u4fdd\u5b58\u3059\u308b\u3068\u518d\u540c\u671f\u3055\u308c\u308b\u3053\u3068\u304c\u3042\u308a\u307e\u3059\u3002"
        )
    elif n_chunks is not None and n_chunks > 0:
        st.caption(f"\u30a4\u30f3\u30c7\u30c3\u30af\u30b9\u6e08\u307f\u30c1\u30e3\u30f3\u30af: {n_chunks} \u4ef6")

    if not has_embedding_for_search():
        try:
            from embedding_providers import get_embedding_backend

            b = get_embedding_backend()
        except ImportError:
            b = "openai"
        if b == "gemini":
            st.info(
                "\u691c\u7d22\u306e\u57cb\u3081\u8fbc\u307f\u306b `GEMINI_API_KEY` \u307e\u305f\u306f `GOOGLE_API_KEY` \u3092\u8a2d\u5b9a\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
            )
        elif b == "openai":
            st.info(
                "\u691c\u7d22\u306e\u57cb\u3081\u8fbc\u307f\u306b `OPENAI_API_KEY`\uff08\u307e\u305f\u306f Streamlit Secrets\uff09\u3092\u8a2d\u5b9a\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
            )
        else:
            st.info(
                "\u57cb\u3081\u8fbc\u307f\u8a2d\u5b9a\uff08TRANSCRIPTION_EMBEDDING_BACKEND\uff09\u3092\u78ba\u8a8d\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
            )

    with st.form("pg_vector_search_form", clear_on_submit=False):
        q = st.text_input(
            _LBL_KEYWORD,
            key="pgai_search_query_input",
            placeholder=_LBL_PLACEHOLDER,
        )
        submitted = st.form_submit_button("\u691c\u7d22", type="primary")
    if submitted:
        qv = (q or "").strip()
        if not qv:
            st.session_state.pgai_search_last_err = (
                "\u30ad\u30fc\u30ef\u30fc\u30c9\u3092\u5165\u529b\u3057\u3066\u304b\u3089\u691c\u7d22\u3092\u62bc\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
            )
            st.session_state.pgai_search_last_rows = []
            st.session_state.pgai_search_empty_result = False
        else:
            with st.spinner("\u691c\u7d22\u4e2d\u2026"):
                rows, err = search_transcripts(qv, limit=15)
            st.session_state.pgai_search_last_err = err
            st.session_state.pgai_search_last_rows = rows if not err else []
            st.session_state.pgai_search_empty_result = bool(not err and not rows)

    err = st.session_state.get("pgai_search_last_err")
    if err:
        st.error(err)

    if (
        not err
        and st.session_state.get("pgai_search_empty_result")
        and not (st.session_state.get("pgai_search_last_rows") or [])
    ):
        st.info(
            "\u8a72\u5f53\u3059\u308b\u30c1\u30e3\u30f3\u30af\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3067\u3057\u305f\u3002"
            "\u30ad\u30fc\u30ef\u30fc\u30c9\u3092\u5909\u3048\u308b\u304b\u3001\u5225\u306e\u8868\u73fe\u3067\u8a66\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
        )

    rows = st.session_state.get("pgai_search_last_rows") or []
    if rows:
        st.divider()
        st.caption(
            f"\u4e0a\u4f4d {len(rows)} \u4ef6\uff08\u8ddd\u96e2\u304c\u5c0f\u3055\u3044\u307b\u3069\u8fd1\u3044\uff09"
        )
        for i, r in enumerate(rows):
            fn = html.escape(str(r.get("filename") or ""))
            pn = html.escape(str(r.get("project_name") or ""))
            sp = html.escape(str(r.get("speaker") or ""))
            dist = r.get("distance")
            fi = int(r.get("file_id") or 0)
            body = html.escape(str(r.get("content") or ""))[:1200]
            dist_s = f" · distance `{dist:.4f}`" if isinstance(dist, (int, float)) else ""
            st.markdown(
                f"**{i + 1}.** `{fn}` · _{pn}_ · **{sp}** · file `{fi}`{dist_s}\n\n{body}",
                unsafe_allow_html=True,
            )
            if st.button(
                "\u3053\u306e\u30d5\u30a1\u30a4\u30eb\u3092\u958b\u304f",
                key=f"open_hit_{fi}_{i}",
            ):
                st.session_state.selected_file_id = fi
                st.session_state.selected_filename = str(r.get("filename") or "")
                st.session_state.search_panel_open = False
                st.session_state.search_panel_minimized = False
                st.rerun()
            st.divider()

    if st.button(_LBL_PANEL_CLOSE, key="search_drawer_close"):
        st.session_state.search_panel_open = False
        st.session_state.search_panel_minimized = False
        st.rerun()


PGAI_SEARCH_HEADER_HTML = r"""
<div></div>
<script>
(function() {
  function appLocation() {
    try {
      if (window.top && window.top.location && window.top.location.href) {
        return window.top.location;
      }
    } catch (e) {}
    try {
      if (window.parent && window.parent.location && window.parent.location.href) {
        return window.parent.location;
      }
    } catch (e2) {}
    return window.location;
  }
  function openSearchParam() {
    try {
      var loc = appLocation();
      var u = new URL(loc.href);
      u.searchParams.set('pgai_search', '1');
      loc.href = u.toString();
    } catch (e) {}
  }
  var doc = (window.parent && window.parent.document) ? window.parent.document : document;
  function placeBtn() {
    if (doc.getElementById('ts-pgai-search-trigger')) return;
    var header = doc.querySelector('[data-testid="stHeader"]');
    if (!header) return;
    var wrap = doc.createElement('div');
    wrap.id = 'ts-pgai-search-wrap';
    wrap.style.cssText = 'display:flex;align-items:center;margin-left:auto;order:999;';
    var btn = doc.createElement('button');
    btn.id = 'ts-pgai-search-trigger';
    btn.type = 'button';
    btn.setAttribute('title', '\u6587\u5b57\u8d77\u3053\u3057\u3092\u63a2\u3059\uff08\u691c\u7d22\uff09');
    btn.setAttribute('aria-label', '\u691c\u7d22');
    btn.textContent = String.fromCodePoint(0x1F50D);
    btn.style.cssText = 'border:1px solid #fbcfe8;border-radius:8px;padding:0.28rem 0.5rem;background:#fdf2f8;cursor:pointer;font-size:1.05rem;line-height:1;color:#334155;';
    btn.onmouseenter = function(){ btn.style.background='#fce7f3'; };
    btn.onmouseleave = function(){ btn.style.background='#fdf2f8'; };
    btn.onclick = function(e) {
      e.preventDefault();
      e.stopPropagation();
      openSearchParam();
    };
    wrap.appendChild(btn);
    var tb = header.querySelector('[data-testid="stToolbar"]');
    if (tb) {
      if (getComputedStyle(tb).display !== 'flex') {
        tb.style.display = 'flex';
        tb.style.alignItems = 'center';
        tb.style.flexWrap = 'nowrap';
      }
      tb.appendChild(wrap);
    } else {
      header.appendChild(wrap);
    }
  }
  placeBtn();
  setInterval(placeBtn, 900);
})();
</script>
"""

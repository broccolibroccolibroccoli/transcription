"""
summarize_transcript.py
=======================
文字起こし・話者分離の結果テキストを読み込み、
summary_rules.csv に記載したルールに基づいて Groq API で要約します。

Groq 無料枠の TPM 制限（6,000 tokens/分）に対応するため、
テキストをチャンク分割して要約し、最後に統合します。

  ステップ1: 文字起こしを複数チャンクに分割して各チャンクを要約
  ステップ2: 各チャンクの要約をまとめて最終要約を生成
  ステップ3: チャンク間に 60 秒超のウェイトを挿入して TPM 制限を回避
  ステップ4（複数チャンク時）: テーマ③を専用の追加リクエストで補完し、長文でも③が切れにくくする

短いテキスト（1チャンク以下）は従来どおり 1 回の API 呼び出しで要約します。

前提:
  - 既に生成した文字起こし・話者分離の結果が存在すること
  - summary_rules.csv が同ディレクトリに存在すること（任意で instruction_file で .md を参照）
  - 環境変数 GROQ_API_KEY が設定されていること
    （Groq Console → https://console.groq.com/keys で取得、クレジットカード不要）

インストール:
  pip install groq

使い方:
  python summarize_transcript.py \\
      --transcript transcription_with_speakers.txt \\
      --rules summary_rules.csv \\
      --output summary_output.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from groq import Groq

# 使用モデル
# 無料枠: 14,400 リクエスト/日、500,000 トークン/日、30 リクエスト/分
GROQ_MODEL = "llama-3.1-8b-instant"

# TPM制限対策
# 1リクエストあたりの最大入力文字数（日本語1文字 ≒ 1.5トークン換算で余裕を持たせた値）
CHUNK_MAX_CHARS = 1200

# チャンク間のウェイト秒数（TPMリセットを待つ）
CHUNK_WAIT_SECONDS = 62

# Groq 無料枠: 413 では「Requested 10117」等となり、入力に加え max_tokens 予約が合算される。
# 文字数をトークンの上界として扱い、1リクエストの合計を抑える。
GROQ_REQUEST_TOKEN_BUDGET = 5500
MIN_COMPLETION_TOKENS = 256

# 出力長（①②③や CSV の max_chars に対応するため、最終・単発は多めに要求。
# call_groq は room = BUDGET - len(prompt) で実際の max_tokens を自動縮小する）
MAX_COMPLETION_TOKENS_FINAL = 4096
MAX_COMPLETION_TOKENS_SINGLE_SHOT = 4096
MAX_COMPLETION_TOKENS_CHUNK = 1024
# 長時間音声で最終1回の出力が足りない場合、③だけ専用リクエストで補完する
MAX_COMPLETION_TOKENS_SECTION_THREE = 3072
SECTION_THREE_INPUT_MAX_CHARS = 4000

# プロンプト内の instruction（.md）の上限（長いと最終統合で必ず 413 になる）
MAX_INSTRUCTION_CHARS_SINGLE_SHOT = 8000
# summary_instruction.md 全文が入るよう余裕を持たせる（末尾の【出力ルール】欠落防止）
MAX_INSTRUCTION_CHARS_FINAL_MERGE = 9000


def _truncate_instruction_text(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[:max_chars] + "\n\n[...省略（API の長さ制限のため）...]"


def _prompt_fits_groq_budget(prompt: str, want_completion: int = MIN_COMPLETION_TOKENS) -> bool:
    """入力文字数 + 完了トークン予約が Groq の 1 リクエスト制限に収まるか（保守的）。"""
    return len(prompt) + want_completion <= GROQ_REQUEST_TOKEN_BUDGET


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_RULES_PATH = str(BASE_DIR / "summary_rules.csv")


def resolve_groq_api_key(explicit: Optional[str] = None) -> str:
    """環境変数、または明示指定から Groq API キーを返す。"""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    return os.environ.get("GROQ_API_KEY", "").strip()


# ------------------------------------------------------------------ #
# 1. CSV からルールを読み込む
# ------------------------------------------------------------------ #


def load_rules(csv_path: str) -> dict:
    """
    summary_rules.csv を読み込み、辞書形式に変換して返す。

    返り値の構造:
    {
        "output_format": "markdown",
        "max_chars": 800,
        "sections": ["概要", ...],
        "speaker_labels": {"SPEAKER_00": "Aさん", ...},
        "role_mapping": {"customer": "SPEAKER_00", "company": "SPEAKER_01"},
        "keywords": [],
        "exclude_filler": True,
        "output_lang": "ja",
        "instruction_body": "...",  # instruction_file から読み込んだ場合
    }
    """
    rules: Dict[str, Any] = {
        "output_format": "plain",
        "max_chars": 1000,
        "sections": [],
        "speaker_labels": {},
        "keywords": [],
        "exclude_filler": False,
        "output_lang": "ja",
        "instruction_body": "",
        "_instruction_relpath": "",
        "role_mapping": {},  # {"customer": "SPEAKER_00", "company": "SPEAKER_01"}
    }

    csv_dir = os.path.dirname(os.path.abspath(csv_path))

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rtype = (row.get("rule_type") or "").strip()
            param = (row.get("parameter") or "").strip()
            value = (row.get("value") or "").strip()

            if rtype == "output_format" and param == "format":
                rules["output_format"] = value

            elif rtype == "summary_length" and param == "max_chars":
                rules["max_chars"] = int(value)

            elif rtype == "section" and param == "name":
                rules["sections"].append(value)

            elif rtype == "speaker_label":
                rules["speaker_labels"][param] = value

            elif rtype == "role_mapping" and param in ("customer", "company") and value:
                rules["role_mapping"][param] = value

            elif rtype == "keyword_highlight" and param == "keyword":
                rules["keywords"].append(value)

            elif rtype == "exclude_filler" and param == "enabled":
                rules["exclude_filler"] = value.lower() == "true"

            elif rtype == "language" and param == "output_lang":
                rules["output_lang"] = value

            elif rtype == "instruction_file" and param == "path":
                rules["_instruction_relpath"] = value

    if rules.get("_instruction_relpath"):
        ipath = os.path.join(csv_dir, rules["_instruction_relpath"])
        if os.path.isfile(ipath):
            with open(ipath, encoding="utf-8") as inf:
                rules["instruction_body"] = inf.read().strip()
    del rules["_instruction_relpath"]

    return rules


# ------------------------------------------------------------------ #
# 2. 文字起こしテキストの前処理
# ------------------------------------------------------------------ #

FILLER_PATTERN = re.compile(
    r"(?<![a-zA-Z])(えー+|えーと|あのー?|まあ|うーん|そのー?|なんか|ちょっと待って|ですね+)(?![a-zA-Z])"
)


def preprocess_transcript(text: str, rules: dict) -> str:
    """
    話者ラベルの置換・フィラー除去などの前処理を行う。
    """
    for original, display in rules["speaker_labels"].items():
        text = text.replace(f"[{original}]", f"[{display}]")

    if rules["exclude_filler"]:
        text = FILLER_PATTERN.sub("", text)
        text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


# ------------------------------------------------------------------ #
# 3. プロンプト生成
# ------------------------------------------------------------------ #


def build_prompt(transcript: str, rules: dict) -> str:
    """
    ルールを反映した要約指示プロンプトを構築する。
    """
    sections_str = (
        "・".join(rules["sections"])
        if rules["sections"]
        else "概要・主な議題・決定事項・アクションアイテム"
    )
    keywords_str = "、".join(rules["keywords"]) if rules["keywords"] else "なし"
    fmt = (
        "Markdown（見出し・箇条書き）"
        if rules["output_format"] == "markdown"
        else "プレーンテキスト"
    )

    instruction = _truncate_instruction_text(
        rules.get("instruction_body") or "", MAX_INSTRUCTION_CHARS_SINGLE_SHOT
    )

    if instruction:
        return f"""{instruction}

---

## CSV で指定した追加条件
- 出力フォーマット: {fmt}
- 最大文字数: {rules['max_chars']}文字以内
- 補助セクション（参考）: {sections_str}
- 特に注目するキーワード: {keywords_str}（含まれる発言は可能な範囲で反映）
- 出力言語: {rules['output_lang']}

## 文字起こしデータ（ソース）
{transcript}
"""

    prompt = f"""以下は会議の文字起こしデータです。ルールに従って要約してください。

## 要約ルール
- 出力フォーマット: {fmt}
- 最大文字数: {rules['max_chars']}文字以内
- 必須セクション: {sections_str}
- 特に注目するキーワード: {keywords_str}（これらが含まれる発言は必ずどこかのセクションに反映する）
- 出力言語: {rules['output_lang']}
- 各話者の発言を公平に反映し、特定の話者に偏らないこと

## 文字起こしデータ
{transcript}
"""
    return prompt


# ------------------------------------------------------------------ #
# 4. テキストをチャンクに分割する
# ------------------------------------------------------------------ #


def split_into_chunks(text: str, max_chars: int = CHUNK_MAX_CHARS) -> List[str]:
    """
    テキストを発話行単位で max_chars 以下のチャンクに分割する。
    話者の発言途中では切らず、行単位でまとめる。
    """
    lines = text.splitlines()
    chunks: List[str] = []
    current_chunk_lines: List[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > max_chars and current_chunk_lines:
            chunks.append("\n".join(current_chunk_lines))
            current_chunk_lines = []
            current_len = 0
        current_chunk_lines.append(line)
        current_len += line_len

    if current_chunk_lines:
        chunks.append("\n".join(current_chunk_lines))

    return chunks


def _instruction_theme_block_for_chunks(rules: dict) -> str:
    """instruction 内の【抽出テーマ】ブロックを取り出し、チャンク抽出で①〜③を漏らさないようにする。"""
    body = (rules.get("instruction_body") or "").strip()
    anchor = "【抽出テーマ】"
    if anchor not in body:
        return ""
    i = body.index(anchor)
    j = body.find("\n【", i + len(anchor))
    if j == -1:
        snippet = body[i:]
    else:
        snippet = body[i:j]
    return snippet.strip()[:2000]


def build_chunk_prompt(chunk: str, chunk_index: int, total_chunks: int, rules: dict) -> str:
    """
    チャンクごとの中間要約プロンプトを生成する。
    """
    keywords_str = "、".join(rules["keywords"]) if rules["keywords"] else "なし"
    theme_block = _instruction_theme_block_for_chunks(rules)
    theme_section = ""
    if theme_block:
        theme_section = f"""
【抽出の観点（このパートにも該当があれば必ず拾う）】
{theme_block}

上記のテーマ①・②・③それぞれについて、このパートに該当する発言・示唆があれば箇条書きで書き出してください。
特に③（AIにどのような期待があるのか）に触れている表現は、他テーマにまとめず必ず③として別に記載してください。

【分類】各箇条書きは【顧客の自発的発言】【自社の誘導・同意】【自社からの提案】のいずれか**1つだけ**に分類し、同じ文を3つにコピーしない。行頭に [顧客] / [誘導同意] / [自社提案] のタグを付ける。
"""
    return f"""以下は会議の文字起こしの一部（{chunk_index + 1}/{total_chunks}）です。
{theme_section}
この部分に含まれる重要な発言・決定事項・TODO を箇条書きで抽出してください。
特に注目するキーワード: {keywords_str}

## 文字起こし（{chunk_index + 1}/{total_chunks}）
{chunk}
"""


def build_final_prompt(chunk_summaries: List[str], rules: dict) -> str:
    """
    各チャンクの中間要約を統合して最終要約を生成するプロンプトを生成する。
    instruction_file がある場合は先頭に付与する。
    """
    instruction = _truncate_instruction_text(
        (rules.get("instruction_body") or "").strip(), MAX_INSTRUCTION_CHARS_FINAL_MERGE
    )
    sections_str = (
        "・".join(rules["sections"])
        if rules["sections"]
        else "概要・主な議題・決定事項・アクションアイテム"
    )
    keywords_str = "、".join(rules["keywords"]) if rules["keywords"] else "なし"
    fmt = (
        "Markdown（見出し・箇条書き）"
        if rules["output_format"] == "markdown"
        else "プレーンテキスト"
    )
    combined = "\n\n---\n\n".join(
        [f"【パート{i + 1}の要点】\n{s}" for i, s in enumerate(chunk_summaries)]
    )

    rule_block = f"""## 要約ルール
- 出力フォーマット: {fmt}
- 最大文字数: {rules['max_chars']}文字以内
- 必須セクション: {sections_str}
- 特に注目するキーワード: {keywords_str}（含まれる場合は必ず反映すること）
- 出力言語: {rules['output_lang']}
- 各話者の発言を公平に反映し、特定の話者に偏らないこと"""

    if instruction:
        merge_must = (
            "\n\n【最終出力の必須事項】\n"
            "- テーマ①・②・③はすべて必ず出力し、見出し（例: ## ①… / ## ②… / ## ③…）を欠かさないこと。\n"
            "- 特に③「AIにどのような期待があるのか」は省略禁止。該当発言が少ない場合は、間接的な期待や示唆を③にまとめ、"
            "本当に一切ない場合のみ「（該当する発言は確認できなかった）」と明記すること。\n"
            "- 【顧客の自発的発言】【自社の誘導・同意】【自社からの提案】に**同一の箇条書きを重複して書かない**。"
            "各項目は定義に照らして**1カテゴリにだけ**配置。該当がないカテゴリは「（該当する発言は確認できなかった）」。\n"
            "- 出力が長くなる場合でも**必ず ## ③ まで書き切る**こと。①②を簡潔にし、**③を最後まで省略しない**。\n"
        )
        return f"""{instruction}
{merge_must}
---

{rule_block}

## 各パートの要点
{combined}
"""

    return f"""以下は会議の文字起こしを複数パートに分けて抽出した要点です。
これらを統合して、会議全体の最終要約を作成してください。

{rule_block}

## 各パートの要点
{combined}
"""


def _join_chunk_summaries_capped_for_section_three(
    summaries: List[str],
    max_total_chars: int = SECTION_THREE_INPUT_MAX_CHARS,
) -> str:
    """テーマ③専用プロンプト用にパート要点を連結。長いときは均等に省略して入力を抑える。"""
    if not summaries:
        return ""
    sep_len = len("\n\n---\n\n") * (len(summaries) - 1)
    overhead = 50 * len(summaries)
    budget = max(800, max_total_chars - sep_len - overhead)
    per = max(200, budget // len(summaries))
    parts: List[str] = []
    for i, s in enumerate(summaries):
        block = s.strip()
        if len(block) > per:
            block = block[:per] + "…（このパートは省略）"
        parts.append(f"【パート{i + 1}の要点】\n{block}")
    return "\n\n---\n\n".join(parts)


def build_section_three_followup_prompt(combined_capped: str, rules: dict) -> str:
    """
    テーマ③のみを詳述する軽量プロンプト（入力を抑え、出力枠を③に割り当てる）。
    """
    lang = rules.get("output_lang", "ja")
    return f"""あなたは議事録の要約者です。
以下は会議の各パートから抽出したメモです。ここから **テーマ③「AIにどのような期待があるのか」に該当する内容だけ** を統合し、
**完結した Markdown 1セクション**として出力してください（**途中で切らない**）。

## 出力形式（必須）
- 先頭の見出しは `## ③` で始め、タイトルに「AI」「期待」が分かるようにしてください。
- 次の3区分で箇条書き（メイン要約と同じ定義）:
  - ### 【顧客の自発的発言】
  - ### 【自社の誘導・同意】
  - ### 【自社からの提案】
- テーマ①②の内容は書かない。③のみ。
- 該当がない区分は「（該当する発言は確認できなかった）」と明記。

出力言語: {lang}

## 各パートの要点
{combined_capped}
"""


SECTION_THREE_BLOCK_RE = re.compile(r"(?ms)^##\s*③[^\n]*\n.*?(?=^##\s|\Z)")


def merge_section_three_into_full_summary(full: str, section_three_md: str) -> str:
    """全体要約の ③ ブロックを、専用リクエストの結果で置換（なければ末尾に追加）。"""
    t = (section_three_md or "").strip()
    if not t:
        return full
    if not re.match(r"^##\s*③", t):
        t = "## ③AIにどのような期待があるのか\n\n" + t
    if SECTION_THREE_BLOCK_RE.search(full):
        return SECTION_THREE_BLOCK_RE.sub(t.rstrip() + "\n\n", full, count=1)
    return full.rstrip() + "\n\n" + t + "\n"


def _parse_summary_markdown_to_rows(text: str) -> List[Tuple[str, str, str]]:
    """
    Groq が返す Markdown 要約を (theme, category, content) の行に分解する。
    見出し・箇条書きの揺れに多少耐性を持たせる。
    """
    rows: List[Tuple[str, str, str]] = []
    theme = ""
    category = ""
    inline_cat = re.compile(r"^\*\*(.+?)\*\*\s*:\s*(.+)$")
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## ") and not line.startswith("###"):
            theme = line[3:].strip()
            category = ""
            continue
        if line.startswith("### "):
            category = line[4:].strip()
            for s in ("**", "【", "】"):
                category = category.replace(s, "")
            category = category.strip()
            continue
        if line.startswith(("*", "-", "+")):
            body = line.lstrip("*+-").strip()
            m = inline_cat.match(body)
            if m:
                rows.append((theme, m.group(1).strip(), m.group(2).strip()))
                continue
            rows.append((theme, category, body))
        elif theme and not line.startswith("#"):
            rows.append((theme, category, line))
    return rows


def summary_markdown_to_csv(markdown_text: str) -> str:
    """
    Markdown 要約を UTF-8 の CSV 文字列に変換する（theme, category, content）。
    パースできない場合は 1 列 content に全文を入れる。
    """
    md = (markdown_text or "").strip()
    if not md:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["theme", "category", "content"])
        return buf.getvalue()

    parsed = _parse_summary_markdown_to_rows(md)
    if not parsed:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        w.writerow(["content"])
        w.writerow([md])
        return buf.getvalue()

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(["theme", "category", "content"])
    for t, c, x in parsed:
        w.writerow([t, c, x])
    return buf.getvalue()


# 要約の三大カテゴリ（instruction の【】と対応）
SUMMARY_CATEGORY_THREE = frozenset(
    {
        "顧客の自発的発言",
        "自社の誘導・同意",
        "自社からの提案",
    }
)


def normalize_section_title(text: str) -> str:
    """【】・箇条書き記号・太字を除いたカテゴリ見出し文字列。"""
    t = (text or "").strip()
    t = re.sub(r"^[\*\-\+]\s*", "", t)
    t = t.strip()
    if t.startswith("【") and t.endswith("】"):
        t = t[1:-1]
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    return t.strip()


def is_category_header_content_line(x: str) -> bool:
    return normalize_section_title(x) in SUMMARY_CATEGORY_THREE


def fix_category_markdown_bullets(md: str) -> str:
    """三大カテゴリが * の箇条書きになっている行を ### 見出しに変える。"""
    out: List[str] = []
    for line in (md or "").splitlines():
        s = line.strip()
        matched = False
        for label in SUMMARY_CATEGORY_THREE:
            if s in (
                f"* {label}",
                f"- {label}",
                f"+ {label}",
                f"* 【{label}】",
                f"- 【{label}】",
                f"+ 【{label}】",
                f"* **{label}**",
                f"- **{label}**",
                f"+ **{label}**",
            ):
                out.append(f"### {label}")
                matched = True
                break
        if not matched:
            out.append(line)
    return "\n".join(out)


def apply_summary_role_tags(text: str, rules: dict) -> str:
    """
    （顧客）（自社）を、role_mapping + speaker_labels で解決した表示に置き換える。
    role_mapping に customer / company へ割り当てる話者 ID（例: SPEAKER_00）を書き、
    speaker_label で表示名を上書きできる。未設定の speaker_label は ID のまま。
    """
    if not (text and str(text).strip()):
        return text or ""
    rm = rules.get("role_mapping") or {}
    sl = rules.get("speaker_labels") or {}

    def resolve(side: str) -> Optional[str]:
        sid = (rm.get(side) or "").strip()
        if not sid:
            return None
        return sl.get(sid, sid)

    out = text
    c = resolve("customer")
    if c:
        out = out.replace("（顧客）", f"（{c}）")
        out = out.replace("(顧客)", f"({c})")
    co = resolve("company")
    if co:
        out = out.replace("（自社）", f"（{co}）")
        out = out.replace("(自社)", f"({co})")
    return out


def postprocess_summary_markdown(md: str, rules: dict) -> str:
    """カテゴリ見出し整形 → 話者タグ置換の順。"""
    md = fix_category_markdown_bullets(md or "")
    md = apply_summary_role_tags(md, rules)
    return md


def dataframe_summary_to_markdown(df: Any) -> str:
    """theme/category/content の DataFrame を Markdown に整形（カテゴリ行に * を付けない）。"""
    import pandas as pd

    def s(v) -> str:
        if pd.isna(v):
            return ""
        return str(v).strip()

    def norm_cat(v: str) -> str:
        return normalize_section_title(v) if v else ""

    def heading_display(c: str) -> str:
        t = norm_cat(c)
        return t if t else (c or "").strip()

    current_theme = None
    current_cat_norm: Optional[str] = None
    parts: list[str] = []
    for _, row in df.iterrows():
        t = s(row.get("theme", ""))
        c = s(row.get("category", ""))
        x = s(row.get("content", ""))
        if not x and not t and not c:
            continue
        if t != current_theme:
            current_theme = t
            current_cat_norm = None
            if t:
                parts.append(f"## {t}\n")
        nc = norm_cat(c)
        if c and nc != current_cat_norm:
            current_cat_norm = nc
            parts.append(f"### {heading_display(c)}\n")
        if x:
            if is_category_header_content_line(x):
                clean = normalize_section_title(x)
                if nc == clean:
                    continue
                if clean != current_cat_norm:
                    current_cat_norm = clean
                    parts.append(f"### {clean}\n")
                continue
            parts.append(f"* {x}\n")
    return "".join(parts) if parts else "（空）"


def _merge_intermediate_batch(
    batch: List[str],
    rules: dict,
    client: Groq,
) -> str:
    """複数の中間要約を1つに圧縮（最終プロンプトの入力過多を防ぐ）。"""
    if not batch:
        return ""
    if len(batch) == 1:
        s = batch[0]
        combined = f"【断片1】\n{s}"
    else:
        combined = "\n\n---\n\n".join(
            [f"【断片{i + 1}】\n{s}" for i, s in enumerate(batch)]
        )
    lang = rules.get("output_lang", "ja")
    theme_keep = ""
    if _instruction_theme_block_for_chunks(rules):
        theme_keep = (
            "テーマ①・②・③のうち、どれかに属する要点は統合時に削除しないこと。"
            "特に③（AIへの期待）に関する箇条書きは必ず残すこと。"
            "【顧客の自発的発言】【自社の誘導・同意】【自社からの提案】は定義どおりに分け、"
            "同じ文を3カテゴリに複製しないこと。\n\n"
        )
    prompt = f"""以下は会議の文字起こしを要約した断片です。重複を除き、時系列・論点が追えるように1つのまとまった要約に統合してください。
出力言語: {lang}
{theme_keep}箇条書き可。長さは2000文字以内を目安に。

{combined}
"""
    if not _prompt_fits_groq_budget(prompt, want_completion=MIN_COMPLETION_TOKENS):
        if len(batch) == 1:
            s = batch[0]
            if len(s) <= 500:
                return call_groq(client, prompt, max_tokens=1024)
            mid = max(1, len(s) // 2)
            left = _merge_intermediate_batch([s[:mid]], rules, client)
            time.sleep(CHUNK_WAIT_SECONDS)
            right = _merge_intermediate_batch([s[mid:]], rules, client)
            time.sleep(CHUNK_WAIT_SECONDS)
            return _merge_intermediate_batch([left, right], rules, client)
        mid = max(1, len(batch) // 2)
        left = _merge_intermediate_batch(batch[:mid], rules, client)
        time.sleep(CHUNK_WAIT_SECONDS)
        right = _merge_intermediate_batch(batch[mid:], rules, client)
        time.sleep(CHUNK_WAIT_SECONDS)
        return _merge_intermediate_batch([left, right], rules, client)
    return call_groq(client, prompt, max_tokens=1024)


def _reduce_summaries_for_final_merge(
    summaries: List[str],
    rules: dict,
    client: Groq,
    *,
    verbose: bool = False,
) -> List[str]:
    """
    build_final_prompt が TPM 上限を超えないよう、中間要約を段階的に統合する。
    """
    guard = 0
    while (
        not _prompt_fits_groq_budget(
            build_final_prompt(summaries, rules), want_completion=MIN_COMPLETION_TOKENS
        )
        and guard < 200
    ):
        guard += 1
        if len(summaries) == 1:
            s = summaries[0]
            if _prompt_fits_groq_budget(
                build_final_prompt(summaries, rules), want_completion=MIN_COMPLETION_TOKENS
            ):
                break
            if len(s) <= 400:
                raise RuntimeError(
                    "要約の入力が Groq の TPM 上限を超えています。"
                    "summary_instruction.md が長すぎる可能性があります。内容を短くするか、"
                    "summary_rules.csv の instruction_file を外してください。"
                )
            mid = max(1, len(s) // 2)
            summaries = [s[:mid], s[mid:]]
            continue

        next_level: List[str] = []
        for i in range(0, len(summaries), 2):
            pair = summaries[i : i + 2]
            if len(pair) == 1:
                next_level.append(pair[0])
            else:
                if verbose:
                    print(f"   中間要約を統合中（{guard} 段目）…")
                merged = _merge_intermediate_batch(pair, rules, client)
                next_level.append(merged)
                time.sleep(CHUNK_WAIT_SECONDS)
        summaries = next_level

    return summaries


# ------------------------------------------------------------------ #
# 5. Groq API で要約（チャンク分割・TPM制限対応）
# ------------------------------------------------------------------ #


def call_groq(client: Groq, prompt: str, max_tokens: int = 1024) -> str:
    """
    Groq API を1回呼び出す。
    無料枠では「入力」と max_tokens 予約が合算され 413 になるため、
    プロンプト長に応じて max_tokens を自動で抑える。
    """
    plen = len(prompt)
    if plen + MIN_COMPLETION_TOKENS > GROQ_REQUEST_TOKEN_BUDGET:
        raise RuntimeError(
            f"プロンプトが長すぎます（{plen} 文字）。"
            "summary_instruction.md を短くするか、文字起こしを分割してください。"
        )
    room = GROQ_REQUEST_TOKEN_BUDGET - plen
    actual_max = min(max_tokens, room)
    chat_completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=actual_max,
        temperature=0.3,
    )
    choice = chat_completion.choices[0]
    content = choice.message.content
    if content is None:
        return ""
    return content


def summarize_with_groq(
    transcript: str,
    rules: dict,
    api_key: Optional[str] = None,
    *,
    verbose: bool = False,
) -> str:
    """
    Groq API で要約を返す。

    - 1チャンクに収まる場合: build_prompt で 1 回のみ呼び出し
    - 複数チャンク: 各チャンクを抽出 → 統合（チャンク間は TPM 対策で待機）

    transcript は preprocess 済みの文字列を想定する。
    """
    key = resolve_groq_api_key(api_key)
    if not key:
        raise EnvironmentError(
            "環境変数 GROQ_API_KEY が設定されていません。\n"
            "Groq Console ( https://console.groq.com/keys ) で\n"
            "APIキーを取得し（クレジットカード不要）、.env または環境変数に設定してください:\n"
            "  GROQ_API_KEY=your-key-here"
        )

    client = Groq(api_key=key)
    chunks = split_into_chunks(transcript)
    if not chunks:
        return ""

    total = len(chunks)
    if verbose:
        print(f"   テキストを {total} チャンクに分割しました（各最大 {CHUNK_MAX_CHARS} 文字）")

    if total == 1:
        prompt = build_prompt(transcript, rules)
        if not _prompt_fits_groq_budget(prompt, want_completion=MIN_COMPLETION_TOKENS):
            raise RuntimeError(
                "1回の要約リクエストが Groq の上限を超えています。"
                "summary_instruction.md を短くするか、文字起こしを分割してください。"
            )
        return call_groq(client, prompt, max_tokens=MAX_COMPLETION_TOKENS_SINGLE_SHOT)

    chunk_summaries: List[str] = []
    for i, chunk in enumerate(chunks):
        if verbose:
            print(f"   チャンク {i + 1}/{total} を要約中...")
        prompt = build_chunk_prompt(chunk, i, total, rules)
        summary = call_groq(client, prompt, max_tokens=MAX_COMPLETION_TOKENS_CHUNK)
        chunk_summaries.append(summary)

        if i < total - 1:
            if verbose:
                print(f"   TPM制限のため {CHUNK_WAIT_SECONDS} 秒待機中...")
            time.sleep(CHUNK_WAIT_SECONDS)

    if verbose:
        print("   全チャンクの要約を統合中...")
        print(f"   TPM制限のため {CHUNK_WAIT_SECONDS} 秒待機中...")
    time.sleep(CHUNK_WAIT_SECONDS)

    chunk_summaries = _reduce_summaries_for_final_merge(
        chunk_summaries, rules, client, verbose=verbose
    )

    fp = build_final_prompt(chunk_summaries, rules)
    if not _prompt_fits_groq_budget(fp, want_completion=MIN_COMPLETION_TOKENS):
        raise RuntimeError(
            "要約の最終統合時の入力が Groq の上限を超えています。"
            "summary_instruction.md を短くするか、summary_rules.csv の instruction_file を外してください。"
        )

    full_summary = call_groq(client, fp, max_tokens=MAX_COMPLETION_TOKENS_FINAL)

    # 長文では最終1回の出力枠が足りず③が切れることがあるため、③だけ専用リクエストで補完して差し替え
    s3_prompt: Optional[str] = None
    for cap in (
        SECTION_THREE_INPUT_MAX_CHARS,
        3200,
        2400,
        1600,
        1200,
        800,
    ):
        combined_s3 = _join_chunk_summaries_capped_for_section_three(
            chunk_summaries, max_total_chars=cap
        )
        candidate = build_section_three_followup_prompt(combined_s3, rules)
        if _prompt_fits_groq_budget(candidate, want_completion=MIN_COMPLETION_TOKENS):
            s3_prompt = candidate
            break

    if s3_prompt is not None:
        if verbose:
            print("   テーマ③を専用リクエストで補完しています…")
        time.sleep(CHUNK_WAIT_SECONDS)
        section_three = call_groq(
            client, s3_prompt, max_tokens=MAX_COMPLETION_TOKENS_SECTION_THREE
        )
        full_summary = merge_section_three_into_full_summary(full_summary, section_three)

    return full_summary


# ------------------------------------------------------------------ #
# セグメント行からテキスト化（アプリ連携用）
# ------------------------------------------------------------------ #


def segments_rows_to_transcript(
    rows: Sequence[Tuple[Any, ...]],
    apply_boundary_fix: bool = False,
) -> str:
    """
    get_segments_by_file_id と同形式の行から [話者] 本文 形式の1テキストを作る。

    rows: (segment_index, speaker, text, start_time, end_time)
    """
    if apply_boundary_fix:
        from segment_postprocess import fix_speaker_boundary_rows

        rows = fix_speaker_boundary_rows(list(rows))
    lines: List[str] = []
    for _seg_idx, speaker, text, _start, _end in rows:
        sp = speaker or "UNKNOWN"
        lines.append(f"[{sp}] {text}")
    return "\n".join(lines)


def summarize_transcript_text(
    transcript_raw: str,
    rules_path: str = DEFAULT_RULES_PATH,
    api_key: Optional[str] = None,
) -> str:
    """
    前処理・Groq 呼び出しまで一括実行。アプリから利用。
    戻り値は CSV 文字列（UTF-8）。
    """
    rules = load_rules(rules_path)
    transcript = preprocess_transcript(transcript_raw, rules)
    md = summarize_with_groq(transcript, rules, api_key=api_key)
    md = postprocess_summary_markdown(md, rules)
    return summary_markdown_to_csv(md)


# ------------------------------------------------------------------ #
# 6. メイン処理
# ------------------------------------------------------------------ #


def main() -> None:
    parser = argparse.ArgumentParser(
        description="文字起こし結果をルールに基づいて要約します（Groq Llama 3.1 8B / チャンク分割対応）"
    )
    parser.add_argument(
        "--transcript",
        default="transcription_with_speakers.txt",
        help="文字起こしテキストファイルのパス",
    )
    parser.add_argument(
        "--rules",
        default="summary_rules.csv",
        help="要約ルールCSVファイルのパス",
    )
    parser.add_argument(
        "--output",
        default="summary_output.csv",
        help="要約結果の出力ファイルパス（CSV）",
    )
    args = parser.parse_args()

    print(f"📋 ルールを読み込み中: {args.rules}")
    rules = load_rules(args.rules)
    print(f"   セクション: {rules['sections']}")
    print(f"   話者ラベル: {rules['speaker_labels']}")
    print(f"   話者ロール: {rules.get('role_mapping')}")
    print(f"   フィラー除去: {rules['exclude_filler']}")
    if rules.get("instruction_body"):
        print(f"   指示ファイル: 読み込み済み（{len(rules['instruction_body'])} 文字）")

    print(f"\n📄 文字起こしを読み込み中: {args.transcript}")
    with open(args.transcript, encoding="utf-8") as f:
        raw_transcript = f.read()

    transcript = preprocess_transcript(raw_transcript, rules)
    print(f"   文字数（前処理後）: {len(transcript)}")

    print(f"\n🤖 Groq ({GROQ_MODEL}) で要約中...")
    md_summary = summarize_with_groq(transcript, rules, verbose=True)
    md_summary = postprocess_summary_markdown(md_summary, rules)
    csv_summary = summary_markdown_to_csv(md_summary)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(csv_summary)
    print(f"\n✅ 要約が完了しました → {args.output}")
    print("\n--- 要約プレビュー（先頭300文字）---")
    print(csv_summary[:300])


if __name__ == "__main__":
    main()

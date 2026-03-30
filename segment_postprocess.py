"""
文字起こしセグメントの後処理（話者境界での語尾混入の補正など）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

Row = Tuple[Any, Any, str, Any, Any]


def is_incomplete(text: str) -> bool:
    """直前セグメントが話者境界で途中までしか含まれていない疑いがあるか判定する。"""
    if not text:
        return False
    incomplete_endings = [
        "ていき",
        "でいき",
        "していき",
        "ていて",
        "てい",
        "掘り下げ",
        "解剖し",
    ]
    return any(text.endswith(e) for e in incomplete_endings)


def fix_speaker_boundary(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    話者切り替わりで次セグメント先頭に付いた語尾・助詞を前セグメントに戻す。

    segments は少なくともキー 'text' を持つ dict のリスト。

    語尾の付け替えは、直前セグメントの末尾が is_incomplete に該当するときだけ行う
    （パターン拡大に伴う誤補正を抑える）。
    """
    # 長いパターンを先に試す（「ですね」が単独の「で」に誤マッチしないようにする）
    boundary_patterns = [
        r"^(んです|ました|ません|ますね|ですね|ですよ)",  # 複合語尾
        r"^(ます|です|ない|たい|てる|てい)",  # 語尾
        r"^(ね|よ|な|か|が|は|を|も|で|に|と|の)",  # 1文字の助詞・語尾
    ]
    result: List[Dict[str, Any]] = []
    for i, seg in enumerate(segments):
        if i == 0:
            result.append(seg)
            continue
        text = seg.get("text") or ""
        prev_text = result[-1].get("text") or ""
        if is_incomplete(prev_text):
            for pattern in boundary_patterns:
                m = re.match(pattern, text)
                if m and len(text) > len(m.group()):
                    result[-1]["text"] = prev_text + m.group()
                    seg = dict(seg)
                    seg["text"] = text[len(m.group()) :]
                    break
        result.append(seg)
    return result


def fix_speaker_boundary_rows(rows: List[Row]) -> List[Row]:
    """
    (segment_index, speaker, text, start_time, end_time) のタプル列に境界補正を適用する。
    CSV 出力直前や DB 保存前に利用する。
    """
    if not rows:
        return []
    segments = [
        {
            "segment_index": r[0],
            "speaker": r[1],
            "text": r[2] or "",
            "start": r[3],
            "end": r[4],
        }
        for r in rows
    ]
    fixed = fix_speaker_boundary(segments)
    return [
        (d["segment_index"], d["speaker"], d["text"], d["start"], d["end"])
        for d in fixed
    ]

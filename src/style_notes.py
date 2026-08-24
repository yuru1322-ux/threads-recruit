"""ユーザーの手動修正差分を style-notes.md に蓄積する.

生成直後の本文（generated_body/generated_reply）と、/posted 時点の本文（body/reply）
を比較し、差分があれば data/style_edits.jsonl に追記したうえで、
style-notes.md の自動セクション（AUTO-EDITS マーカーの間）を直近 MAX_ENTRIES 件で
書き直す。手書きの分析部分（マーカーより上）には触れない。
"""
from __future__ import annotations

import json
from datetime import date, datetime

from . import config

MAX_ENTRIES = 15
AUTO_SECTION_START = "<!-- AUTO-EDITS:START -->"
AUTO_SECTION_END = "<!-- AUTO-EDITS:END -->"


def record_edit(
    *,
    post_date: date,
    before_body: str,
    after_body: str,
    before_reply: str,
    after_reply: str,
) -> bool:
    """差分があれば記録して True を返す。差分がなければ何もせず False を返す."""
    if before_body == after_body and before_reply == after_reply:
        return False
    entry = {
        "date": post_date.isoformat(),
        "recorded_at": datetime.now(config.TZ).isoformat(),
        "before_body": before_body,
        "after_body": after_body,
        "before_reply": before_reply,
        "after_reply": after_reply,
    }
    _append_jsonl(entry)
    _refresh_notes_auto_section()
    return True


def _append_jsonl(entry: dict) -> None:
    config.STYLE_EDITS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with config.STYLE_EDITS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _load_entries() -> list[dict]:
    if not config.STYLE_EDITS_FILE.exists():
        return []
    out = []
    for line in config.STYLE_EDITS_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _render_auto_section() -> str:
    entries = _load_entries()[-MAX_ENTRIES:]
    lines = [f"## 自動記録: 直近の手動修正差分（最新{len(entries)}件・生成 → 投稿時点）", ""]
    if not entries:
        lines.append("（まだ記録がありません。/posted 時に生成直後との差分があれば、ここに自動で追記されます）")
    else:
        for e in reversed(entries):
            lines.append(f"### {e['date']}")
            if e["before_body"] != e["after_body"]:
                lines.append(f"- 本文（生成）: {e['before_body']!r}")
                lines.append(f"- 本文（修正後）: {e['after_body']!r}")
            if e["before_reply"] != e["after_reply"]:
                lines.append(f"- 返信（生成）: {e['before_reply']!r}")
                lines.append(f"- 返信（修正後）: {e['after_reply']!r}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _refresh_notes_auto_section() -> None:
    auto_block = f"{AUTO_SECTION_START}\n{_render_auto_section()}{AUTO_SECTION_END}\n"
    path = config.STYLE_NOTES_FILE
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if AUTO_SECTION_START in text and AUTO_SECTION_END in text:
        pre = text.split(AUTO_SECTION_START)[0]
        post = text.split(AUTO_SECTION_END)[1]
        text = pre.rstrip() + "\n\n" + auto_block + post.lstrip("\n")
    else:
        text = text.rstrip("\n") + "\n\n" + auto_block
    path.write_text(text, encoding="utf-8")

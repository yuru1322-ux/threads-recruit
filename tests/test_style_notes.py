"""style_notes（手動修正差分の自動蓄積）のテスト:
    python -m pytest tests/test_style_notes.py -q
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, style_notes  # noqa: E402


def _with_isolated_notes(fn):
    orig_notes = config.STYLE_NOTES_FILE
    orig_edits = config.STYLE_EDITS_FILE
    with tempfile.TemporaryDirectory() as d:
        config.STYLE_NOTES_FILE = Path(d) / "style-notes.md"
        config.STYLE_EDITS_FILE = Path(d) / "style_edits.jsonl"
        try:
            fn()
        finally:
            config.STYLE_NOTES_FILE = orig_notes
            config.STYLE_EDITS_FILE = orig_edits


def test_record_edit_noop_when_unchanged():
    def run():
        changed = style_notes.record_edit(
            post_date=date(2026, 8, 24),
            before_body="本文", after_body="本文",
            before_reply="返信", after_reply="返信",
        )
        assert changed is False
        assert not config.STYLE_EDITS_FILE.exists()

    _with_isolated_notes(run)
    print("✓ 差分がなければ記録しない")


def test_record_edit_appends_jsonl_and_updates_notes():
    def run():
        changed = style_notes.record_edit(
            post_date=date(2026, 8, 24),
            before_body="生成された本文", after_body="修正後の本文",
            before_reply="返信", after_reply="返信",
        )
        assert changed is True
        lines = config.STYLE_EDITS_FILE.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1

        notes = config.STYLE_NOTES_FILE.read_text(encoding="utf-8")
        assert "生成された本文" in notes
        assert "修正後の本文" in notes
        assert style_notes.AUTO_SECTION_START in notes
        assert style_notes.AUTO_SECTION_END in notes

    _with_isolated_notes(run)
    print("✓ 差分がある場合はjsonlに追記し、style-notes.mdの自動セクションを更新する")


def test_record_edit_preserves_handwritten_content_above_marker():
    def run():
        config.STYLE_NOTES_FILE.write_text("# 手書きの分析\n\nここは触らないでほしい。\n", encoding="utf-8")
        style_notes.record_edit(
            post_date=date(2026, 8, 24),
            before_body="A", after_body="B",
            before_reply="C", after_reply="C",
        )
        notes = config.STYLE_NOTES_FILE.read_text(encoding="utf-8")
        assert "ここは触らないでほしい。" in notes

    _with_isolated_notes(run)
    print("✓ 自動セクションの追記時、手書き部分は保持される")


def test_record_edit_caps_at_max_entries():
    def run():
        for i in range(style_notes.MAX_ENTRIES + 5):
            style_notes.record_edit(
                post_date=date(2026, 1, 1),
                before_body=f"before{i}", after_body=f"after{i}",
                before_reply="x", after_reply="x",
            )
        notes = config.STYLE_NOTES_FILE.read_text(encoding="utf-8")
        assert "before0" not in notes  # 古いものは切り捨てられる
        assert f"before{style_notes.MAX_ENTRIES + 4}" in notes  # 最新は残る

    _with_isolated_notes(run)
    print(f"✓ 自動セクションは直近{style_notes.MAX_ENTRIES}件までに制限される")


if __name__ == "__main__":
    for fn in [
        test_record_edit_noop_when_unchanged,
        test_record_edit_appends_jsonl_and_updates_notes,
        test_record_edit_preserves_handwritten_content_above_marker,
        test_record_edit_caps_at_max_entries,
    ]:
        fn()
    print("\nすべてのテストに合格しました。")

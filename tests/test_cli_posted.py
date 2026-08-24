"""cli posted（手動投稿の完了記録）のテスト:
    python -m pytest tests/test_cli_posted.py -q
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import cli, config, drafts, history, style_notes  # noqa: E402


def _with_isolated_storage(fn):
    orig = {
        "DRAFT_DIR": config.DRAFT_DIR,
        "HISTORY_FILE": config.HISTORY_FILE,
        "STYLE_NOTES_FILE": config.STYLE_NOTES_FILE,
        "STYLE_EDITS_FILE": config.STYLE_EDITS_FILE,
    }
    with tempfile.TemporaryDirectory() as d:
        config.DRAFT_DIR = Path(d) / "drafts"
        config.DRAFT_DIR.mkdir()
        config.HISTORY_FILE = Path(d) / "history.json"
        config.STYLE_NOTES_FILE = Path(d) / "style-notes.md"
        config.STYLE_EDITS_FILE = Path(d) / "style_edits.jsonl"
        try:
            fn()
        finally:
            for k, v in orig.items():
                setattr(config, k, v)


def _make_draft(target, *, edited=False):
    generated = {
        "theme_key": "salary", "theme_name": "給与・収入系",
        "angle_id": "bonus", "angle_label": "賞与ありという業界内での希少性",
        "hook": "実は…", "body": "実は…\n\n生成された本文です。",
        "reply": "生成された返信です。", "summary": "テスト用の要約", "warnings": [],
    }
    draft = drafts.new_draft(target, "月", generated)
    if edited:
        draft["body"] = "実は…\n\n手直しした本文です！"
    drafts.save(draft)
    return draft


def test_posted_marks_status_and_records_history():
    def run():
        target = date(2026, 8, 24)
        _make_draft(target)
        code = cli.cmd_posted(SimpleNamespace(date=target.isoformat()))
        assert code == 0

        saved = drafts.load(target)
        assert saved["status"] == drafts.STATUS_POSTED
        assert saved["posted_at"] is not None

        used = history.used_angles("salary", date(2026, 8, 25))
        assert "bonus" in used

    _with_isolated_storage(run)
    print("✓ posted: statusがpostedになり、historyに記録される")


def test_posted_records_style_diff_when_edited():
    def run():
        target = date(2026, 8, 24)
        _make_draft(target, edited=True)
        cli.cmd_posted(SimpleNamespace(date=target.isoformat()))

        assert config.STYLE_EDITS_FILE.exists()
        notes = config.STYLE_NOTES_FILE.read_text(encoding="utf-8")
        assert "手直しした本文です" in notes

    _with_isolated_storage(run)
    print("✓ posted: 生成時と本文が違えば style-notes.md に差分が記録される")


def test_posted_no_diff_recorded_when_unedited():
    def run():
        target = date(2026, 8, 24)
        _make_draft(target, edited=False)
        cli.cmd_posted(SimpleNamespace(date=target.isoformat()))
        assert not config.STYLE_EDITS_FILE.exists()

    _with_isolated_storage(run)
    print("✓ posted: 手直しがなければ style_edits は記録されない")


def test_posted_is_idempotent():
    def run():
        target = date(2026, 8, 24)
        _make_draft(target)
        cli.cmd_posted(SimpleNamespace(date=target.isoformat()))
        history_after_first = config.HISTORY_FILE.read_text(encoding="utf-8")
        code = cli.cmd_posted(SimpleNamespace(date=target.isoformat()))
        assert code == 0
        history_after_second = config.HISTORY_FILE.read_text(encoding="utf-8")
        assert history_after_first == history_after_second

    _with_isolated_storage(run)
    print("✓ posted: 2回コメントしてもhistoryが二重記録されない")


def test_posted_missing_draft_returns_error():
    def run():
        code = cli.cmd_posted(SimpleNamespace(date="2026-08-24"))
        assert code == 1

    _with_isolated_storage(run)
    print("✓ posted: 下書きがない日はエラーを返す")


if __name__ == "__main__":
    for fn in [
        test_posted_marks_status_and_records_history,
        test_posted_records_style_diff_when_edited,
        test_posted_no_diff_recorded_when_unedited,
        test_posted_is_idempotent,
        test_posted_missing_draft_returns_error,
    ]:
        fn()
    print("\nすべてのテストに合格しました。")

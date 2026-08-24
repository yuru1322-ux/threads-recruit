"""週次まとめ生成（generate_week）のテスト:
    python -m pytest tests/test_weekly.py -q
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, weekly  # noqa: E402


class FakeMessage:
    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]


class FakeClient:
    """呼ばれた回数を summary/hook に埋め込むだけの、常に妥当なJSONを返すモック."""

    def __init__(self):
        self.calls = 0
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        payload = (
            '{"hook": "フック%d", "body": "フック%d\\n\\n本文%d", '
            '"reply": "返信%d。DMどうぞ。", "summary": "要約%d"}'
        ) % (self.calls, self.calls, self.calls, self.calls, self.calls)
        return FakeMessage(payload)


def _with_isolated_storage(fn):
    orig_draft_dir = config.DRAFT_DIR
    orig_history_file = config.HISTORY_FILE
    with tempfile.TemporaryDirectory() as d:
        config.DRAFT_DIR = Path(d) / "drafts"
        config.DRAFT_DIR.mkdir()
        config.HISTORY_FILE = Path(d) / "history.json"
        try:
            fn()
        finally:
            config.DRAFT_DIR = orig_draft_dir
            config.HISTORY_FILE = orig_history_file


def test_generate_week_creates_six_days_mon_to_sat():
    def run():
        monday = date(2026, 8, 24)
        results = weekly.generate_week(monday, client=FakeClient())
        assert len(results) == 6
        assert [d["date"] for d in results] == [
            "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28", "2026-08-29",
        ]
        assert [d["weekday"] for d in results] == ["月", "火", "水", "木", "金", "土"]

    _with_isolated_storage(run)
    print("✓ 週次生成: 月〜土の6日分が作られる")


def test_generate_week_avoids_duplicate_angles_within_week():
    def run():
        monday = date(2026, 8, 24)
        results = weekly.generate_week(monday, client=FakeClient())
        angle_ids = [d["angle_id"] for d in results]
        assert len(angle_ids) == len(set(angle_ids)), f"同じ週の中で切り口が重複した: {angle_ids}"

    _with_isolated_storage(run)
    print("✓ 週次生成: 同じ週の中では切り口(angle_id)が重複しない")


def test_generate_week_skips_existing_drafts_without_force():
    def run():
        monday = date(2026, 8, 24)
        first = weekly.generate_week(monday, client=FakeClient())
        second = weekly.generate_week(monday, client=FakeClient())
        # 2回目は生成し直さないので、bodyが1回目と同じまま
        assert [d["body"] for d in first] == [d["body"] for d in second]

    _with_isolated_storage(run)
    print("✓ 週次生成: 既存の下書きは --force なしでは上書きしない")


if __name__ == "__main__":
    for fn in [
        test_generate_week_creates_six_days_mon_to_sat,
        test_generate_week_avoids_duplicate_angles_within_week,
        test_generate_week_skips_existing_drafts_without_force,
    ]:
        fn()
    print("\nすべてのテストに合格しました。")

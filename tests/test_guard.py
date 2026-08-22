"""guard（短時間の連続投稿の抑止）のテスト:
    python -m pytest tests/test_guard.py -q
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, guard  # noqa: E402


def _with_temp_attempt_file(fn):
    original = config.LAST_POST_ATTEMPT_FILE
    with tempfile.TemporaryDirectory() as d:
        config.LAST_POST_ATTEMPT_FILE = Path(d) / "last_post_attempt.json"
        try:
            fn()
        finally:
            config.LAST_POST_ATTEMPT_FILE = original


def test_check_passes_when_no_previous_attempt():
    def run():
        guard.check(datetime.now())  # 例外が出なければOK

    _with_temp_attempt_file(run)
    print("✓ 記録がなければクールダウンなしで通る")


def test_check_blocks_within_cooldown_and_force_overrides():
    def run():
        now = datetime.now()
        guard.record(now)
        try:
            guard.check(now + timedelta(minutes=1))
            assert False, "CooldownError が発生するはず"
        except guard.CooldownError as e:
            assert "--force" in str(e)
        guard.check(now + timedelta(minutes=1), force=True)  # force なら通る

    _with_temp_attempt_file(run)
    print("✓ クールダウン中は止まり、--force で上書きできる")


def test_check_passes_after_cooldown_elapses():
    def run():
        now = datetime.now()
        guard.record(now)
        guard.check(now + timedelta(minutes=config.POST_COOLDOWN_MINUTES + 1))

    _with_temp_attempt_file(run)
    print("✓ クールダウン経過後は通る")


if __name__ == "__main__":
    for fn in [
        test_check_passes_when_no_previous_attempt,
        test_check_blocks_within_cooldown_and_force_overrides,
        test_check_passes_after_cooldown_elapses,
    ]:
        fn()
    print("\nすべてのテストに合格しました。")

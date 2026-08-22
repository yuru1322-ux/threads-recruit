"""短時間の連続投稿を防ぐガード.

Threads投稿APIを短時間に何度も叩くとMeta側のレート制限・アクセスブロック
（OAuthException code 200 "API access blocked" 等）を招くおそれがある。
前回の投稿試行時刻を data/last_post_attempt.json に記録し、
POST_COOLDOWN_MINUTES 以内の再実行を止める。
"""
from __future__ import annotations

import json
from datetime import datetime

from . import config


class CooldownError(RuntimeError):
    def __init__(self, last_attempted_at: datetime, remaining_seconds: float):
        self.last_attempted_at = last_attempted_at
        self.remaining_seconds = remaining_seconds
        remaining_minutes = int(remaining_seconds // 60) + 1
        super().__init__(
            f"前回の投稿試行（{last_attempted_at.isoformat()}）から"
            f"{config.POST_COOLDOWN_MINUTES}分経っていません（あと約{remaining_minutes}分）。"
            "短時間の連続実行はMeta側の制限を招くため停止します。"
            "意図的に実行する場合は --force を付けてください。"
        )


def _read_last_attempt() -> datetime | None:
    if not config.LAST_POST_ATTEMPT_FILE.exists():
        return None
    try:
        data = json.loads(config.LAST_POST_ATTEMPT_FILE.read_text(encoding="utf-8"))
        return datetime.fromisoformat(data["attempted_at"])
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        return None


def check(now: datetime, *, force: bool = False) -> None:
    """クールダウン中なら CooldownError を送出する。force=True なら常に通す。"""
    if force:
        return
    last = _read_last_attempt()
    if last is None:
        return
    elapsed = (now - last).total_seconds()
    cooldown_seconds = config.POST_COOLDOWN_MINUTES * 60
    if elapsed < cooldown_seconds:
        raise CooldownError(last, cooldown_seconds - elapsed)


def record(now: datetime) -> None:
    """投稿API呼び出し直前に、今回の試行時刻を記録する."""
    config.LAST_POST_ATTEMPT_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.LAST_POST_ATTEMPT_FILE.write_text(
        json.dumps({"attempted_at": now.isoformat()}, ensure_ascii=False),
        encoding="utf-8",
    )

"""投稿ログ（JSONL）.

data/logs/YYYY-MM.jsonl に1行1レコードで追記する。
"""
from __future__ import annotations

import json
from datetime import datetime

from . import config


def write(record: dict) -> None:
    now = datetime.now(config.TZ)
    record = {"logged_at": now.isoformat(), **record}
    path = config.LOG_DIR / f"{now:%Y-%m}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_post(
    *,
    posted_at: str,
    weekday_label: str,
    theme_name: str,
    angle_label: str,
    body_text: str,
    reply_text: str,
    status: str,
    post_id: str | None = None,
    reply_id: str | None = None,
    error: str | None = None,
) -> None:
    write(
        {
            "posted_at": posted_at,
            "weekday": weekday_label,
            "theme": theme_name,
            "angle": angle_label,
            "body_text": body_text,
            "reply_text": reply_text,
            "status": status,
            "threads_post_id": post_id,
            "threads_reply_id": reply_id,
            "error": error,
        }
    )

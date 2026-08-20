"""下書き（drafts/YYYY-MM-DD.json）の読み書き."""
from __future__ import annotations

import json
from datetime import date, datetime

from . import config

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_POSTED = "posted"
STATUS_FAILED = "failed"


def path_for(target: date):
    return config.DRAFT_DIR / f"{target.isoformat()}.json"


def exists(target: date) -> bool:
    return path_for(target).exists()


def load(target: date) -> dict | None:
    p = path_for(target)
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def save(draft: dict) -> None:
    target = datetime.strptime(draft["date"], "%Y-%m-%d").date()
    p = path_for(target)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
        f.write("\n")


def new_draft(target: date, weekday_label: str, generated: dict) -> dict:
    return {
        "date": target.isoformat(),
        "weekday": weekday_label,
        "scheduled_at": f"{target.isoformat()}T20:00:00+09:00",
        "theme_key": generated["theme_key"],
        "theme_name": generated["theme_name"],
        "angle_id": generated["angle_id"],
        "angle_label": generated["angle_label"],
        "hook": generated.get("hook", ""),
        "body": generated["body"],
        "reply": generated["reply"],
        "summary": generated.get("summary", ""),
        "warnings": generated.get("warnings", []),
        "status": STATUS_PENDING,
        "generated_at": datetime.now(config.TZ).isoformat(),
        "posted_at": None,
        "threads_post_id": None,
        "threads_reply_id": None,
        "error": None,
    }


def set_status(target: date, status: str) -> dict:
    draft = load(target)
    if draft is None:
        raise FileNotFoundError(f"{target} の下書きがありません")
    draft["status"] = status
    save(draft)
    return draft


def render(draft: dict) -> str:
    """人が読む用の整形表示."""
    warn = "\n".join(f"  ⚠ {w}" for w in draft.get("warnings", []))
    return (
        f"日付   : {draft['date']}（{draft['weekday']}）20:00\n"
        f"テーマ : {draft['theme_name']}\n"
        f"切り口 : {draft['angle_label']}\n"
        f"状態   : {draft['status']}\n"
        f"{'-' * 40}\n"
        f"【1投稿目（本文）】\n{draft['body']}\n\n"
        f"【2投稿目（返信欄）】\n{draft['reply']}\n"
        f"{'-' * 40}\n"
        + (f"要確認:\n{warn}\n" if warn else "")
    )

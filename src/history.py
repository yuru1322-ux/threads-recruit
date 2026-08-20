"""投稿済みネタ・切り口の重複管理.

data/history.json に投稿済みの「テーマ×切り口」と要約を記録し、
同じ切り口は ANGLE_COOLDOWN_DAYS（既定28日=4週間）空けるまで再利用しない。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from . import config


def _load() -> dict:
    if not config.HISTORY_FILE.exists():
        return {"entries": []}
    try:
        with config.HISTORY_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {"entries": []}
    data.setdefault("entries", [])
    return data


def _save(data: dict) -> None:
    config.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with config.HISTORY_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def recent_entries(theme_key: str, today: date, days: int | None = None) -> list[dict]:
    """指定テーマの、クールダウン期間内のエントリ."""
    days = config.ANGLE_COOLDOWN_DAYS if days is None else days
    since = today - timedelta(days=days)
    return [
        e
        for e in _load()["entries"]
        if e.get("theme_key") == theme_key and _parse(e["date"]) >= since
    ]


def used_angles(theme_key: str, today: date) -> list[str]:
    """クールダウン期間内に使用済みの切り口 id 一覧."""
    return sorted({e["angle_id"] for e in recent_entries(theme_key, today) if e.get("angle_id")})


def available_angles(theme_key: str, all_angles: list[dict], today: date) -> list[dict]:
    """まだ使えるの切り口。全部使い切っていたら最も古いものから解放する."""
    used = set(used_angles(theme_key, today))
    remaining = [a for a in all_angles if a["id"] not in used]
    if remaining:
        return remaining
    # 全て使用済み → 使用日が最も古い順に並べ直して返す（最低限の分散は保つ）
    entries = recent_entries(theme_key, today)
    last_used: dict[str, date] = {}
    for e in entries:
        d = _parse(e["date"])
        if e.get("angle_id") and (e["angle_id"] not in last_used or d > last_used[e["angle_id"]]):
            last_used[e["angle_id"]] = d
    return sorted(all_angles, key=lambda a: last_used.get(a["id"], date.min))


def recent_summaries(theme_key: str, today: date, limit: int = 12) -> list[str]:
    """直近の投稿要約（プロンプトに渡して内容の重複を避けるため）."""
    entries = sorted(recent_entries(theme_key, today, days=120), key=lambda e: e["date"], reverse=True)
    out = []
    for e in entries[:limit]:
        out.append(f"{e['date']}［{e.get('angle_label', e.get('angle_id', '-'))}］{e.get('summary', '')}")
    return out


def record(
    *,
    post_date: date,
    theme_key: str,
    theme_name: str,
    angle_id: str,
    angle_label: str,
    summary: str,
    hook: str,
) -> None:
    data = _load()
    data["entries"] = [e for e in data["entries"] if e.get("date") != post_date.isoformat() or e.get("theme_key") != theme_key]
    data["entries"].append(
        {
            "date": post_date.isoformat(),
            "theme_key": theme_key,
            "theme_name": theme_name,
            "angle_id": angle_id,
            "angle_label": angle_label,
            "summary": summary,
            "hook": hook,
        }
    )
    data["entries"].sort(key=lambda e: e["date"])
    _save(data)


def recent_hooks(limit: int = 10) -> list[str]:
    """全テーマ横断で直近に使ったつかみフレーズ（連続使用を避ける）."""
    entries = sorted(_load()["entries"], key=lambda e: e["date"], reverse=True)
    return [e.get("hook", "") for e in entries[:limit] if e.get("hook")]

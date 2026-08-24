"""週次まとめ生成（月〜土の6日分を1回で生成する）."""
from __future__ import annotations

from datetime import date, timedelta

from . import drafts, generator
from .generator import WEEKDAY_JA
from .themes import get_theme


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_dates(monday: date) -> list[date]:
    """月〜土の6日分（日曜は投稿なしのため含めない）."""
    return [monday + timedelta(days=i) for i in range(6)]


def generate_week(monday: date, *, force: bool = False, client=None) -> list[dict]:
    """monday を起点とした週の月〜土6日分の下書きを生成・保存する.

    同じ週の中で切り口（angle_id）が重複しないよう、既に使った切り口idを
    後続の日の生成から除外する（テーマ間で共通のBASE_ANGLESを避けるため）。
    既存の下書きがある日は --force なしではスキップし、その角度をused集合に加える。
    client を渡さない場合、実際に生成が必要になった時点で1つだけ作って6日分使い回す
    （テストでは FakeClient を渡せば anthropic を一切呼ばずに済む）。
    """
    used_ids_this_week: set[str] = set()
    results: list[dict] = []
    for target in week_dates(monday):
        theme = get_theme(target.weekday())
        if theme is None:
            continue

        if drafts.exists(target) and not force:
            existing = drafts.load(target)
            results.append(existing)
            if existing.get("angle_id"):
                used_ids_this_week.add(existing["angle_id"])
            continue

        if client is None:
            client = generator.default_client()
        generated = generator.generate(theme, target, exclude_ids=used_ids_this_week, client=client)
        used_ids_this_week.add(generated["angle_id"])
        draft = drafts.new_draft(target, WEEKDAY_JA[theme.weekday], generated)
        drafts.save(draft)
        results.append(draft)
    return results

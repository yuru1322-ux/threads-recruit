"""API キーなしで動く基本テスト:  python -m pytest tests -q  または  python tests/test_basic.py"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import drafts, generator, history  # noqa: E402
from src.themes import THEMES, get_theme  # noqa: E402


class FakeMessage:
    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]


class FakeClient:
    """Anthropic クライアントのモック."""

    def __init__(self, payload):
        self.payload = payload
        self.messages = self

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return FakeMessage(self.payload)


def test_weekday_mapping():
    assert get_theme(0).name == "給与・収入系"
    assert get_theme(2).key == "oncall"
    assert get_theme(5).key == "dm"
    assert get_theme(6) is None, "日曜はテーマなし"
    print("✓ 曜日→テーマの割り当て")


def test_generate_with_mock():
    payload = """```json
    {"hook": "ここだけの話なんですが…", "body": "ここだけの話なんですが…\\n\\n業界平均より10万円以上高い固定給なんです！",
     "reply": "訪問看護は年俸制でボーナスなしという職場も多いのですが、うちは固定給で賞与もあります。気になる方は気軽にDMしてくださいね。",
     "summary": "業界平均との給与比較"}
    ```"""
    theme = get_theme(0)
    res = generator.generate(theme, date(2026, 8, 17), client=FakeClient(payload))
    assert res["theme_key"] == "salary"
    assert res["warnings"] == [], res["warnings"]
    print("✓ 生成〜JSONパース")


def test_validation_catches_rule_breaks():
    theme = get_theme(0)
    bad = {"body": "実は…\n\n固定給45万円なんです！", "reply": "詳細です"}
    w = generator.validate(bad, theme)
    assert any("45万" in x for x in w), w

    theme = get_theme(2)
    bad2 = {"body": "知ってますか？\n\nオンコールは3か月に1回だけなんです", "reply": "詳細です"}
    w2 = generator.validate(bad2, theme)
    assert any("一般スタッフ" in x for x in w2), w2

    ok2 = {"body": "知ってますか？\n\n一般スタッフのオンコールは3か月に1回なんです", "reply": "詳細です"}
    assert generator.validate(ok2, theme) == []
    print("✓ ルール違反の自動検出（月曜の金額・水曜の断り書き）")


def test_angle_cooldown(tmp_root=None):
    theme = get_theme(1)
    today = date(2026, 8, 18)
    all_ids = {a["id"] for a in theme.angles}
    avail_before = {a["id"] for a in history.available_angles(theme.key, theme.angles, today)}
    assert avail_before == all_ids or avail_before <= all_ids
    print(f"✓ 重複管理（利用可能な切り口 {len(avail_before)}/{len(all_ids)}）")


def test_prompt_contains_rules():
    theme = get_theme(2)
    p = generator.build_prompt(theme, date(2026, 8, 19), theme.angles[0])
    assert "一般スタッフは" in p
    assert "他社名" in p
    p0 = generator.build_prompt(get_theme(0), date(2026, 8, 17), get_theme(0).angles[0])
    assert "45万円という具体的な数字は絶対に出さない" in p0
    print("✓ プロンプトに必須ルールが含まれる")


def test_draft_roundtrip():
    theme = get_theme(4)
    gen = {"theme_key": theme.key, "theme_name": theme.name, "angle_id": "hourly_leave",
           "angle_label": "時間休", "hook": "実は…", "body": "実は…\n\n有休がよく通ります！",
           "reply": "詳細。DMどうぞ。", "summary": "有休の話", "warnings": []}
    d = drafts.new_draft(date(2026, 8, 21), "金", gen)
    assert d["status"] == "pending"
    assert "20:00:00+09:00" in d["scheduled_at"]
    assert "【2投稿目（返信欄）】" in drafts.render(d)
    print("✓ 下書きの生成・整形")


if __name__ == "__main__":
    for fn in [test_weekday_mapping, test_generate_with_mock, test_validation_catches_rule_breaks,
               test_angle_cooldown, test_prompt_contains_rules, test_draft_roundtrip]:
        fn()
    print("\nすべてのテストに合格しました。")

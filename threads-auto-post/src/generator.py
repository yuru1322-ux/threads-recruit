"""Claude による投稿文の生成."""
from __future__ import annotations

import json
import random
import re
from datetime import date

from . import config, history
from .themes import HOOK_EXAMPLES, STYLE_RULES, Theme

WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]

SYSTEM_PROMPT = """あなたは、訪問看護ステーションで働く現役の訪問看護師です。
自分が働いている職場のリアルをThreadsで発信し、「この働き方、合いそうかも」と思ってくれた方からDMをもらうことを目的にしています。
求人広告のコピーライターではなく、あくまで「中の人が本音をこぼしている」トーンで書いてください。

出力は必ず指定されたJSON形式のみとし、前置きや説明文は一切書かないでください。"""

USER_TEMPLATE = """今日は{date_str}（{weekday}曜日）です。
今日のテーマは「{theme_name}」です。

# 使ってよい素材（これ以外の事実を創作しないこと）
{materials}

# このテーマ固有の注意点
{notes}

# 今日使う切り口
{angle_label}（id: {angle_id}）
この切り口の角度から書いてください。

# 直近に投稿済みの内容（重複を避けること）
{recent}

# 直近で使ったつかみフレーズ（連続使用を避けること）
{recent_hooks}

# 投稿フォーマット（厳守）
- body（1投稿目・本文）:
  1行目 … つかみフレーズ（例のような、思わず続きが読みたくなる一言）
  2行目以降 … アピールポイントを1文
  ※合計で概ね40〜90文字。長くしすぎないこと。
  ※1行目と2行目の間は空行を1つ入れる。
- reply（2投稿目・返信欄）:
  本文の続きとして、詳細な内容を具体的に書く。
  最後に、押しつけがましくない自然なDM誘導で締める。
  ※概ね150〜300文字。

# つかみフレーズの例（そのまま使っても、同じ温度感で作ってもよい）
{hooks}

# 文体ルール（厳守）
{style}

# 出力形式
以下のJSONのみを出力してください。
{{
  "hook": "1投稿目の1行目に使ったつかみフレーズ",
  "body": "1投稿目の全文（改行を含む）",
  "reply": "2投稿目の全文（改行を含む）",
  "summary": "この投稿の内容を30文字程度で要約（重複管理用）"
}}"""


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items) if items else "- （特になし）"


def choose_angle(theme: Theme, target: date, seed: int | None = None) -> dict:
    """クールダウンを考慮して切り口を選ぶ."""
    candidates = history.available_angles(theme.key, theme.angles, target)
    if not candidates:
        candidates = list(theme.angles)
    rng = random.Random(seed if seed is not None else f"{theme.key}-{target.isoformat()}")
    return rng.choice(candidates)


def build_prompt(theme: Theme, target: date, angle: dict) -> str:
    return USER_TEMPLATE.format(
        date_str=target.strftime("%Y年%m月%d日"),
        weekday=WEEKDAY_JA[theme.weekday],
        theme_name=theme.name,
        materials=_bullets(theme.materials),
        notes=_bullets(theme.notes),
        angle_label=angle["label"],
        angle_id=angle["id"],
        recent=_bullets(history.recent_summaries(theme.key, target)),
        recent_hooks=_bullets(history.recent_hooks()),
        hooks=_bullets(HOOK_EXAMPLES),
        style=_bullets(STYLE_RULES),
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"JSONを抽出できませんでした: {text[:200]}")
    return json.loads(text[start : end + 1])


def validate(result: dict, theme: Theme) -> list[str]:
    """生成結果のセルフチェック。問題があれば警告文のリストを返す."""
    warnings: list[str] = []
    body, reply = result.get("body", ""), result.get("reply", "")

    if not body or not reply:
        warnings.append("body または reply が空です")
    if len(body) > config.MAX_TEXT_LEN:
        warnings.append(f"本文が{config.MAX_TEXT_LEN}文字を超えています（{len(body)}文字）")
    if len(reply) > config.MAX_TEXT_LEN:
        warnings.append(f"返信文が{config.MAX_TEXT_LEN}文字を超えています（{len(reply)}文字）")
    if "#" in body or "#" in reply:
        warnings.append("ハッシュタグが含まれている可能性があります")

    # 月曜：45万円を本文で出していないか
    if theme.key == "salary" and re.search(r"45\s*万", body):
        warnings.append("【要修正】月曜の本文に『45万』が含まれています。金額は返信欄で明かす決まりです")

    # 水曜：オンコール回数に「一般スタッフ」の断りがあるか
    if theme.key == "oncall":
        joined = body + reply
        if re.search(r"3\s*か?月に1回|3ヶ月に1回", joined) and "一般スタッフ" not in joined:
            warnings.append("【要修正】オンコール回数に『一般スタッフは』の断りがありません")

    return warnings


def generate(theme: Theme, target: date, angle: dict | None = None, *, client=None) -> dict:
    """投稿文を生成して dict を返す."""
    angle = angle or choose_angle(theme, target)
    prompt = build_prompt(theme, target, angle)

    if client is None:
        import anthropic

        config.require("ANTHROPIC_API_KEY", config.ANTHROPIC_API_KEY)
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    message = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
    result = _extract_json(text)

    result["angle_id"] = angle["id"]
    result["angle_label"] = angle["label"]
    result["theme_key"] = theme.key
    result["theme_name"] = theme.name
    result["warnings"] = validate(result, theme)
    return result

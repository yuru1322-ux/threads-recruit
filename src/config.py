"""環境変数と共通設定."""
from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv 未導入でも動く
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOG_DIR = DATA_DIR / "logs"
DRAFT_DIR = ROOT / "drafts"
HISTORY_FILE = DATA_DIR / "history.json"
LAST_POST_ATTEMPT_FILE = DATA_DIR / "last_post_attempt.json"
STYLE_NOTES_FILE = ROOT / "style-notes.md"
STYLE_EDITS_FILE = DATA_DIR / "style_edits.jsonl"

for _d in (DATA_DIR, LOG_DIR, DRAFT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN", "")
THREADS_USER_ID = os.getenv("THREADS_USER_ID", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tokyo"))
ANGLE_COOLDOWN_DAYS = int(os.getenv("ANGLE_COOLDOWN_DAYS", "28"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")

# 短時間の連続投稿でMeta側の制限を招かないためのクールダウン（分）
POST_COOLDOWN_MINUTES = int(os.getenv("POST_COOLDOWN_MINUTES", "10"))

GRAPH_BASE = "https://graph.threads.net/v1.0"

# Threads のテキスト上限
MAX_TEXT_LEN = 500


def require(name: str, value: str) -> str:
    if not value:
        raise RuntimeError(f"環境変数 {name} が設定されていません（.env または GitHub Secrets を確認してください）")
    return value

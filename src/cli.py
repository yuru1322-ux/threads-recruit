"""コマンドラインインターフェース.

  python -m src.cli generate [--date YYYY-MM-DD] [--angle ANGLE_ID] [--force]
  python -m src.cli show     [--date YYYY-MM-DD]
  python -m src.cli approve  [--date YYYY-MM-DD]
  python -m src.cli reject   [--date YYYY-MM-DD]
  python -m src.cli post     [--date YYYY-MM-DD] [--require-approval] [--dry-run]
  python -m src.cli check
  python -m src.cli log      [--limit N]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

from . import config, drafts, generator, history, postlog
from .generator import WEEKDAY_JA
from .themes import get_theme


def _today() -> date:
    return datetime.now(config.TZ).date()


def _parse_date(s: str | None) -> date:
    return _today() if not s else datetime.strptime(s, "%Y-%m-%d").date()


# ---------------------------------------------------------------- generate
def cmd_generate(args) -> int:
    target = _parse_date(args.date)
    theme = get_theme(target.weekday())
    if theme is None:
        print(f"{target}（日）は投稿なしの日です。生成をスキップします。")
        return 0
    if drafts.exists(target) and not args.force:
        print(f"{target} の下書きは既にあります。上書きするには --force を付けてください。")
        return 0

    angle = None
    if args.angle:
        angle = next((a for a in theme.angles if a["id"] == args.angle), None)
        if angle is None:
            print(f"切り口 '{args.angle}' は {theme.name} に存在しません。", file=sys.stderr)
            print("利用可能: " + ", ".join(a["id"] for a in theme.angles), file=sys.stderr)
            return 1

    generated = generator.generate(theme, target, angle)
    draft = drafts.new_draft(target, WEEKDAY_JA[theme.weekday], generated)
    drafts.save(draft)
    print(drafts.render(draft))
    print(f"保存しました: {drafts.path_for(target)}")
    return 0


# ------------------------------------------------------------------- show
def cmd_show(args) -> int:
    target = _parse_date(args.date)
    draft = drafts.load(target)
    if draft is None:
        print(f"{target} の下書きはありません。")
        return 1
    print(drafts.render(draft))
    return 0


def _set(args, status: str) -> int:
    target = _parse_date(args.date)
    try:
        draft = drafts.set_status(target, status)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"{target} の下書きを {status} にしました。")
    print(drafts.render(draft))
    return 0


def cmd_approve(args) -> int:
    return _set(args, drafts.STATUS_APPROVED)


def cmd_reject(args) -> int:
    return _set(args, drafts.STATUS_REJECTED)


# ------------------------------------------------------------------- post
def cmd_post(args) -> int:
    target = _parse_date(args.date)
    theme = get_theme(target.weekday())
    if theme is None:
        print(f"{target}（日）は投稿なしの日です。")
        return 0

    draft = drafts.load(target)
    if draft is None:
        print(f"{target} の下書きがありません。投稿を中止します。", file=sys.stderr)
        postlog.log_post(
            posted_at=datetime.now(config.TZ).isoformat(),
            weekday_label=WEEKDAY_JA[target.weekday()],
            theme_name=theme.name,
            angle_label="-",
            body_text="",
            reply_text="",
            status="skipped_no_draft",
            error="下書きが存在しません",
        )
        return 1

    if draft["status"] == drafts.STATUS_POSTED:
        print(f"{target} は既に投稿済みです（post_id={draft['threads_post_id']}）。")
        return 0

    if args.require_approval and draft["status"] not in (drafts.STATUS_APPROVED, drafts.STATUS_PARTIAL):
        print(f"{target} の下書きは未承認（status={draft['status']}）のため投稿しません。", file=sys.stderr)
        postlog.log_post(
            posted_at=datetime.now(config.TZ).isoformat(),
            weekday_label=draft["weekday"],
            theme_name=draft["theme_name"],
            angle_label=draft["angle_label"],
            body_text=draft["body"],
            reply_text=draft["reply"],
            status="skipped_not_approved",
            error=f"status={draft['status']}",
        )
        return 2

    dry = args.dry_run or config.DRY_RUN
    now = datetime.now(config.TZ)

    if dry:
        print("[DRY RUN] 実際には投稿しません。以下の内容で投稿されます。\n")
        print(drafts.render(draft))
        postlog.log_post(
            posted_at=now.isoformat(),
            weekday_label=draft["weekday"],
            theme_name=draft["theme_name"],
            angle_label=draft["angle_label"],
            body_text=draft["body"],
            reply_text=draft["reply"],
            status="dry_run",
        )
        return 0

    from .threads_api import PartialPostError, ThreadsClient, ThreadsError

    try:
        client = ThreadsClient()
        if draft["status"] == drafts.STATUS_PARTIAL and draft.get("threads_post_id"):
            # 本文は投稿済み。返信だけ再試行する（本文の二重投稿を避ける）。
            post_id = draft["threads_post_id"]
            reply_id = client.post_text(draft["reply"], reply_to_id=post_id)
        else:
            post_id, reply_id = client.post_with_reply(draft["body"], draft["reply"])
    except PartialPostError as e:
        draft["status"] = drafts.STATUS_PARTIAL
        draft["threads_post_id"] = e.post_id
        draft["error"] = str(e)
        drafts.save(draft)
        postlog.log_post(
            posted_at=now.isoformat(),
            weekday_label=draft["weekday"],
            theme_name=draft["theme_name"],
            angle_label=draft["angle_label"],
            body_text=draft["body"],
            reply_text=draft["reply"],
            status="partial_body_only",
            post_id=e.post_id,
            error=str(e),
        )
        print(f"本文は投稿されましたが返信の投稿に失敗しました（post_id={e.post_id}）。次回実行時に返信のみ再試行します。", file=sys.stderr)
        return 1
    except (ThreadsError, RuntimeError) as e:
        draft["status"] = drafts.STATUS_FAILED
        draft["error"] = str(e)
        drafts.save(draft)
        postlog.log_post(
            posted_at=now.isoformat(),
            weekday_label=draft["weekday"],
            theme_name=draft["theme_name"],
            angle_label=draft["angle_label"],
            body_text=draft["body"],
            reply_text=draft["reply"],
            status="failed",
            error=str(e),
        )
        print(f"投稿に失敗しました: {e}", file=sys.stderr)
        return 1

    draft["status"] = drafts.STATUS_POSTED
    draft["posted_at"] = now.isoformat()
    draft["threads_post_id"] = post_id
    draft["threads_reply_id"] = reply_id
    draft["error"] = None
    drafts.save(draft)

    history.record(
        post_date=target,
        theme_key=draft["theme_key"],
        theme_name=draft["theme_name"],
        angle_id=draft["angle_id"],
        angle_label=draft["angle_label"],
        summary=draft.get("summary", ""),
        hook=draft.get("hook", ""),
    )
    postlog.log_post(
        posted_at=now.isoformat(),
        weekday_label=draft["weekday"],
        theme_name=draft["theme_name"],
        angle_label=draft["angle_label"],
        body_text=draft["body"],
        reply_text=draft["reply"],
        status="success",
        post_id=post_id,
        reply_id=reply_id,
    )
    print(f"投稿しました。post_id={post_id} / reply_id={reply_id}")
    return 0


# ------------------------------------------------------------------ check
def cmd_check(args) -> int:
    ok = True
    print("== 環境変数 ==")
    for name in ("THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "ANTHROPIC_API_KEY"):
        val = getattr(config, name)
        print(f"  {name}: {'設定済み' if val else '未設定 ✗'}")
        ok = ok and bool(val)
    print(f"  ANTHROPIC_MODEL: {config.ANTHROPIC_MODEL}")
    print(f"  TIMEZONE: {config.TZ}")

    if config.THREADS_ACCESS_TOKEN and config.THREADS_USER_ID:
        from .threads_api import ThreadsClient, ThreadsError

        try:
            info = ThreadsClient().check_token()
            print(f"== Threads API 疎通 OK == @{info.get('username', '?')} (id={info.get('id')})")
        except ThreadsError as e:
            ok = False
            print(f"== Threads API 疎通 NG == {e}")

    print("\n== 今週の予定 ==")
    today = _today()
    monday = today - timedelta(days=today.weekday())
    for i in range(7):
        d = monday + timedelta(days=i)
        theme = get_theme(d.weekday())
        draft = drafts.load(d)
        state = draft["status"] if draft else ("—" if theme else "投稿なし")
        print(f"  {d}（{WEEKDAY_JA[d.weekday()]}） {theme.name if theme else '休み':<18} {state}")
    return 0 if ok else 1


# -------------------------------------------------------------------- log
def cmd_log(args) -> int:
    import json

    files = sorted(config.LOG_DIR.glob("*.jsonl"))
    rows = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    rows = rows[-args.limit :]
    if not rows:
        print("ログはまだありません。")
        return 0
    for r in rows:
        print(f"{r.get('posted_at', '')[:19]} [{r.get('weekday')}] {r.get('theme')} / {r.get('angle')} -> {r.get('status')} {r.get('threads_post_id') or ''}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="threads-auto-post", description="Threads自動投稿システム")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_date(p):
        p.add_argument("--date", help="対象日 (YYYY-MM-DD)。既定は今日")
        return p

    g = add_date(sub.add_parser("generate", help="下書きを生成する"))
    g.add_argument("--angle", help="切り口を明示指定する")
    g.add_argument("--force", action="store_true", help="既存の下書きを上書きする")
    g.set_defaults(func=cmd_generate)

    add_date(sub.add_parser("show", help="下書きを表示する")).set_defaults(func=cmd_show)
    add_date(sub.add_parser("approve", help="下書きを承認する")).set_defaults(func=cmd_approve)
    add_date(sub.add_parser("reject", help="下書きを却下する")).set_defaults(func=cmd_reject)

    p = add_date(sub.add_parser("post", help="下書きをThreadsへ投稿する"))
    p.add_argument("--require-approval", action="store_true", help="承認済みの下書きのみ投稿する")
    p.add_argument("--dry-run", action="store_true", help="実際には投稿しない")
    p.set_defaults(func=cmd_post)

    sub.add_parser("check", help="設定と今週の状況を確認する").set_defaults(func=cmd_check)

    l = sub.add_parser("log", help="投稿ログを表示する")
    l.add_argument("--limit", type=int, default=20)
    l.set_defaults(func=cmd_log)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

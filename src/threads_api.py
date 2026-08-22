"""Threads API（Meta Graph API）クライアント.

投稿は2段階:
  1. メディアコンテナ作成  POST /{user-id}/threads
  2. 公開                  POST /{user-id}/threads_publish
返信は 1. で reply_to_id を指定する。
"""
from __future__ import annotations

import time

import requests

from . import config


class ThreadsError(RuntimeError):
    pass


class ThreadsAPIError(ThreadsError):
    """Graph API がエラーレスポンス（JSONの error オブジェクト）を返した場合の例外.

    code / error_subcode / fbtrace_id を保持し、diagnose やエラーメッセージ整形で使う。
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: int | None = None,
        error_subcode: int | None = None,
        error_type: str | None = None,
        fbtrace_id: str | None = None,
        raw_message: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.error_subcode = error_subcode
        self.error_type = error_type
        self.fbtrace_id = fbtrace_id
        self.raw_message = raw_message

    @property
    def is_blocked(self) -> bool:
        """Meta側のアクセス制限（OAuthException code 200 "API access blocked"）かどうか."""
        return self.code == 200 and self.error_type == "OAuthException"


def _parse_api_error(res: "requests.Response") -> ThreadsAPIError:
    err: dict = {}
    try:
        body = res.json()
        if isinstance(body, dict):
            err = body.get("error") or {}
    except ValueError:
        pass
    message = err.get("message") or res.text[:500]
    return ThreadsAPIError(
        f"HTTP {res.status_code}: {message}",
        status_code=res.status_code,
        code=err.get("code"),
        error_subcode=err.get("error_subcode"),
        error_type=err.get("type"),
        fbtrace_id=err.get("fbtrace_id"),
        raw_message=message,
    )


def describe_error(e: ThreadsAPIError) -> str:
    """code / error_subcode から、日本語の原因説明と対処法を返す."""
    if e.is_blocked:
        return (
            "Meta側のAPIアクセス制限（OAuthException code 200 \"API access blocked\"）と判断されます。"
            "手動リトライを繰り返すとブロックが長引くおそれがあるため、今は再実行せず時間をおいてください。"
            "`python -m src.cli diagnose` で読み取りが復旧しているか確認できます。"
        )
    if e.code == 100 and e.error_subcode == 33:
        return (
            "対象ID、または権限の問題です（code 100 / subcode 33）。"
            "reply_to_id・コンテナIDが正しいか、トークンの投稿権限（threads_content_publish 等）を確認してください。"
        )
    if e.code in (4, 17, 32):
        return (
            f"レート制限です（code {e.code}）。しばらく時間をおいてから再実行してください。"
            "短時間の連続実行は避けてください。"
        )
    if e.code == 190:
        return (
            f"アクセストークンが無効・期限切れの可能性があります（code 190 / subcode {e.error_subcode}）。"
            "Meta for Developers でトークンを再発行し、GitHub Secrets の THREADS_ACCESS_TOKEN を更新してください。"
        )
    return (
        f"未分類のAPIエラーです（code={e.code}, error_subcode={e.error_subcode}）。"
        f"fbtrace_id={e.fbtrace_id} を確認してください。"
    )


class PartialPostError(ThreadsError):
    """本文（1投稿目）は公開できたが、返信（2投稿目）が失敗した場合の例外.

    本文の post_id を保持し、呼び出し側が二重投稿せずに返信だけ再試行できるようにする。
    """

    def __init__(self, post_id: str, cause: Exception):
        super().__init__(f"本文の投稿（post_id={post_id}）は成功しましたが、返信の投稿に失敗しました: {cause}")
        self.post_id = post_id
        self.cause = cause


class ThreadsClient:
    def __init__(self, access_token: str | None = None, user_id: str | None = None, *, timeout: int = 30):
        self.access_token = access_token if access_token is not None else config.THREADS_ACCESS_TOKEN
        self.user_id = user_id if user_id is not None else config.THREADS_USER_ID
        self.timeout = timeout
        config.require("THREADS_ACCESS_TOKEN", self.access_token)
        config.require("THREADS_USER_ID", self.user_id)

    # ---- 低レベル ----
    def _post(self, path: str, params: dict, *, retries: int = 3) -> dict:
        url = f"{config.GRAPH_BASE}/{path}"
        params = {**params, "access_token": self.access_token}
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                res = requests.post(url, data=params, timeout=self.timeout)
            except requests.RequestException as e:
                last_err = e
                if attempt < retries - 1:
                    time.sleep(2 ** attempt * 3)
                continue

            if res.ok:
                return res.json()

            api_err = _parse_api_error(res)
            if api_err.is_blocked:
                # Meta側のアクセス制限。リクエストを重ねるとブロックが長引くため、
                # リトライせず即座に投げる。
                raise api_err
            if res.status_code >= 500 or res.status_code == 429:
                last_err = api_err
                if attempt < retries - 1:
                    time.sleep(2 ** attempt * 3)
                continue
            # その他の 4xx は再試行しても無駄なので即座に投げる
            raise api_err
        raise ThreadsError(f"リクエストに失敗しました: {last_err}")

    # ---- 高レベル ----
    def create_container(self, text: str, *, reply_to_id: str | None = None) -> str:
        if len(text) > config.MAX_TEXT_LEN:
            raise ThreadsError(f"テキストが{config.MAX_TEXT_LEN}文字を超えています（{len(text)}文字）")
        params = {"media_type": "TEXT", "text": text}
        if reply_to_id:
            params["reply_to_id"] = reply_to_id
        data = self._post(f"{self.user_id}/threads", params)
        container_id = data.get("id")
        if not container_id:
            raise ThreadsError(f"コンテナIDが取得できませんでした: {data}")
        return container_id

    def get_container_status(self, container_id: str) -> dict:
        res = requests.get(
            f"{config.GRAPH_BASE}/{container_id}",
            params={"fields": "status,error_message", "access_token": self.access_token},
            timeout=self.timeout,
        )
        if not res.ok:
            raise _parse_api_error(res)
        return res.json()

    def wait_until_ready(self, container_id: str, *, timeout: int = 120, poll_interval: int = 5) -> None:
        """コンテナの非同期処理が終わる（status=FINISHED）まで待つ.

        固定秒数のスリープだけでは処理が終わっていないうちに公開しようとして
        「Object with ID '...' does not exist」（error_subcode 33）になることがあるため、
        Meta の推奨通り status をポーリングする。
        """
        deadline = time.monotonic() + timeout
        while True:
            status = self.get_container_status(container_id).get("status")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise ThreadsError(f"コンテナの処理が失敗しました（status={status}, id={container_id}）")
            if time.monotonic() >= deadline:
                raise ThreadsError(f"コンテナの処理待ちがタイムアウトしました（status={status}, id={container_id}）")
            time.sleep(poll_interval)

    def publish(self, container_id: str) -> str:
        self.wait_until_ready(container_id)
        data = self._post(f"{self.user_id}/threads_publish", {"creation_id": container_id})
        post_id = data.get("id")
        if not post_id:
            raise ThreadsError(f"投稿IDが取得できませんでした: {data}")
        return post_id

    def post_text(self, text: str, *, reply_to_id: str | None = None) -> str:
        container_id = self.create_container(text, reply_to_id=reply_to_id)
        return self.publish(container_id)

    def post_with_reply(self, body: str, reply: str) -> tuple[str, str]:
        """本文を投稿し、その返信欄に続きを投稿する.

        本文の投稿が成功した後に返信が失敗した場合は PartialPostError を送出し、
        本文の post_id を呼び出し側に伝える（本文だけ投稿されて放置・二重投稿されるのを防ぐ）。
        """
        post_id = self.post_text(body)
        time.sleep(5)
        try:
            reply_id = self.post_text(reply, reply_to_id=post_id)
        except ThreadsError as e:
            raise PartialPostError(post_id, e) from e
        return post_id, reply_id

    def check_token(self) -> dict:
        """トークンとユーザーIDの疎通確認."""
        res = requests.get(
            f"{config.GRAPH_BASE}/{self.user_id}",
            params={"fields": "id,username,threads_profile_picture_url", "access_token": self.access_token},
            timeout=self.timeout,
        )
        if not res.ok:
            raise _parse_api_error(res)
        return res.json()

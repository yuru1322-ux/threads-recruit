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
                if res.status_code >= 500 or res.status_code == 429:
                    raise ThreadsError(f"HTTP {res.status_code}: {res.text[:300]}")
                if not res.ok:
                    # 4xx は再試行しても無駄なので即座に投げる
                    raise ThreadsError(f"HTTP {res.status_code}: {res.text[:500]}")
                return res.json()
            except (requests.RequestException, ThreadsError) as e:
                last_err = e
                if isinstance(e, ThreadsError) and "HTTP 4" in str(e) and "HTTP 429" not in str(e):
                    raise
                if attempt < retries - 1:
                    time.sleep(2 ** attempt * 3)
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

    def publish(self, container_id: str, *, wait: int = 10) -> str:
        # Meta 側の推奨に従い、コンテナ作成後に少し待ってから公開する
        if wait:
            time.sleep(wait)
        data = self._post(f"{self.user_id}/threads_publish", {"creation_id": container_id})
        post_id = data.get("id")
        if not post_id:
            raise ThreadsError(f"投稿IDが取得できませんでした: {data}")
        return post_id

    def post_text(self, text: str, *, reply_to_id: str | None = None, wait: int = 10) -> str:
        container_id = self.create_container(text, reply_to_id=reply_to_id)
        return self.publish(container_id, wait=wait)

    def post_with_reply(self, body: str, reply: str, *, wait: int = 10) -> tuple[str, str]:
        """本文を投稿し、その返信欄に続きを投稿する."""
        post_id = self.post_text(body, wait=wait)
        time.sleep(5)
        reply_id = self.post_text(reply, reply_to_id=post_id, wait=wait)
        return post_id, reply_id

    def check_token(self) -> dict:
        """トークンとユーザーIDの疎通確認."""
        res = requests.get(
            f"{config.GRAPH_BASE}/{self.user_id}",
            params={"fields": "id,username,threads_profile_picture_url", "access_token": self.access_token},
            timeout=self.timeout,
        )
        if not res.ok:
            raise ThreadsError(f"HTTP {res.status_code}: {res.text[:500]}")
        return res.json()

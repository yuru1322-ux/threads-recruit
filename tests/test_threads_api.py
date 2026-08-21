"""threads_api のモックテスト（実際のAPIは呼ばない）:
    python -m pytest tests/test_threads_api.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.threads_api import PartialPostError, ThreadsClient, ThreadsError  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or str(json_data)
        self.ok = status_code < 400

    def json(self):
        return self._json


def _client():
    return ThreadsClient(access_token="TOKEN", user_id="27984855431123122")


def test_publish_waits_for_finished_status():
    """コンテナが IN_PROGRESS → FINISHED になるまでポーリングしてから publish する."""
    statuses = iter(["IN_PROGRESS", "IN_PROGRESS", "FINISHED"])

    def fake_get(url, params=None, timeout=None):
        return FakeResponse(200, {"status": next(statuses)})

    def fake_post(url, data=None, timeout=None):
        assert url.endswith("/threads_publish")
        assert data["creation_id"] == "container123"
        return FakeResponse(200, {"id": "post456"})

    with patch("src.threads_api.requests.get", side_effect=fake_get), \
         patch("src.threads_api.requests.post", side_effect=fake_post), \
         patch("src.threads_api.time.sleep", return_value=None):
        client = _client()
        post_id = client.publish("container123")
    assert post_id == "post456"
    print("✓ publish はコンテナが FINISHED になるまで待つ")


def test_publish_raises_when_container_errors():
    def fake_get(url, params=None, timeout=None):
        return FakeResponse(200, {"status": "ERROR", "error_message": "bad"})

    with patch("src.threads_api.requests.get", side_effect=fake_get), \
         patch("src.threads_api.time.sleep", return_value=None):
        client = _client()
        try:
            client.publish("container123")
            assert False, "ThreadsError が発生するはず"
        except ThreadsError as e:
            assert "ERROR" in str(e)
    print("✓ コンテナが ERROR の場合は例外になる（不在の container_id を publish しない）")


def test_post_with_reply_raises_partial_post_error_and_keeps_post_id():
    """本文成功・返信失敗のとき、post_id を保持した PartialPostError になる（本文の放置/二重投稿防止）."""
    call = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        return FakeResponse(200, {"status": "FINISHED"})

    def fake_post(url, data=None, timeout=None):
        call["n"] += 1
        if url.endswith("/threads"):
            return FakeResponse(200, {"id": f"container{call['n']}"})
        if url.endswith("/threads_publish"):
            if call["n"] == 2:  # 本文の publish
                return FakeResponse(200, {"id": "body_post_id"})
            return FakeResponse(400, text="Unsupported post request")  # 返信の publish が失敗
        raise AssertionError(f"unexpected url: {url}")

    with patch("src.threads_api.requests.get", side_effect=fake_get), \
         patch("src.threads_api.requests.post", side_effect=fake_post), \
         patch("src.threads_api.time.sleep", return_value=None):
        client = _client()
        try:
            client.post_with_reply("本文", "返信")
            assert False, "PartialPostError が発生するはず"
        except PartialPostError as e:
            assert e.post_id == "body_post_id"
    print("✓ 本文成功・返信失敗時は post_id 付きの PartialPostError になる")


if __name__ == "__main__":
    for fn in [
        test_publish_waits_for_finished_status,
        test_publish_raises_when_container_errors,
        test_post_with_reply_raises_partial_post_error_and_keeps_post_id,
    ]:
        fn()
    print("\nすべてのテストに合格しました。")

"""threads_api のモックテスト（実際のAPIは呼ばない）:
    python -m pytest tests/test_threads_api.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.threads_api import (  # noqa: E402
    PartialPostError,
    ThreadsAPIError,
    ThreadsClient,
    ThreadsError,
    describe_error,
)


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


def test_blocked_error_stops_immediately_without_retry():
    """code 200 (OAuthException "API access blocked") はリトライせず即座に例外になる."""
    call_count = {"n": 0}

    def fake_post(url, data=None, timeout=None):
        call_count["n"] += 1
        return FakeResponse(
            400,
            {
                "error": {
                    "message": "API access blocked.",
                    "type": "OAuthException",
                    "code": 200,
                    "fbtrace_id": "abc123",
                }
            },
        )

    with patch("src.threads_api.requests.post", side_effect=fake_post), \
         patch("src.threads_api.time.sleep", return_value=None) as sleep_mock:
        client = _client()
        try:
            client.create_container("テスト投稿")
            assert False, "ThreadsAPIError が発生するはず"
        except ThreadsAPIError as e:
            assert e.is_blocked
            assert e.code == 200
            assert e.fbtrace_id == "abc123"
    assert call_count["n"] == 1, "ブロック時はリトライしないはず"
    sleep_mock.assert_not_called()
    print("✓ code 200 (OAuthException) はリトライせず即座に停止する")


def test_rate_limit_error_is_retried_then_raised():
    """レート制限系(HTTP 429)はリトライしたうえで最終的に例外になる."""
    call_count = {"n": 0}

    def fake_post(url, data=None, timeout=None):
        call_count["n"] += 1
        return FakeResponse(429, {"error": {"message": "rate limited", "code": 4}}, text="rate limited")

    with patch("src.threads_api.requests.post", side_effect=fake_post), \
         patch("src.threads_api.time.sleep", return_value=None):
        client = _client()
        try:
            client.create_container("テスト投稿")
            assert False, "ThreadsError が発生するはず"
        except ThreadsError:
            pass
    assert call_count["n"] == 3, "429はretries回数だけ試行するはず"
    print("✓ 429はリトライしたうえで最終的に例外になる")


def test_other_client_error_parses_fields_and_does_not_retry():
    def fake_post(url, data=None, timeout=None):
        return FakeResponse(
            400,
            {
                "error": {
                    "message": "Object does not exist",
                    "type": "OAuthException",
                    "code": 100,
                    "error_subcode": 33,
                    "fbtrace_id": "xyz",
                }
            },
        )

    with patch("src.threads_api.requests.post", side_effect=fake_post) as post_mock, \
         patch("src.threads_api.time.sleep", return_value=None):
        client = _client()
        try:
            client.create_container("テスト投稿")
            assert False, "ThreadsAPIError が発生するはず"
        except ThreadsAPIError as e:
            assert e.code == 100
            assert e.error_subcode == 33
            assert e.fbtrace_id == "xyz"
            assert not e.is_blocked
    assert post_mock.call_count == 1, "リトライしても無駄な4xxは即座に停止するはず"
    print("✓ 4xxエラーの code/error_subcode/fbtrace_id を解析し、リトライしない")


def test_describe_error_maps_known_codes_to_japanese_guidance():
    blocked = ThreadsAPIError("blocked", code=200, error_type="OAuthException")
    assert "ブロック" in describe_error(blocked)

    id_issue = ThreadsAPIError("id issue", code=100, error_subcode=33)
    assert "権限" in describe_error(id_issue)

    rate = ThreadsAPIError("rate", code=17)
    assert "レート制限" in describe_error(rate)

    expired = ThreadsAPIError("expired", code=190, error_subcode=463)
    assert "トークン" in describe_error(expired)

    unknown = ThreadsAPIError("???", code=999)
    assert "未分類" in describe_error(unknown)
    print("✓ describe_error が主要なエラーコードを日本語ガイダンスに変換する")


if __name__ == "__main__":
    for fn in [
        test_publish_waits_for_finished_status,
        test_publish_raises_when_container_errors,
        test_post_with_reply_raises_partial_post_error_and_keeps_post_id,
        test_blocked_error_stops_immediately_without_retry,
        test_rate_limit_error_is_retried_then_raised,
        test_other_client_error_parses_fields_and_does_not_retry,
        test_describe_error_maps_known_codes_to_japanese_guidance,
    ]:
        fn()
    print("\nすべてのテストに合格しました。")

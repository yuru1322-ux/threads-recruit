"""cli diagnose のテスト（実際のAPIは呼ばない）:
    python -m pytest tests/test_cli_diagnose.py -q
"""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import cli, config  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or str(json_data)
        self.ok = status_code < 400

    def json(self):
        return self._json


def _with_fake_creds(fn):
    orig_token, orig_uid = config.THREADS_ACCESS_TOKEN, config.THREADS_USER_ID
    config.THREADS_ACCESS_TOKEN = "TOKEN"
    config.THREADS_USER_ID = "27984855431123122"
    try:
        fn()
    finally:
        config.THREADS_ACCESS_TOKEN, config.THREADS_USER_ID = orig_token, orig_uid


def test_diagnose_never_posts_and_reports_ok_when_read_succeeds():
    def run():
        def fake_get(url, params=None, timeout=None):
            return FakeResponse(200, {"id": "123", "username": "sample"})

        with patch("src.threads_api.requests.get", side_effect=fake_get), \
             patch("src.threads_api.requests.post") as post_mock:
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.cmd_diagnose(SimpleNamespace())
        assert code == 0
        assert "読み取りOK" in out.getvalue()
        assert "@sample" in out.getvalue()
        post_mock.assert_not_called()

    _with_fake_creds(run)
    print("✓ diagnose は投稿APIを一切呼ばず、読み取り成功時は終了コード0")


def test_diagnose_reports_blocked_error_details():
    def run():
        def fake_get(url, params=None, timeout=None):
            return FakeResponse(
                400,
                {
                    "error": {
                        "message": "API access blocked.",
                        "type": "OAuthException",
                        "code": 200,
                        "fbtrace_id": "abc",
                    }
                },
            )

        with patch("src.threads_api.requests.get", side_effect=fake_get):
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.cmd_diagnose(SimpleNamespace())
        text = out.getvalue()
        assert code == 1
        assert "code=200" in text
        assert "ブロック" in text

    _with_fake_creds(run)
    print("✓ ブロック中は code/error_subcode/message を整形して表示する")


if __name__ == "__main__":
    for fn in [
        test_diagnose_never_posts_and_reports_ok_when_read_succeeds,
        test_diagnose_reports_blocked_error_details,
    ]:
        fn()
    print("\nすべてのテストに合格しました。")

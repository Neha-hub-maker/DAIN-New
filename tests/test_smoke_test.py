"""Smoke CLI parsing and HTTP responses, entirely mocked with the standard library."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from email.message import Message
from http.client import BadStatusLine
import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from scripts import smoke_test


BASE = "https://dain-new.vercel.app"
ORIGIN = "https://neha-hub-maker.github.io"
TOKEN = "synthetic-session-token-never-print"
EMAIL = "student@cs.du.ac.bd"
REJECTION = {"status": "rejected", "reason": "insufficient_content", "claims": []}


def response(status=200, headers=None, body=b""):
    result = MagicMock()
    result.status = status
    result.headers = Message()
    for key, value in (headers or {}).items():
        result.headers[key] = value
    result.read.return_value = body
    result.__enter__.return_value = result
    return result


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.network_guard = patch("socket.create_connection", side_effect=AssertionError("Real network forbidden"))
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)
        self.env = patch.dict(os.environ, {"DAIN_SMOKE_TOKEN": TOKEN, "DAIN_SMOKE_EMAIL": EMAIL}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_cli(self, replies, args=None):
        output = io.StringIO()
        with patch.object(smoke_test, "build_opener") as opener, redirect_stdout(output):
            opener.return_value.open.side_effect = replies
            code = smoke_test.main(args or [BASE, ORIGIN])
        self.assertNotIn(TOKEN, output.getvalue())
        self.assertNotIn(EMAIL, output.getvalue())
        return code, output.getvalue(), opener.return_value.open.call_args_list

    def replies(self, rejection=REJECTION):
        return [response(), response(headers={"access-control-allow-origin": ORIGIN}), response(body=json.dumps(rejection).encode())]

    def test_success_constructs_exact_routes_preflight_and_authenticated_json(self):
        code, output, calls = self.run_cli(self.replies(), [f" {BASE}/// ", f" {ORIGIN}/// "])
        self.assertEqual(code, 0)
        self.assertEqual(output.count("PASS"), 3)
        requests = [call.args[0] for call in calls]
        self.assertEqual([(req.method, req.full_url) for req in requests], [
            ("GET", BASE + "/health"), ("OPTIONS", BASE + "/submissions/verify"), ("POST", BASE + "/submissions/verify"),
        ])
        preflight = {name.lower(): value for name, value in requests[1].header_items()}
        self.assertEqual(preflight["origin"], ORIGIN)
        self.assertEqual(preflight["access-control-request-method"], "POST")
        self.assertEqual(preflight["access-control-request-headers"], "Content-Type, Authorization")
        post = requests[2]
        self.assertEqual(post.get_header("Authorization"), f"Bearer {TOKEN}")
        self.assertEqual(post.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(post.data), smoke_test.gibberish_payload(EMAIL))
        self.assertEqual(smoke_test.gibberish_payload(EMAIL)["evidenceLink"], "")
        self.assertTrue(all(call.kwargs["timeout"] == 10 for call in calls))

    def test_origin_normalization(self):
        for raw, expected in [
            ("HTTPS://NEHA-HUB-MAKER.GITHUB.IO:443///", ORIGIN),
            ("http://localhost:3000/", "http://localhost:3000"),
            ("http://localhost:80/", "http://localhost"),
            ("http://[::1]:3000/", "http://[::1]:3000"),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(smoke_test.frontend_origin(raw), expected)

    def test_invalid_urls_and_origins_fail_without_network_or_echoing_secrets(self):
        for args in [
            ["api.example.test", ORIGIN], ["file:///tmp/site", ORIGIN],
            [f"https://user:{TOKEN}@api.example.test", ORIGIN],
            [f"{BASE}?key={TOKEN}", ORIGIN], [f"{BASE}#{TOKEN}", ORIGIN],
            ["https://api.example.test:bad", ORIGIN], [BASE, ORIGIN + "/repository"],
            [BASE, "null"], ["https://api.example.test/\npath", ORIGIN],
        ]:
            with self.subTest(args=args), patch.object(smoke_test, "build_opener") as opener:
                error_output = io.StringIO()
                with redirect_stderr(error_output), self.assertRaises(SystemExit) as exited:
                    smoke_test.main(args)
                self.assertEqual(exited.exception.code, 2)
                self.assertNotIn(TOKEN, error_output.getvalue())
                opener.assert_not_called()

    def test_health_failure_does_not_skip_other_checks(self):
        replies = self.replies()
        replies[0] = response(status=503)
        code, output, calls = self.run_cli(replies)
        self.assertEqual(code, 1)
        self.assertIn("FAIL health: HTTP 503", output)
        self.assertEqual(output.count("PASS"), 2)
        self.assertEqual(len(calls), 3)

    def test_preflight_requires_success_and_exact_origin(self):
        for status, allowed in [(403, ORIGIN), (200, "*"), (200, "https://other.example.test"), (200, None)]:
            with self.subTest(status=status, allowed=allowed):
                replies = self.replies()
                replies[1] = response(status=status, headers={} if allowed is None else {"Access-Control-Allow-Origin": allowed})
                code, output, _ = self.run_cli(replies)
                self.assertEqual(code, 1)
                self.assertIn("FAIL CORS preflight", output)

    def test_gibberish_requires_a_real_content_rejection(self):
        for body in [
            b"not JSON", b"[]", b"null", b"true", b"{}",
            b'{"status":"verified"}', b'{"status":"needs_review"}',
            b'{"status":"rejected","reason":"author_email_mismatch"}',
            b'{"status":"verification_pending","reason":"missing_api_key"}',
            json.dumps({"status": TOKEN, "reason": TOKEN}).encode(),
        ]:
            with self.subTest(body=body):
                replies = self.replies()
                replies[2] = response(body=body)
                code, output, _ = self.run_cli(replies)
                self.assertEqual(code, 1)
                self.assertIn("FAIL gibberish rejection", output)

    def test_http_errors_do_not_print_server_bodies_or_reasons(self):
        replies = self.replies()
        replies[2] = HTTPError(BASE, 401, TOKEN, Message(), io.BytesIO(TOKEN.encode()))
        code, output, _ = self.run_cli(replies)
        self.assertEqual(code, 1)
        self.assertIn("FAIL gibberish rejection: HTTP 401", output)

    def test_network_and_timeout_errors_are_redacted_and_checks_continue(self):
        for index in range(3):
            for error in [URLError(TOKEN), TimeoutError(TOKEN), BadStatusLine(TOKEN)]:
                with self.subTest(index=index, error=type(error).__name__):
                    replies = self.replies()
                    replies[index] = error
                    code, output, calls = self.run_cli(replies)
                    self.assertEqual(code, 1)
                    self.assertIn("Network error or timeout", output)
                    self.assertEqual(len(calls), 3)

    def test_missing_auth_fails_only_the_gibberish_check(self):
        with patch.dict(os.environ, {}, clear=True):
            code, output, calls = self.run_cli(self.replies())
        self.assertEqual(code, 1)
        self.assertIn("Set DAIN_SMOKE_TOKEN and DAIN_SMOKE_EMAIL", output)
        self.assertEqual(len(calls), 2)

    def test_redirects_are_not_followed_with_a_token(self):
        redirect = smoke_test.NoRedirects().redirect_request(Request(BASE), None, 302, TOKEN, {}, "https://other.example.test")
        self.assertIsNone(redirect)


if __name__ == "__main__":
    unittest.main()

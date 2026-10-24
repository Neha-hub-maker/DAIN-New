"""Check health, CORS and local gibberish rejection without provider API keys.

Usage: python scripts/smoke_test.py <backend_url> <frontend_origin>
The authenticated third check reads DAIN_SMOKE_TOKEN and DAIN_SMOKE_EMAIL from
the operator's environment; neither value is ever printed or written to disk.
"""

from __future__ import annotations

import argparse
from http.client import HTTPException
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


VERIFICATION_PATH = "/submissions/verify"
TIMEOUT_SECONDS = 10


def backend_url(value: str) -> str:
    """Accept an HTTP(S) base URL, never credentials, queries or fragments."""
    value = value.strip().rstrip("/")
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or any(char.isspace() for char in value)
        ):
            raise ValueError
        parsed.port  # Validate the port without contacting the host.
    except ValueError:
        raise argparse.ArgumentTypeError("Use an HTTP(S) URL without credentials, query or fragment.") from None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def frontend_origin(value: str) -> str:
    """Normalize an origin as a browser does; repository paths are not origins."""
    parsed = urlsplit(backend_url(value))
    if parsed.path:
        raise argparse.ArgumentTypeError("The frontend origin must not include a path.")
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    if port is not None and (parsed.scheme, port) not in {("http", 80), ("https", 443)}:
        host = f"{host}:{port}"
    return f"{parsed.scheme}://{host}"


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirect must not turn the POST into a GET or forward its token.
        return None


def request(method: str, url: str, headers: dict[str, str], payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with build_opener(NoRedirects()).open(req, timeout=TIMEOUT_SECONDS) as response:
            return response.status, response.headers, response.read(1_048_576)
    except HTTPError as error:
        # Error bodies/reasons can contain secrets: only return the numeric status.
        error.close()
        return error.code, error.headers, b""


def gibberish_payload(email: str) -> dict[str, str]:
    return {
        "headline": "CCCCCCCCCCCC",
        "summary": "CCCCCCCCCCCC CCCCCCCCCCCC CCCCCCCCCCCC",
        "category": "Academic", "subType": "Smoke test",
        "institution": "University of Dhaka", "impact": "", "evidenceLink": "",
        "achievementDate": "2000-01-01", "authorEmail": email,
    }


def run_checks(base: str, origin: str, token: str, email: str) -> int:
    failures = 0

    def report(name, check):
        nonlocal failures
        try:
            passed, detail = check()
        except (OSError, URLError, TimeoutError, HTTPException):
            passed, detail = False, "Network error or timeout"
        except (ValueError, TypeError):
            passed, detail = False, "Invalid response"
        failures += not passed
        print(f"{'PASS' if passed else 'FAIL'} {name}: {detail}")

    def health():
        status, _, _ = request("GET", f"{base}/health", {})
        return status == 200, f"HTTP {status}"

    def preflight():
        status, headers, _ = request("OPTIONS", f"{base}{VERIFICATION_PATH}", {
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization",
        })
        matches = headers.get("Access-Control-Allow-Origin") == origin
        return 200 <= status < 300 and matches, f"HTTP {status}; allowed origin {'matches' if matches else 'does not match'}"

    def gibberish():
        if not token or not email:
            return False, "Set DAIN_SMOKE_TOKEN and DAIN_SMOKE_EMAIL for a verified user"
        if any(char.isspace() for char in token) or "\r" in email or "\n" in email:
            return False, "Invalid smoke-test authentication configuration"
        status, _, body = request("POST", f"{base}{VERIFICATION_PATH}", {
            "Origin": origin, "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }, gibberish_payload(email))
        if status != 200:
            return False, f"HTTP {status}; expected authenticated local content rejection"
        result = json.loads(body)
        # Identity rejection alone must not produce a false positive.
        passed = isinstance(result, dict) and result.get("status") == "rejected" and result.get("reason") == "insufficient_content"
        return passed, "Local pre-check rejected gibberish" if passed else "Expected rejected with reason insufficient_content"

    report("health", health)
    report("CORS preflight", preflight)
    report("gibberish rejection", gibberish)
    return int(failures > 0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend_url", type=backend_url)
    parser.add_argument("frontend_origin", type=frontend_origin)
    args = parser.parse_args(argv)
    return run_checks(
        args.backend_url, args.frontend_origin,
        os.environ.get("DAIN_SMOKE_TOKEN", "").strip(),
        os.environ.get("DAIN_SMOKE_EMAIL", "").strip(),
    )


if __name__ == "__main__":
    raise SystemExit(main())

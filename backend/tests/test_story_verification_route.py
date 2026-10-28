"""Story verification contracts with the paid service mocked throughout."""

import asyncio
import importlib.util
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from uvicorn import Config

from app.core.config import Settings
from app.db.session import SessionLocal
from app.main import app
from app.models.dain import User
from app.routes import dain
from app.services import achievement_verification, rate_limit
from app.services.rate_limit import IPRateLimiter
from app.services.security import hash_password


ENDPOINT = "/submissions/verify"
EMAIL = "student@cs.du.ac.bd"
CLAIM = {"text": "The team won the award.", "verdict": "verified", "confidence": 0.9, "sources": ["https://news.example.org/award"]}


def story_payload(**overrides):
    payload = {
        "headline": "Dhaka University team wins robotics award",
        "summary": "A Dhaka University team won the national robotics award with their rescue robot.",
        "category": "Academic",
        "subType": "Awards",
        "institution": "University of Dhaka",
        "impact": "First place",
        "evidenceLink": "https://news.example.org/award",
        "achievementDate": "2024-06-01",
        "authorEmail": EMAIL,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def mocked_verifier(monkeypatch):
    mock = AsyncMock(return_value={"status": "verified", "reason": "claims_verified", "claims": [CLAIM]})
    monkeypatch.setattr(achievement_verification, "verify_achievement", mock)
    monkeypatch.setattr(dain, "story_verification_limiter", IPRateLimiter())
    return mock


@pytest.fixture
def auth_headers(client):
    database = SessionLocal()
    try:
        database.add(User(
            email=EMAIL, full_name="Test Student", password_hash=hash_password("secure-password-123"),
            is_email_verified=True,
        ))
        database.commit()
    finally:
        database.close()
    login = client.post("/auth/login", json={"email": EMAIL, "password": "secure-password-123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.parametrize("verification_status,editorial_status,routing_status", [
    ("verified", "passed", "passed"),
    ("rejected", "failed", "skipped"),
    ("needs_review", "held", "skipped"),
    ("verification_pending", "held", "skipped"),
])
def test_verification_status_maps_to_exact_response(client, auth_headers, mocked_verifier, verification_status, editorial_status, routing_status):
    claims = [] if verification_status == "verification_pending" else [CLAIM]
    mocked_verifier.return_value = {"status": verification_status, "reason": "test_reason", "claims": claims}
    response = client.post(ENDPOINT, headers=auth_headers, json=story_payload())
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "reason", "claims", "stages"}
    assert body["status"] == verification_status
    assert body["reason"] == "test_reason"
    assert body["claims"] == claims
    assert [(stage["id"], stage["status"]) for stage in body["stages"]] == [
        ("identity", "passed"), ("editorial", editorial_status), ("routing", routing_status),
    ]
    for stage in body["stages"]:
        assert set(stage) == {"id", "status", "detail"}
        assert isinstance(stage["detail"], str) and stage["detail"]
    mocked_verifier.assert_awaited_once_with(
        headline=story_payload()["headline"], summary=story_payload()["summary"],
        sector="Academic", classification="Awards", institution="University of Dhaka",
        primary_metric="First place", evidence_link="https://news.example.org/award",
        achievement_date=date(2024, 6, 1),
    )
    assert "author_email" not in mocked_verifier.call_args.kwargs
    assert EMAIL not in str(mocked_verifier.call_args)


def test_snake_case_field_names_are_supported(client, auth_headers, mocked_verifier):
    payload = story_payload()
    for form_name, service_name in {
        "category": "sector", "subType": "classification", "impact": "primary_metric",
        "evidenceLink": "evidence_link", "achievementDate": "achievement_date", "authorEmail": "author_email",
    }.items():
        payload[service_name] = payload.pop(form_name)
    assert client.post(ENDPOINT, headers=auth_headers, json=payload).status_code == 200
    mocked_verifier.assert_awaited_once()


@pytest.mark.parametrize("status,editorial,routing", [("needs_review", "held", "skipped"), ("verified", "passed", "passed")])
def test_unreadable_link_note_keeps_claim_evidence_and_correct_stages(client, auth_headers, mocked_verifier, status, editorial, routing):
    reason = "insufficient_evidence; evidence_link_unreadable" if status == "needs_review" else "claims_verified; evidence_link_unreadable"
    claim = {**CLAIM, "verdict": "unverified" if status == "needs_review" else "verified", "confidence": 0.6 if status == "needs_review" else 0.9}
    mocked_verifier.return_value = {"status": status, "reason": reason, "claims": [claim]}

    response = client.post(ENDPOINT, headers=auth_headers, json=story_payload())

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "reason", "claims", "stages"}
    assert body["status"] == status and body["reason"] == reason and body["claims"] == [claim]
    assert [(stage["id"], stage["status"]) for stage in body["stages"]] == [
        ("identity", "passed"), ("editorial", editorial), ("routing", routing),
    ]


@pytest.mark.parametrize("email,reason", [("student@example.org", "invalid_institutional_email"), ("other@mis.du.ac.bd", "author_email_mismatch")])
def test_failed_identity_skips_paid_verification(client, auth_headers, mocked_verifier, email, reason):
    response = client.post(ENDPOINT, headers=auth_headers, json=story_payload(authorEmail=email))
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["reason"] == reason
    assert response.json()["claims"] == []
    assert [stage["status"] for stage in response.json()["stages"]] == ["failed", "skipped", "skipped"]
    mocked_verifier.assert_not_awaited()


def test_identity_reuses_configured_institutional_verifier(client, auth_headers, mocked_verifier, monkeypatch):
    monkeypatch.setattr(dain.settings, "institutional_email_domain", "another.example.org")
    response = client.post(ENDPOINT, headers=auth_headers, json=story_payload())
    assert response.json()["reason"] == "invalid_institutional_email"
    mocked_verifier.assert_not_awaited()


@pytest.mark.parametrize("authorization", [None, "Bearer invalid-token"])
def test_authentication_required_before_paid_calls(client, mocked_verifier, authorization):
    headers = {"Authorization": authorization} if authorization else {}
    assert client.post(ENDPOINT, headers=headers, json=story_payload()).status_code == 401
    mocked_verifier.assert_not_awaited()


def test_unverified_account_cannot_spend_credits(client, auth_headers, mocked_verifier):
    database = SessionLocal()
    try:
        user = database.query(User).filter_by(email=EMAIL).one()
        user.is_email_verified = False
        database.commit()
    finally:
        database.close()
    assert client.post(ENDPOINT, headers=auth_headers, json=story_payload()).status_code == 403
    mocked_verifier.assert_not_awaited()


def test_rate_limit_returns_429_before_sixth_paid_call(client, auth_headers, mocked_verifier, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(rate_limit, "monotonic", lambda: clock[0])
    for _ in range(5):
        assert client.post(ENDPOINT, headers=auth_headers, json=story_payload()).status_code == 200
    limited = client.post(ENDPOINT, headers=auth_headers, json=story_payload())
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"
    assert mocked_verifier.await_count == 5
    clock[0] += 60
    assert client.post(ENDPOINT, headers=auth_headers, json=story_payload()).status_code == 200
    assert mocked_verifier.await_count == 6


def test_ip_limit_cannot_be_bypassed_by_forwarding_headers(client, auth_headers, mocked_verifier):
    for number in range(6):
        headers = {**auth_headers, "X-Forwarded-For": f"198.51.100.{number}", "X-Real-IP": f"198.51.100.{number}"}
        response = client.post(ENDPOINT, headers=headers, json=story_payload())
        assert response.status_code == (200 if number < 5 else 429)
    assert mocked_verifier.await_count == 5


def test_limits_are_independent_per_ip(client, auth_headers, mocked_verifier):
    async def run():
        for address in ("198.51.100.1", "198.51.100.2"):
            transport = httpx.ASGITransport(app=app, client=(address, 50000))
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as peer:
                for _ in range(5):
                    assert (await peer.post(ENDPOINT, headers=auth_headers, json=story_payload())).status_code == 200
                assert (await peer.post(ENDPOINT, headers=auth_headers, json=story_payload())).status_code == 429
    asyncio.run(run())
    assert mocked_verifier.await_count == 10


@pytest.mark.parametrize("client_ips", [
    ("203.0.113.1", "203.0.113.2"),
    ("2001:db8::1", "2001:db8::2"),
])
def test_trusted_proxy_preserves_separate_client_limits(auth_headers, mocked_verifier, monkeypatch, client_ips):
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "198.51.100.0/24")
    config = Config(app, proxy_headers=True, log_config=None)
    config.load()

    async def run():
        transport = httpx.ASGITransport(app=config.loaded_app, client=("198.51.100.10", 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as peer:
            for address in client_ips:
                # Include a second trusted proxy in the chain, as hosts may do.
                headers = {
                    **auth_headers,
                    "Origin": "http://localhost:3000",
                    "X-Forwarded-For": f"{address}, 198.51.100.11",
                }
                for _ in range(5):
                    assert (await peer.post(ENDPOINT, headers=headers, json=story_payload())).status_code == 200
                limited = await peer.post(ENDPOINT, headers=headers, json=story_payload())
                assert limited.status_code == 429
                assert int(limited.headers["Retry-After"]) > 0
                assert limited.headers["access-control-allow-origin"] == "http://localhost:3000"

    asyncio.run(run())
    assert mocked_verifier.await_count == 10


@pytest.mark.parametrize("peer_ip,forwarded_suffix", [
    ("203.0.113.50", ""),  # A direct/untrusted peer cannot set its own address.
    ("198.51.100.10", ", 203.0.113.50, 198.51.100.11"),  # Ignore forged leftmost entries.
])
def test_proxy_headers_cannot_rotate_a_callers_rate_limit(auth_headers, mocked_verifier, monkeypatch, peer_ip, forwarded_suffix):
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "198.51.100.0/24")
    config = Config(app, proxy_headers=True, log_config=None)
    config.load()

    async def run():
        transport = httpx.ASGITransport(app=config.loaded_app, client=(peer_ip, 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as peer:
            for number in range(6):
                headers = {
                    **auth_headers,
                    "X-Forwarded-For": f"192.0.2.{number + 1}{forwarded_suffix}",
                    "X-Real-IP": f"192.0.2.{number + 1}",
                }
                response = await peer.post(ENDPOINT, headers=headers, json=story_payload())
                assert response.status_code == (200 if number < 5 else 429)

    asyncio.run(run())
    assert mocked_verifier.await_count == 5


@pytest.mark.parametrize("field,size", [("headline", 121), ("summary", 601), ("subType", 121), ("institution", 201), ("impact", 201)])
def test_oversize_text_is_422_without_paid_calls(client, auth_headers, mocked_verifier, field, size):
    response = client.post(ENDPOINT, headers=auth_headers, json=story_payload(**{field: "অ" * size}))
    assert response.status_code == 422
    mocked_verifier.assert_not_awaited()


def test_oversize_evidence_url_is_422(client, auth_headers, mocked_verifier):
    response = client.post(ENDPOINT, headers=auth_headers, json=story_payload(evidenceLink="https://example.org/" + "a" * 2048))
    assert response.status_code == 422
    mocked_verifier.assert_not_awaited()


@pytest.mark.parametrize("changes", [
    {"headline": "short"}, {"summary": "too short"}, {"subType": "  "}, {"institution": "  "},
    {"authorEmail": "not-an-email"}, {"category": "unknown"}, {"achievementDate": "not-a-date"},
    {"evidenceLink": "file:///etc/passwd"}, {"evidenceLink": "javascript:alert(1)"},
])
def test_invalid_form_fields_are_422(client, auth_headers, mocked_verifier, changes):
    assert client.post(ENDPOINT, headers=auth_headers, json=story_payload(**changes)).status_code == 422
    mocked_verifier.assert_not_awaited()


def test_optional_form_fields_accept_empty_strings(client, auth_headers, mocked_verifier):
    response = client.post(ENDPOINT, headers=auth_headers, json=story_payload(evidenceLink="", impact=""))
    assert response.status_code == 200
    assert mocked_verifier.call_args.kwargs["evidence_link"] is None
    assert mocked_verifier.call_args.kwargs["primary_metric"] == ""


def test_smoke_script_payload_is_rejected_without_provider_calls(client, auth_headers, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts" / "smoke_test.py"
    spec = importlib.util.spec_from_file_location("dain_smoke_script", path)
    smoke_script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke_script)
    no_network = AsyncMock(side_effect=AssertionError("Gibberish must never call providers"))
    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    monkeypatch.setattr(dain, "story_verification_limiter", IPRateLimiter())

    response = client.post(ENDPOINT, headers=auth_headers, json=smoke_script.gibberish_payload(EMAIL))

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["reason"] == "insufficient_content"
    assert response.json()["stages"][0]["status"] == "passed"
    no_network.assert_not_awaited()


def test_exact_form_length_limits_are_accepted(client, auth_headers, mocked_verifier):
    response = client.post(ENDPOINT, headers=auth_headers, json=story_payload(
        headline="অ" * 120, summary="অ" * 600, subType="অ" * 120,
        institution="অ" * 200, impact="অ" * 200,
    ))
    assert response.status_code == 200
    mocked_verifier.assert_awaited_once()


def test_openapi_publishes_form_aliases_limits_and_auth():
    schema = app.openapi()
    properties = schema["components"]["schemas"]["StoryVerificationRequest"]["properties"]
    assert set(properties) == set(story_payload())
    assert properties["headline"]["maxLength"] == 120
    assert properties["summary"]["maxLength"] == 600
    assert schema["paths"][ENDPOINT]["post"]["security"] == [{"HTTPBearer": []}]


@pytest.mark.parametrize("origin,expected", [("http://localhost:3000", 200), ("http://127.0.0.1:3000", 200), ("null", 400), ("https://untrusted.example.org", 400)])
def test_cors_for_served_frontend_and_file_origin(client, mocked_verifier, origin, expected):
    response = client.options(ENDPOINT, headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert response.status_code == expected
    if expected == 200:
        assert response.headers["access-control-allow-origin"] == origin
        assert "authorization" in response.headers["access-control-allow-headers"].lower()
    else:
        assert "access-control-allow-origin" not in response.headers
    mocked_verifier.assert_not_awaited()


def test_example_cors_uses_the_github_pages_origin_without_a_path():
    path = Path(__file__).resolve().parents[1] / ".env.example"
    configured = Settings(_env_file=path)
    assert configured.cors_origin_list == ["https://neha-hub-maker.github.io"]

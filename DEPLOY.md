# Deployment

The API uses Python **3.12.14** in both Render and Docker. Keep these pins together:
`psycopg[binary]==3.2.3` does not provide Python 3.14 wheels. No credentials belong
in Git, HTML, or a committed environment file. Configure secrets in the host dashboard.

## Dashboard settings

`render.yaml` declares the template variables except `PORT`, which Render supplies
automatically. Entries with
`sync: false` must be supplied through the dashboard; secret values are never in
the Blueprint. The safe defaults below are already declared in the Blueprint.

| Variables | What to configure |
| --- | --- |
| `DATABASE_URL` | Your managed PostgreSQL connection URI, preferably the Render internal URL when colocated. `postgres://` and `postgresql://` are normalized to `postgresql+psycopg://`. URL-encode credentials; retain required TLS query parameters. |
| `GROQ_API_KEY`, `TAVILY_API_KEY` | Dashboard secrets from [Groq](https://console.groq.com/keys) and [Tavily](https://app.tavily.com). Missing keys hold valid submissions as `verification_pending`. |
| `GROQ_MODEL` | Default `openai/gpt-oss-120b`; ensure it is available to your account. |
| `CORS_ORIGINS` | Comma-separated HTTPS frontend origins: scheme + hostname + optional port, without paths. Whitespace/trailing slashes are stripped and empty entries ignored. Do not use `*` or `null`. Local launch scripts use `http://localhost:3000`. |
| `FORWARDED_ALLOW_IPS` | Uvicorn's comma-separated trusted ingress proxy IPs/CIDRs, obtained from the host. Required on Render; its startup command fails if this is empty. Docker/Compose default to loopback only for direct local use. Set the actual ingress addresses for hosted containers. |
| `PORT` | Supplied by Render: do not replace it with a fixed dashboard value. Docker/Compose default to 8000 and respect overrides; Uvicorn always binds `0.0.0.0:$PORT`. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`, `SMTP_USE_SSL` | Your email provider's hostname, login, secret and authorized sender. Default port 587 with STARTTLS (`SMTP_USE_SSL=false`); use port 465 with `true` for implicit TLS. Required for production registration/verification emails. |
| `APP_ENV`, `DEBUG`, `EXPOSE_VERIFICATION_TOKEN_IN_RESPONSE` | Keep `production`, `false`, `false`. Never expose email verification codes in production responses. |
| `INSTITUTIONAL_EMAIL_DOMAIN` | Default `du.ac.bd`, including departmental subdomains. |
| `VERIFICATION_TOKEN_TTL_MINUTES`, `SESSION_TOKEN_TTL_MINUTES` | Defaults 60 and 1440. |
| `MEDIA_ROOT`, `MAX_UPLOAD_SIZE_BYTES` | `/var/data/uploads`, 5242880 bytes. The Blueprint attaches a 1 GiB disk at `/var/data`, requiring a paid Render service. |
| `PYTHON_VERSION` | Render runtime pin `3.12.14`. |
| `POSTGRES_PASSWORD` | Local Compose only; unused by the hosted API. For Compose, supply this and a matching `DATABASE_URL` through your shell or private configuration outside Git. Use host `db:5432`, database `dain`, user `dain_user`. |

## Deployment order

1. Provision PostgreSQL, a persistent media disk and the email provider. Choose the
   public frontend origin. Obtain the host's ingress proxy IPs/CIDRs and confirm
   how it sanitizes/appends `X-Forwarded-For`; these cannot be inferred offline.
2. Import `render.yaml` and fill in the dashboard settings **before deployment**:
   database, SMTP, provider keys, frontend CORS origins and trusted proxy addresses.
   Keep the production safety defaults. Let the host supply `PORT`.
3. Deploy the backend from `backend/`. Startup must complete, in order:
   `alembic upgrade head` → `python -m app.db.seed` → Uvicorn with `--host 0.0.0.0`,
   `--port "$PORT"`, `--proxy-headers`, `--forwarded-allow-ips "$FORWARDED_ALLOW_IPS"`.
   The `&&` chain stops startup and logs an error if migrations cannot connect or
   seeding fails; it never serves an unmigrated app. Back up an existing database
   before upgrading. Do not suppress migration errors or use `--sql` on deployment.
4. Confirm the process-only `/health` returns HTTP 200 with `status: "ok"` and the
   host routes to it. It never touches the database, Groq or Tavily. A healthy
   response alone does not establish database/provider availability; check the
   migration logs and authenticated API smoke tests separately.
5. In `index.html`, replace the clearly marked `DEPLOYED_API_BASE` placeholder with
   the API's HTTPS base URL (no `/docs` suffix), or insert a script assigning
   `window.DAIN_API_BASE` **before** the application script. This public URL is the
   only frontend configuration; never include keys. The localhost fallback is only
   used on `localhost`, `127.0.0.1`, or `[::1]`. A remaining placeholder emits a
   console warning. Static hosts do not substitute dashboard env vars into HTML.
6. Publish the frontend. Confirm a JSON POST preflight to `/submissions/verify`
   succeeds from its exact origin, allowing `POST`, `OPTIONS`, `Content-Type` and
   `Authorization`. Then run the authenticated smoke tests below. For Docker, the
   same migrations/seeding run before Uvicorn. Compose waits for PostgreSQL
   readiness and stores database/media in named volumes. CI needs no env file.

Uvicorn converts `X-Forwarded-For` to the ASGI client address only when the
connecting peer is trusted. The route limits that resolved address, never raw
forwarding headers. For multiple proxies, list all trusted hops; Uvicorn selects
the first untrusted address from the right, avoiding caller-injected leftmost
addresses. Do not set `FORWARDED_ALLOW_IPS=*` on a directly reachable backend.
Wildcard trust is appropriate only if the host guarantees every connection comes
from trusted ingress and sanitizes client-supplied forwarding headers. Confirm
this with the host rather than guessing a production trust range.

A placeholder API URL or an HTTP API on an HTTPS frontend prevents connectivity;
configure the actual HTTPS base URL, without `/docs`. A 401/403 with CORS headers
means authentication is required; a 429 means a rate-limit bucket was exhausted.
Neither is a CORS failure. Confirm the deployed artifact contains the configured
URL and the host dashboard contains the frontend origin and proxy trust setting.

## Post-deploy smoke tests

Run the standard-library connectivity script from the repository root:

```text
python scripts/smoke_test.py <backend_url> <frontend_origin>
```

Use the backend's public HTTP(S) base URL and the frontend's origin without a
repository path. Set `DAIN_SMOKE_TOKEN` to an existing verified user's login
session token and `DAIN_SMOKE_EMAIL` to that account's email in the process
environment before running; no environment file or Groq/Tavily keys are needed.
Do not put a token in the command arguments or commit it. With missing auth,
health/CORS still run and the third check reports FAIL with setup instructions.

The script prints PASS/FAIL for health (HTTP 200), the JSON/Bearer OPTIONS
preflight's exact allowed origin, and authenticated gibberish rejection. It exits
nonzero on any failure and never prints credentials, response bodies or raw
network exceptions. Redirects are refused to avoid forwarding a session token.
The gibberish check requires reason `insufficient_content`, so an identity
rejection cannot falsely pass. It uses no Groq/Tavily credits, but counts as one
request against the five-per-minute verification limit.

These are operator steps; they were **not run against live providers** for this PR.
The two real-story tests spend provider credits. Use `/docs` to register a DU
account, complete `/auth/verify-email` with the code received by email, log in,
and authorize with the returned Bearer token. Do not enable debug/token exposure
to bypass email verification. Also confirm an unauthenticated verification request
returns 401 and a CORS preflight from the deployed frontend permits its origin and
the `Authorization`/`Content-Type` headers.

POST `/submissions/verify` with the story fields: `headline` (10–120), `summary`
(30–600), `category` (e.g. `Academic`), `subType`, `institution`, `impact`,
`achievementDate` (past ISO date), `authorEmail` (the authenticated DU email), and
`evidenceLink` (HTTPS URL, or `""` when absent). Use genuine, specific achievements
for cases 2 and 3; public evidence is assessed, never assumed to exist.

| Case | Input | Expected result |
| --- | --- | --- |
| 1. Gibberish | Headline `CCCCCCCCCCCC`; summary `CCCCCCCCCCCC CCCCCCCCCCCC CCCCCCCCCCCC`; all other required fields valid. | HTTP 200, `rejected`, reason `insufficient_content`, editorial `failed`, routing `skipped`. No Groq/Tavily calls. |
| 2. Real story with a link | A coherent achievement and a genuine public evidence URL. | Structured `claims` and three `stages`; `verified` only when every claim is verified with confidence ≥0.7. Insufficient evidence may yield `needs_review`; contradicted evidence yields `rejected`. |
| 3. Real story without a link | A coherent achievement with `evidenceLink: ""`. | Search still runs. `unverified` is normal and yields `needs_review`, not a falsehood/rejection. A fully evidenced result may be `verified`. |

For either real story, `verification_pending` means check provider keys, quotas,
timeouts or availability. Only `verified` may have routing `passed`; other results
remain unpublished. The per-IP limit is five verification requests per minute
(HTTP 429 with `Retry-After`); space out retries.

## Current application limits

The static UI still has demo sessions and localStorage stories/editor approvals;
these are not server authorization or durable publication. Its registration view
does not complete email verification; use the API flow above for authenticated
smoke tests. Do not treat this deployment configuration as completion of those
product workflows. The API verification limiter is process-local; keep one worker
and instance until a shared limiter is added for scaling.

## Offline regression checks

```bash
python -m unittest discover -s tests -p 'test_smoke_test.py'
node --test tests/*.test.cjs
node --test tests/verification.browser.cjs
```

The browser suite uses Playwright and Chromium, which must already be installed
in the test environment. It uses a system `/usr/bin/chromium` when available,
otherwise Playwright's installed Chromium; `DAIN_CHROMIUM_PATH` can select another
browser executable. Every HTTP request is intercepted, including assets, health
and verification requests. Smoke-script tests mock HTTP and prohibit sockets.

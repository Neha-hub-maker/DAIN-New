# Deployment

The API uses Python **3.12.14** in both Render and Docker. Keep these pins together:
`psycopg[binary]==3.2.3` does not provide Python 3.14 wheels. No credentials belong
in Git, HTML, or a committed environment file. Configure secrets in the host dashboard.

## Dashboard settings

`render.yaml` declares every variable in `backend/.env.example`. Entries with
`sync: false` must be supplied through the dashboard; secret values are never in
the Blueprint. The safe defaults below are already declared in the Blueprint.

| Variables | What to configure |
| --- | --- |
| `DATABASE_URL` | Your managed PostgreSQL connection URI, preferably the Render internal URL when colocated. `postgres://` and `postgresql://` are normalized to `postgresql+psycopg://`. URL-encode credentials; retain required TLS query parameters. |
| `GROQ_API_KEY`, `TAVILY_API_KEY` | Dashboard secrets from [Groq](https://console.groq.com/keys) and [Tavily](https://app.tavily.com). Missing keys hold valid submissions as `verification_pending`. |
| `GROQ_MODEL` | Default `openai/gpt-oss-120b`; ensure it is available to your account. |
| `CORS_ORIGINS` | Comma-separated exact HTTPS frontend origins: scheme + hostname + optional port, without paths or trailing slashes. Spaces/blank entries are ignored. Do not use `*` or `null`. Local launch scripts use `http://localhost:3000`. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`, `SMTP_USE_SSL` | Your email provider's hostname, login, secret and authorized sender. Default port 587 with STARTTLS (`SMTP_USE_SSL=false`); use port 465 with `true` for implicit TLS. Required for production registration/verification emails. |
| `APP_ENV`, `DEBUG`, `EXPOSE_VERIFICATION_TOKEN_IN_RESPONSE` | Keep `production`, `false`, `false`. Never expose email verification codes in production responses. |
| `INSTITUTIONAL_EMAIL_DOMAIN` | Default `du.ac.bd`, including departmental subdomains. |
| `VERIFICATION_TOKEN_TTL_MINUTES`, `SESSION_TOKEN_TTL_MINUTES` | Defaults 60 and 1440. |
| `MEDIA_ROOT`, `MAX_UPLOAD_SIZE_BYTES` | `/var/data/uploads`, 5242880 bytes. The Blueprint attaches a 1 GiB disk at `/var/data`, requiring a paid Render service. |
| `PYTHON_VERSION` | Render runtime pin `3.12.14`. |
| `POSTGRES_PASSWORD` | Local Compose only; unused by the hosted API. For Compose, supply this and a matching `DATABASE_URL` through your shell or private configuration outside Git. Use host `db:5432`, database `dain`, user `dain_user`. |

## Deployment order

1. Provision a managed PostgreSQL database and configure the email provider. Choose
   the public frontend origin before configuring CORS.
2. Import `render.yaml` as a Render Blueprint and set the dashboard variables above.
   Render builds from `backend/`. Startup runs `alembic upgrade head`, idempotent
   category seeding, then Uvicorn bound to `0.0.0.0:$PORT`. Migration failure stops
   startup. Back up an existing database before schema upgrades.
3. Check that Render's `/health` probe returns HTTP 200 with `status: "ok"`.
   This endpoint checks the database with `SELECT 1`; it never calls Groq/Tavily.
4. In `index.html`, replace the clearly marked `DEPLOYED_API_BASE` placeholder with
   the API's HTTPS base URL (no `/docs` suffix), or insert a script assigning
   `window.DAIN_API_BASE` **before** the application script. This public URL is the
   only frontend configuration; never include keys. The localhost fallback is only
   used on `localhost`, `127.0.0.1`, or `[::1]`. A remaining placeholder emits a
   console warning. Static hosts do not substitute dashboard env vars into HTML.
5. Publish the static frontend, confirm its exact origin is in `CORS_ORIGINS`, and
   run the smoke tests below. For Docker, the same migrations/seeding run before
   Uvicorn; `PORT` defaults to 8000. Compose waits for PostgreSQL readiness and
   stores database/media in named volumes. No environment file is required by CI.

## Post-deploy smoke tests

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

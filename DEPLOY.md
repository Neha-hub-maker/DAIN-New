# Deployment

This repository has two deployments:

- Frontend: https://neha-hub-maker.github.io/DAIN-New/ — root `index.html` and
  `api-config.js`, published by `.github/workflows/deploy.yml` on every push to
  `main`. GitHub Pages uses the Actions workflow, not a separate frontend host.
- Backend: https://dain-new.vercel.app — this repository's `backend/` FastAPI app,
  including `POST /submissions/verify`. Set the Vercel project's **Root Directory
  to `backend`** and use its FastAPI/Python deployment support for `app/main.py`.

`api-config.js` sets `window.DAIN_API_BASE = "https://dain-new.vercel.app"` before
`index.html` starts the application. Keep this origin without a trailing slash or
API path. No provider keys or database credentials belong in frontend files.

## Vercel dashboard settings

Set these for the backend's production environment. Environment changes require
**a redeploy** before a running deployment uses them. Turn **Deployment Protection
off for the API** so cross-origin health requests and OPTIONS preflights are not
blocked by a platform sign-in page. Backend authentication remains required.

| Variable | Value or source |
| --- | --- |
| `DATABASE_URL` | Managed PostgreSQL connection URI from the database provider; store privately in the dashboard. URL-encode credentials and retain required TLS parameters. Standard PostgreSQL URLs select the installed psycopg 3 driver. |
| `GROQ_API_KEY` | Dashboard secret from https://console.groq.com/keys. |
| `TAVILY_API_KEY` | Dashboard secret from https://app.tavily.com. |
| `GROQ_MODEL` | `openai/gpt-oss-120b`. |
| `CORS_ORIGINS` | `https://neha-hub-maker.github.io` — origin only, **no `/DAIN-New/` path**. Comma-separated additional origins are supported when needed; whitespace/trailing slashes are removed. |
| `APP_ENV` | `production`. |
| `DEBUG` | `false`. |
| `EXPOSE_VERIFICATION_TOKEN_IN_RESPONSE` | `false`. Verification codes must be delivered through email. |
| `INSTITUTIONAL_EMAIL_DOMAIN` | `du.ac.bd`; departmental subdomains are accepted. |
| `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM` | Your email provider's hostname, login, private password/app token and authorized sender. Required for production registration. |
| `SMTP_PORT`, `SMTP_USE_SSL` | Provider settings: normally 587 / `false` for STARTTLS, or 465 / `true` for implicit TLS. |
| `VERIFICATION_TOKEN_TTL_MINUTES`, `SESSION_TOKEN_TTL_MINUTES` | Defaults 60 and 1440. |
| `MEDIA_ROOT`, `MAX_UPLOAD_SIZE_BYTES` | `/tmp/dain-uploads`, 5242880. Vercel's temporary files are ephemeral and not shared durable media storage. |

Select a compatible Python runtime (3.12 or 3.13) in Vercel's project settings.
`psycopg[binary]==3.2.3` has no Python 3.14 wheels. The local Docker image remains
pinned to Python 3.12.14. The example template is `backend/.env.example`; do not
commit environment files or credentials.

`POSTGRES_PASSWORD`, `PORT` and `FORWARDED_ALLOW_IPS` in that template are for local
Compose/Docker/Uvicorn only, not Vercel dashboard requirements. Compose needs a
private database password and a matching `DATABASE_URL` using host `db:5432`, user
`dain_user`, database `dain`. Its port defaults to 8000. Trust only known local
proxy addresses when using Uvicorn; Vercel manages the production function listener.

## Deployment order

1. Provision PostgreSQL and SMTP delivery. Configure the Vercel project from this
   repository with **Root Directory = `backend`**, the dashboard variables above,
   a compatible Python runtime and API Deployment Protection off.
2. Migrate the database once before serving requests. From a trusted environment
   with `DATABASE_URL` set privately, run from `backend/`:

   ```bash
   python -m pip install -r requirements.txt
   python -m alembic upgrade head
   python -m app.db.seed
   ```

   Do not run migrations per serverless invocation or suppress connection errors.
   Run `alembic upgrade head` again for later schema changes; back up existing data
   before upgrades. No database connection or migration was run against production
   while preparing these changes.
3. Deploy/redeploy the Vercel backend. Check `https://dain-new.vercel.app/health`
   for process liveness. Check `https://dain-new.vercel.app/health/ready` for database
   readiness: HTTP 200 contains `database: "ok"` and key-presence booleans; HTTP 503
   contains only `database: "unavailable"`. Readiness never contacts Groq/Tavily or
   returns exception text, database URLs or keys. A configured key is not proof
   that a provider account/quota works.
4. Merge the frontend configuration to `main`. GitHub Actions automatically
   publishes `index.html`, `api-config.js` and assets to the GitHub Pages address
   above. There is no frontend build-time secret substitution. Confirm the new
   artifact loads `api-config.js` relative to `/DAIN-New/`.
5. Run the smoke checks below. A platform login/redirect means API Deployment
   Protection must be disabled. HTTP 401/403 with CORS headers means backend
   authentication is required; HTTP 429 means a rate limit, not a CORS failure.

## Smoke tests

With an existing verified DU user's session token in `DAIN_SMOKE_TOKEN` and the
matching email in `DAIN_SMOKE_EMAIL`, run from the repository root:

```bash
python scripts/smoke_test.py https://dain-new.vercel.app https://neha-hub-maker.github.io
```

Do not put tokens in command arguments, Git or environment files. The script uses
only Python's standard library, prints PASS/FAIL for health, a JSON/Bearer OPTIONS
preflight to `/submissions/verify`, and authenticated gibberish rejection, and
exits nonzero on failure. With missing auth the third check fails with setup
instructions. It never prints tokens, response bodies or raw exceptions, and
refuses redirects. An identity rejection cannot falsely pass the content check.

For manual checks, register, verify the emailed code and log in through the UI or
`/docs`; never enable debug/token exposure to bypass verification. Submit valid
form fields and a past achievement date:

| Case | Expected result |
| --- | --- |
| Gibberish: headline `CCCCCCCCCCCC`, summary `CCCCCCCCCCCC CCCCCCCCCCCC CCCCCCCCCCCC`. | `rejected`, reason `insufficient_content`, no Groq/Tavily calls. The script exercises this exact pre-check. |
| A genuine achievement with a public evidence link. | Claims and stages; only sufficiently evidenced claims produce `verified`. Otherwise `needs_review`, or `rejected` for contradictions. |
| A genuine achievement with an empty evidence link. | Search still runs. `unverified` means `needs_review`, not false. Fully evidenced claims may still be `verified`. |

Real-story checks use provider credits and were not performed here. Missing keys,
provider errors or deadlines yield `verification_pending`; only verified content
passes routing. The gibberish check uses no provider credits but counts toward
five verification requests per minute per IP.

## Serverless limits

Vercel has request time limits depending on the plan and function configuration.
Ensure its function duration supports the verifier's 25-second overall timeout;
the frontend waits up to 40 seconds. A platform timeout may occur first and must
leave the story Pending Review. These limits were not checked against the live
project.

The in-memory limiter may be shared across requests using one warm function (and
clients presented with the same proxy IP). It resets on cold starts and is not a
global quota across function instances. Its current behavior is unchanged. Durable
media storage and shared rate limiting need separate work for scaling. Static
stories/editor approvals remain browser-local prototype workflows.

## Offline regression checks

```bash
python -m unittest discover -s tests -p 'test_smoke_test.py'
node --test tests/*.test.cjs
node --test tests/verification.browser.cjs
cd backend
.venv/bin/python -m pytest -q tests
```

The browser suite requires installed Playwright and Chromium; `DAIN_CHROMIUM_PATH`
can select an installed browser executable. All HTTP, including requests using the
production addresses, is intercepted in browser/smoke tests. Provider HTTP is
mocked in backend tests; local SQLite is used instead of a production database.

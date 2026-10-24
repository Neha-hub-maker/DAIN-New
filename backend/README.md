# DAIN Developer A backend MVP

Backend-only implementation for DAIN (DUNITE Achievement & Impact Network). It covers the Developer A scope: database infrastructure, institutional-email verification prototype, authentication, submission routing, secure uploads, editorial APIs, automated validation, duplicate flags, and media-ready web-package generation. No frontend is included.

## What this MVP does

1. A member registers with an address at `INSTITUTIONAL_EMAIL_DOMAIN` or one of its subdomains (for example, `du.ac.bd`, `cs.du.ac.bd`, or `mis.du.ac.bd`).
2. The member verifies a one-time, expiring email token, then logs in with an opaque Bearer token.
3. A verified member creates a draft in an Academic, Startup, or Social Impact category, attaches links/files, and submits it.
4. DAIN records completeness warnings and likely title duplicates without automatically blocking the member.
5. An editor/admin reviews the submission, approves/rejects it, and may generate an approved story as a shareable web page.

## Important institutional-verification limitation

The current DU domain/subdomain check plus one-time token is an **institutional-email verification prototype**. It is not real DUNITE Auth, DUNITE SSO, or OIDC. No DUNITE integration credentials/specification were provided. The prototype boundary is isolated in `app/services/institutional_verification.py`, so an approved DUNITE integration can replace it later.

Production registration requires SMTP delivery configured through the host dashboard. For local testing only, use `DEBUG=true` and `EXPOSE_VERIFICATION_TOKEN_IN_RESPONSE=true`; registration will then return a one-time token. Never enable this in a deployed environment. See [DEPLOY.md](../DEPLOY.md) for the deployment sequence and all settings.

## Windows local setup

### 1. Install prerequisites

- Python 3.12 (the deployment pin is 3.12.14): verify with `py --version`
- PostgreSQL 16 or newer: verify with `psql --version`

### 2. Create the database

Open **SQL Shell (psql)** as a PostgreSQL administrator and run:

```sql
CREATE USER dain_user WITH PASSWORD 'replace-with-a-long-unique-password';
CREATE DATABASE dain OWNER dain_user;
```

### 3. Configure the project

From PowerShell:

```powershell
Set-Location "C:\Users\IT\Documents\Codex\2026-08-25\you-are-my-senior-backend-engineer"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`. At minimum, set the password and the confirmed institutional domain:

```env
DATABASE_URL=postgresql+psycopg://dain_user:replace-with-a-long-unique-password@localhost:5432/dain
INSTITUTIONAL_EMAIL_DOMAIN=du.ac.bd
APP_ENV=development
DEBUG=true
EXPOSE_VERIFICATION_TOKEN_IN_RESPONSE=true
MEDIA_ROOT=uploads
MAX_UPLOAD_SIZE_BYTES=5242880
```

### 4. Initialize the schema and seed categories

```powershell
python -m alembic upgrade head
python -m app.db.seed
```

The initial migration creates the DAIN schema. The seed command adds the three official MVP categories and their example dynamic fields:

- Academic: publication/evidence link
- Startup: funding amount
- Social Impact: impact measure

### 5. Run tests and the API

```powershell
python -m pytest -q
python -m uvicorn app.main:app --reload
```

From the repository root, run `node --test tests/email-validation.test.cjs` to check frontend email validation across registration, login, and story submission. These checks use Node's built-in test runner and require no npm packages.

Open `http://127.0.0.1:8000/docs`. `GET /health` checks the configured PostgreSQL connection.

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL SQLAlchemy URL; never commit its password. |
| `INSTITUTIONAL_EMAIL_DOMAIN` | Allowed root domain and its subdomains for the prototype, currently `du.ac.bd`. |
| `APP_ENV` | Environment label. |
| `DEBUG` | Enables development-only behavior; keep `false` in deployment. |
| `VERIFICATION_TOKEN_TTL_MINUTES` | One-time verification token lifetime; default `60`. |
| `SESSION_TOKEN_TTL_MINUTES` | Opaque Bearer token lifetime; default `1440`. |
| `EXPOSE_VERIFICATION_TOKEN_IN_RESPONSE` | Local-only prototype switch; default `false`. |
| `MEDIA_ROOT` | Directory for MVP file uploads and generated HTML. |
| `MAX_UPLOAD_SIZE_BYTES` | Maximum upload size; default 5 MB. |
| `CORS_ORIGINS` | Comma-separated frontend origins. The launch scripts use `http://localhost:3000`; the example also permits `http://127.0.0.1:3000`. |

## API summary

| Method | Endpoint | Authentication | Purpose |
|---|---|---|---|
| POST | `/auth/register` | None | Register an institutional account. |
| POST | `/auth/verify-email` | None | Verify a one-time email token. |
| POST | `/auth/resend-verification` | None | Request a replacement verification token. |
| POST | `/auth/login` | None | Log in a verified user. |
| POST | `/auth/logout` | Bearer | Revoke the current session. |
| GET | `/auth/me` | Verified Bearer | Read the safe profile. |
| GET | `/categories` | Verified Bearer | Fetch active dynamic-form categories and fields. |
| POST | `/categories` | Admin | Create a category and its dynamic fields. |
| POST | `/submissions` | Verified Bearer | Create a draft. |
| POST | `/submissions/verify` | Verified Bearer | Verify a story form and return identity, editorial, and routing stages. |
| GET | `/submissions` | Verified Bearer | List own submissions; editors/admins see all. |
| GET | `/submissions/{id}` | Owner/editor/admin | Read a submission. |
| POST | `/submissions/{id}/links` | Draft owner | Add a supporting URL. |
| POST | `/submissions/{id}/assets` | Draft owner | Upload JPEG, PNG, WEBP, or PDF evidence. |
| GET | `/assets/{id}` | Owner/editor/admin | Download an authorized evidence file. |
| POST | `/submissions/{id}/submit` | Draft owner | Run validation and submit for review. |
| GET | `/submissions/{id}/validation` | Owner/editor/admin | Read validation results. |
| GET | `/editor/submissions` | Editor/admin | View the editorial queue. |
| POST | `/submissions/{id}/reviews` | Editor/admin | Approve, reject, or request changes. |
| POST | `/submissions/{id}/media-package` | Editor/admin | Generate an approved package. |
| GET | `/packages/{slug}` | None | Read a generated, approved media-ready page. |

The interactive OpenAPI page at `/docs` shows the exact request and response shapes.

### Story verification

`POST /submissions/verify` takes the token returned by `/auth/login` in `Authorization: Bearer <token>`. The author email must pass the existing configured DU domain/subdomain check and match the verified account. Identity failures return `rejected`, with editorial/routing skipped and no paid verification call. The endpoint checks a form draft without saving or publishing it.

Use the form's JSON field names, or the corresponding snake_case service names:

| Form field | Service name | Limits |
|---|---|---|
| `headline` | `headline` | 10–120 characters |
| `summary` | `summary` | 30–600 characters |
| `category` | `sector` | Academic, Professional, Entrepreneurial, Social Impact, or Personal |
| `subType` | `classification` | 1–120 characters |
| `institution` | `institution` | 1–200 characters |
| `impact` | `primary_metric` | Optional, up to 200 characters |
| `evidenceLink` | `evidence_link` | Optional HTTP(S) URL, up to 2048 characters; empty is accepted |
| `achievementDate` | `achievement_date` | Required ISO date (`YYYY-MM-DD`) |
| `authorEmail` | `author_email` | Valid email, up to 254 characters |

Headline and summary limits match the HTML form. Other text fields have server-side caps because the current form does not declare `maxlength` for them. The author email is used locally and is excluded from the fields passed to Groq/Tavily.

The response always has `status`, `reason`, `claims`, and three `stages`, in identity/editorial/routing order. Each claim has `text`, `verdict`, `confidence`, and `sources`; each stage has `id`, `status`, and `detail`. Editorial is `passed` for verified content, `failed` for rejected content, and `held` for needs-review or pending results. Routing is `passed` only when verified; it means ready for routing, without performing distribution.

Authenticated requests with a valid body are limited to five per IP in a sliding 60-second window. Excess requests return HTTP 429 and `Retry-After` before paid calls. Client forwarding headers do not select the IP; configure trusted proxy handling at the server when deploying behind a proxy. The simple limiter is process-local and resets on restart. Multiple workers/replicas would need a shared limiter for a global quota.

Both `Launch_DAIN_Platform.bat` and `Launch_FullStack.bat` start Python's static server on port 3000 and open `http://localhost:3000/index.html`. `Launch_DAIN_Dev.bat` launches development tools only. Use the HTTP URL for development: opening the HTML directly produces the unsupported `null` origin. `backend/.env.example` lists the supported development origins; the default configuration has no CORS wildcard. No real `.env` is needed for route tests.

## Security notes

- Passwords use Argon2 hashes; plaintext passwords are never persisted or returned.
- Session and verification tokens use cryptographic randomness; only SHA-256 token hashes are stored.
- Authentication and authorization are distinct dependencies. Editor/admin endpoints enforce roles.
- Files have a 5 MB configurable limit, allowed MIME types, content-signature checks, generated storage keys, and authorization checks on download.
- User input is escaped before rendering media-package HTML.
- Upload storage is local-disk MVP storage. Use managed object storage, malware scanning, and backup/retention controls before production.

## Validation and AI

Validation checks required dynamic fields and detects likely duplicate titles using normalized-text similarity. Results are stored and flagged for human review; they do not automatically reject or block a story.

The optional achievement verifier uses Groq for claim extraction/assessment and Tavily for search and evidence-link extraction. `GROQ_API_KEY` and `TAVILY_API_KEY` default to empty strings; missing keys yield `verification_pending`. `GROQ_MODEL` defaults to `openai/gpt-oss-120b`. Provider errors and the overall 25-second timeout also yield a pending result. Route tests mock the verifier, and service tests mock HTTP; neither needs real credentials or network access.

## Docker deployment

Docker is provided for a small demonstration deployment, not production hardening.

1. Supply `POSTGRES_PASSWORD` and a matching `DATABASE_URL` in your shell or private configuration outside Git. For Compose use host `db:5432`, database `dain`, and user `dain_user`; URL-encode the password in the URI. Compose runs in development mode with response verification tokens exposed; use the production settings in [DEPLOY.md](../DEPLOY.md) for hosting.
2. Run:

```powershell
docker compose up --build
```

The API container runs the initial migration and category seed before starting. Production deployment still requires HTTPS/reverse proxy configuration, real DUNITE authentication, approved email delivery, managed media storage, database backups, secret management, and monitoring.

# DAIN Developer A backend MVP

Backend-only implementation for DAIN (DUNITE Achievement & Impact Network). It covers the Developer A scope: database infrastructure, institutional-email verification prototype, authentication, submission routing, secure uploads, editorial APIs, automated validation, duplicate flags, and media-ready web-package generation. No frontend is included.

## What this MVP does

1. A member registers with an address matching `INSTITUTIONAL_EMAIL_DOMAIN`.
2. The member verifies a one-time, expiring email token, then logs in with an opaque Bearer token.
3. A verified member creates a draft in an Academic, Startup, or Social Impact category, attaches links/files, and submits it.
4. DAIN records completeness warnings and likely title duplicates without automatically blocking the member.
5. An editor/admin reviews the submission, approves/rejects it, and may generate an approved story as a shareable web page.

## Important institutional-verification limitation

The current `@du.ac.bd` check plus one-time token is an **institutional-email verification prototype**. It is not real DUNITE Auth, DUNITE SSO, or OIDC. No DUNITE integration credentials/specification were provided. The prototype boundary is isolated in `app/services/institutional_verification.py`, so an approved DUNITE integration can replace it later.

There is also no email-delivery provider in this MVP. For local testing only, use `DEBUG=true` and `EXPOSE_VERIFICATION_TOKEN_IN_RESPONSE=true`; registration will then return a one-time token. Never enable this in a deployed environment.

## Windows local setup

### 1. Install prerequisites

- Python 3.11 or newer: verify with `py --version`
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
py -3.11 -m venv .venv
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

Open `http://127.0.0.1:8000/docs`. `GET /health` checks the configured PostgreSQL connection.

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL SQLAlchemy URL; never commit its password. |
| `INSTITUTIONAL_EMAIL_DOMAIN` | Allowed domain for the prototype, currently `du.ac.bd`. |
| `APP_ENV` | Environment label. |
| `DEBUG` | Enables development-only behavior; keep `false` in deployment. |
| `VERIFICATION_TOKEN_TTL_MINUTES` | One-time verification token lifetime; default `60`. |
| `SESSION_TOKEN_TTL_MINUTES` | Opaque Bearer token lifetime; default `1440`. |
| `EXPOSE_VERIFICATION_TOKEN_IN_RESPONSE` | Local-only prototype switch; default `false`. |
| `MEDIA_ROOT` | Directory for MVP file uploads and generated HTML. |
| `MAX_UPLOAD_SIZE_BYTES` | Maximum upload size; default 5 MB. |

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

## Security notes

- Passwords use Argon2 hashes; plaintext passwords are never persisted or returned.
- Session and verification tokens use cryptographic randomness; only SHA-256 token hashes are stored.
- Authentication and authorization are distinct dependencies. Editor/admin endpoints enforce roles.
- Files have a 5 MB configurable limit, allowed MIME types, content-signature checks, generated storage keys, and authorization checks on download.
- User input is escaped before rendering media-package HTML.
- Upload storage is local-disk MVP storage. Use managed object storage, malware scanning, and backup/retention controls before production.

## Validation and AI

Validation checks required dynamic fields and detects likely duplicate titles using normalized-text similarity. Results are stored and flagged for human review; they do not automatically reject or block a story.

No LLM, Hugging Face, or external AI API is implemented. The probationary task makes AI integrations optional (“if you plan to use LLMs”), so no external AI keys or unreliable AI dependency were added.

## Docker deployment

Docker is provided for a small demonstration deployment, not production hardening.

1. Put `POSTGRES_PASSWORD` and `INSTITUTIONAL_EMAIL_DOMAIN` in `.env`.
2. Run:

```powershell
docker compose up --build
```

The API container runs the initial migration and category seed before starting. Production deployment still requires HTTPS/reverse proxy configuration, real DUNITE authentication, approved email delivery, managed media storage, database backups, secret management, and monitoring.

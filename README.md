# Reasonbook

**Fraud prevention application for federal and state grants.**

Reasonbook captures the full lifecycle of grant and entitlement funding decisions
as a tamper-evident, auditable record. Risk signals become alerts, alerts become
decisions, decisions are claimed, finalized, and tied to matters and awards — and
every lifecycle event is written into a **hash-chained integrity ledger** that any
reviewer can re-walk from genesis to prove nothing was altered after the fact.

It runs as a **single container**: a Python/Flask API that also serves a React/
TypeScript single-page app, backed by SQLite out of the box (PostgreSQL optional),
with ingestion running in-process on a schedule. No external services are required.

---

## What it does

- **Decision lifecycle** — signal → owner → decision → action → outcome, with
  claim/finalize/defer/escalate transitions, attachments, comments, and an export.
- **Matters & awards** — the federal → state → recipient fund-flow spine that
  decisions attach to, with control-point adherence.
- **Alerts & signals** — a signal/alert ledger that promotes risk signals into
  decisions, deduplicated per interval.
- **Oversight & findings** — oversight cycles, evidence links, and findings.
- **Hash-chained integrity** — every `decision_events` row is chained with
  SHA-256 (`prev_hash`, `hash`); `verify_chain()` and `scripts/verify_integrity.py`
  detect any tampering, including re-chain forgery attempts.
- **USAspending CSV import** — load public agency/recipient data into the catalog.
- **Connector framework** — a declarative connector surface (USAspending is the
  one live path in v1.0; see Roadmap).
- **Single-admin local auth** — JWT sessions (30-minute lifetime), bcrypt password
  hashing, account lockout.
- **Local-storage attachments** — files on a local volume by default, S3-compatible
  object storage optional.

## Data source (v1.0)

Reasonbook ships a declarative connector framework and a **USAspending CSV
importer**. SAM.gov, HHS-OIG LEIE, the Treasury Do Not Pay family (including the
Death Master File), and IRS/Census/CMS feeds are **on the roadmap** — the
risk-signal vocabulary and the program/archetype config for them are present, but
no live clients for those sources are included in v1.0.

> The CSVs bundled in [`data/`](data/) are a **point-in-time snapshot** of public
> USAspending data, included so the app has a working catalog out of the box.
> **Refresh them with current data before relying on the catalog:** download new
> exports from [USAspending.gov](https://www.usaspending.gov/), keep the same
> filenames in `data/`, and re-run `python -m scripts.import_usaspending --all`
> (the importer is idempotent). See [`data/README.md`](data/README.md).

---

## Quick start

### Docker (recommended)

```bash
# Generate a signing secret (required — no default ships in code).
export REASONBOOK_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")

# Optionally create a first-run admin (password is printed once to the logs).
export REASONBOOK_ADMIN_EMAIL=admin@example.org

docker compose up --build
```

The login page serves at <http://localhost:8000>. The API health check is at
<http://localhost:8000/api/health>. Data (the SQLite file + attachments) lives on
the `reasonbook-data` volume. To use PostgreSQL instead, see
[DEPLOY.md](DEPLOY.md).

### Local development (no Docker)

Backend:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
export REASONBOOK_SECRET_KEY=dev-only-secret
alembic upgrade head
flask --app reasonbook.app run --port 8000
```

Frontend (served separately by Vite in dev):

```bash
cd web
pnpm install
pnpm dev        # http://localhost:5173, proxying /api to the backend
```

To build the SPA into the Python package (as the Docker image does):

```bash
cd web && pnpm build   # output copied to reasonbook/static/web by the image build
```

---

## Configuration

All settings come from environment variables prefixed `REASONBOOK_` (the
unprefixed `DATABASE_URL` is accepted as an alias). See
[`.env.example`](.env.example) for the full list. Highlights:

| Variable | Default | Notes |
|---|---|---|
| `REASONBOOK_SECRET_KEY` | _(none)_ | **Required in production.** JWT signing key; fails fast if unset. |
| `REASONBOOK_DATABASE_URL` | `sqlite:///reasonbook.db` | PostgreSQL via `postgresql+psycopg://…` (install `[postgres]`). |
| `REASONBOOK_JWT_TTL_MINUTES` | `30` | Session token lifetime. |
| `REASONBOOK_ATTACHMENT_BACKEND` | `local` | `s3` for S3-compatible object storage. |
| `REASONBOOK_RUN_SCHEDULER` | `true` | In-process ingestion scheduler (one process only). |
| `REASONBOOK_SMTP_HOST` | _(empty)_ | Optional; links logged to stdout in dev when unset. |
| `REASONBOOK_ADMIN_EMAIL` | _(empty)_ | First-run admin bootstrap. |
| `REASONBOOK_SEED_DEMO` | `false` | Create NON-PRODUCTION demo accounts (needs `REASONBOOK_SEED_PASSWORD`). |

Full deployment guidance — PostgreSQL, the SQLite single-writer limit, the
SQLite→PostgreSQL migration procedure, scheduler semantics, egress, and the
self-hosted-fonts option — is in [DEPLOY.md](DEPLOY.md).

---

## Testing

```bash
pytest                 # SQLite (default)
# PostgreSQL:
REASONBOOK_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/db pytest
cd web && pnpm test    # frontend unit tests (Vitest)
```

---

## Roadmap

- Connectors: SAM.gov, HHS-OIG LEIE, Treasury Do Not Pay (incl. the Death Master
  File), IRS 4506-C, Census population, CMS feeds.
- A Celery + Redis "scale" profile for high write-concurrency / multi-node deploys.
- Server-side token revocation (a denylist).
- Login rate limiting.

## Known limitations (v1.0)

- **JWT sessions are stateless** with a 30-minute lifetime. Logout clears the
  client cookie only — there is **no server-side token revocation list**. A token
  remains valid until it expires. (Revocation is on the roadmap.)
- **No login rate limiting.** Brute-force protection relies on **account lockout**
  (consecutive-failure based), which is active. Rate limiting is on the roadmap.
- **SQLite is single-writer.** It is safe for a small team plus the 5-minute
  ingestion batch (WAL + busy-timeout + retry). For high write-concurrency or
  multi-node deployments, set `REASONBOOK_DATABASE_URL` to PostgreSQL (see
  [DEPLOY.md](DEPLOY.md)).
- **SMTP is optional.** When unset, verification/reset links are logged to stdout
  in development; the email-dependent flows are disabled in production.

---

## Built by

Created by Christopher Johnson.

## License

Apache License 2.0. Copyright 2026 Data Visuals LLC. See [LICENSE](LICENSE),
[NOTICE](NOTICE), and [SECURITY.md](SECURITY.md).

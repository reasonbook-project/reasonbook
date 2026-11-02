# Deploying Reasonbook

Reasonbook is a single container: a Flask API that also serves the built React
SPA, with ingestion running in-process. SQLite is the default database;
PostgreSQL is optional. This guide covers a plain Docker deploy.

---

## 1. Plain Docker

```bash
export REASONBOOK_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
docker compose up --build -d
```

- Serves the UI and API at **http://localhost:8000**.
- Health check: `GET /api/health` (used by the container `HEALTHCHECK`).
- Data (SQLite file + attachments) persists on the `reasonbook-data` volume.
- The container runs as a **non-root** user, exposes **one port (8000)**, and
  contains **no Node runtime, no tests, no `.git`, and no `.env`** — only the
  compiled SPA bundle and the Python app.

The entrypoint runs `alembic upgrade head` on every start (idempotent), then
starts gunicorn with `--workers 1`.

### Build + run without compose

```bash
docker build -t reasonbook:1.0.0 .
docker run -d --name reasonbook \
  -p 8000:8000 \
  -e REASONBOOK_SECRET_KEY="$REASONBOOK_SECRET_KEY" \
  -v reasonbook-data:/data \
  reasonbook:1.0.0
```

A reverse proxy is **not** required — Flask serves the SPA directly. Add one only
for TLS termination.

---

## 2. Environment variables

The full list is in [`.env.example`](.env.example). All variables are prefixed
`REASONBOOK_` (the unprefixed `DATABASE_URL` is accepted as an alias).

**Fail-fast:** in production (`REASONBOOK_FLASK_ENV=production`, the image
default) the app refuses to start if `REASONBOOK_SECRET_KEY` is empty. There are
**no default secrets in the code.**

---

## 3. First-run admin bootstrap

Set `REASONBOOK_ADMIN_EMAIL`. On startup the entrypoint creates that admin if it
does not exist and prints a generated password **once** to the container logs:

```bash
docker compose logs reasonbook | grep -A4 "first-run admin"
```

Re-runs are a no-op (no new password is printed). You can also run it manually:

```bash
docker compose exec reasonbook python -m scripts.bootstrap_admin
```

### Create the admin in a running container (no redeploy)

If the app is already running without `REASONBOOK_ADMIN_EMAIL` set — so no admin
exists and you can't log in — open a shell in the running container (e.g. your
platform's **Console**, or `docker compose exec reasonbook sh`) and run the
bootstrap with the email inline:

```bash
REASONBOOK_ADMIN_EMAIL=you@example.org python -m scripts.bootstrap_admin
```

It creates the admin in the live database and prints the generated password
once. **Log in with that email as the username.** This avoids a redeploy; it
writes to whatever database the running instance is using.

> On a platform with an ephemeral filesystem using the default SQLite (see §4),
> an admin created this way is wiped on the next redeploy/restart. Set
> `REASONBOOK_ADMIN_EMAIL` as a persistent env var (so it's recreated each
> deploy), and use PostgreSQL if you need the account and data to persist.

---

## 4. Database

### 4.1 SQLite (default) and the single-writer limit

SQLite is the default (`sqlite:////data/reasonbook.db`). The engine is configured
with `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`, and the ingestion
job retries on "database is locked" with backoff. This makes SQLite **safe for a
small team plus the 5-minute ingestion batch** — write contention is seconds-rare.

SQLite serializes writers with a single database-level write lock, so only one
write transaction commits at a time. This is **not** suitable for high
write-concurrency or multi-node deployments — use PostgreSQL for those.

> **Persistence on ephemeral-filesystem platforms (PaaS / serverless containers).**
> Many managed container platforms give the app an **ephemeral filesystem** that
> is wiped on every redeploy, restart, or scale event. The SQLite file lives on
> that filesystem, so **your data will not survive a redeploy there.** On such a
> platform, either (a) attach a **persistent volume mounted at `/data`**, or
> (b) use **PostgreSQL** (§4.2) by setting `REASONBOOK_DATABASE_URL` — a managed
> Postgres instance is the simplest option. A long-lived host or VM with a mounted
> volume (e.g. `docker compose up` on a server) keeps SQLite perfectly; it is only
> the stateless/ephemeral-disk platforms that need a volume or PostgreSQL.

### 4.2 PostgreSQL (optional)

Start the bundled PostgreSQL service with the `postgres` profile, then point the
app at it:

```bash
docker compose --profile postgres up --build -d
# then set on the reasonbook service (see docker-compose.yml comments):
#   REASONBOOK_DATABASE_URL=postgresql+psycopg://reasonbook:reasonbook@postgres:5432/reasonbook
```

The same models and the same `0001_initial` migration run on both dialects (CI
verifies migrations + the full test suite on `sqlite://` and a PostgreSQL
service). On PostgreSQL the tables live in a `platform` schema; on SQLite they are
flat — handled transparently by a schema-translate map.

### 4.3 SQLite → PostgreSQL migration procedure

This has been validated once with sample data. The schema is identical across
dialects, so the data can be copied row-for-row.

1. Stand up PostgreSQL and create the schema:
   ```bash
   docker compose --profile postgres up -d postgres
   REASONBOOK_DATABASE_URL=postgresql+psycopg://reasonbook:reasonbook@localhost:5432/reasonbook \
     alembic upgrade head
   ```
2. Copy the data with a short script that reads every table from the SQLite
   engine and bulk-inserts into the PostgreSQL engine in FK-dependency order
   (parents before children). The generic column types (`Uuid`, `JSON`,
   `DateTime`) round-trip cleanly between the two.
3. Verify the hash chain end-to-end on the new database:
   ```bash
   REASONBOOK_DATABASE_URL=postgresql+psycopg://…  python scripts/verify_integrity.py
   ```
   A non-zero exit means the chain did not verify — do not cut over.
4. Repoint `REASONBOOK_DATABASE_URL` at PostgreSQL and restart.

---

## 5. Ingestion scheduler

Ingestion runs **in-process** on an APScheduler `BackgroundScheduler` started by
the app factory — no external task queue, no message broker, no separate worker process. It fires every
`REASONBOOK_INGESTION_INTERVAL_MINUTES` (default **5**), reads the local `pipe_*`
staging tables, evaluates triggers, and creates/deduplicates decisions.

**One-process requirement (hard):** the scheduler must run in exactly one process.
Under gunicorn with N workers, N schedulers would each fire the job. The image
runs `--workers 1` for this reason. To scale web workers, run the scheduler as a
separate `--workers 1` process (or a sidecar) and set
`REASONBOOK_RUN_SCHEDULER=false` on the extra web workers. `max_instances=1` +
`coalesce=True` also guarantee a slow run never overlaps itself.

The `pipe_*` tables are Reasonbook's **local ingestion staging tables**: the CSV
upload path writes one row per period into them, and the scheduler reads the
latest period per workflow. There is no external producer.

---

## 6. Demo seed accounts (and how to disable them)

Demo accounts are **NON-PRODUCTION** fictional identities on `example.org`
addresses. They are created **only** when `REASONBOOK_SEED_DEMO=true`, and seeding
fails loudly unless `REASONBOOK_SEED_PASSWORD` is set — there is no shipped
password constant.

- **Disable (default):** leave `REASONBOOK_SEED_DEMO` unset or `false`.
- **Enable for a demo:**
  ```bash
  REASONBOOK_SEED_DEMO=true REASONBOOK_SEED_PASSWORD=choose-a-demo-password \
    docker compose up --build
  ```

Never enable demo seeding in a production deployment.

---

## 7. Outbound egress

Reasonbook makes **no outbound calls at runtime** except to:

- the configured **database** (SQLite file, or PostgreSQL if configured), and
- the optional **SMTP** server (only when `REASONBOOK_SMTP_HOST` is set), and
- the optional **S3-compatible** object store (only when
  `REASONBOOK_ATTACHMENT_BACKEND=s3`).

With none of those configured for a remote host, the container can run fully
network-isolated against a local SQLite volume. The web UI loads fonts from Google
Fonts by default (a CDN request from the **browser**, not the server) — see §8 to
remove that for air-gapped deployments.

---

## 8. Self-hosted fonts (air-gapped)

The SPA imports Inter / Space Grotesk / IBM Plex Mono from the Google Fonts CDN
(`web/src/index.css`, first line). For air-gapped agencies, remove that `@import`
and either (a) self-host the woff2 files under `web/public/fonts/` and `@font-face`
them, or (b) fall back to the system font stack already defined in the CSS. Rebuild
the image after the change.

---

## 9. SMTP (optional)

Email verification and password reset need SMTP. When `REASONBOOK_SMTP_HOST` is
unset:

- in **development**, the verification/reset links are logged to stdout, and
- in **production**, the email-dependent flows are disabled.

No SMTP host default ships in the code.

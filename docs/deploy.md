# Deployment runbook

Roadmap Stage 13 ("hardening and go-live readiness"). Everything below has been proven
against a local Postgres instance where that's possible without real infrastructure (see
`specs/state.md`'s Stage 13 log entry for exactly what was executed and shown, versus
what's still a human task). Nothing here has been run against a real production host —
there isn't one yet.

Every credential-shaped value below is an obvious placeholder in angle brackets
(`<R2_ACCESS_KEY>`) or an unmistakably fake domain (`example.com`). Replace them; do not
copy them as-is.

---

## 1. Server prerequisites

- A host running PostgreSQL **18.4** and Python **3.11** (the versions this project is
  built and tested against — CLAUDE.md).
- `postgresql-client` installed so `pg_dump`/`pg_restore`/`psql` are on `PATH` (needed by
  `core/backup.py`'s nightly job — `BACKUP_PG_DUMP_PATH` only needs overriding if they
  aren't).
- Caddy 2.x installed as the only public-facing process (CLAUDE.md: "Front door: Caddy").
- A real domain, with DNS already pointed at the server, before Caddy is started —
  automatic HTTPS needs to actually reach Let's Encrypt's HTTP-01/TLS-ALPN challenge.
- A Cloudflare R2 bucket and API token (§2.5 / Stage 12's `R2MediaStorage`).

## 2. Database setup

```bash
sudo -u postgres createdb ecommerce
sudo -u postgres psql -d ecommerce -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

Migrations run as the **owner** role (`postgres`, or a dedicated admin role — this repo
doesn't create one; use whatever already administers the box):

```bash
DATABASE_URL="postgres://postgres:<OWNER_DB_PASSWORD>@localhost:5432/ecommerce" \
  DJANGO_SETTINGS_MODULE=config.settings.prod \
  python manage.py migrate
```

Then create the least-privilege **runtime** role the running application actually
connects as (`deploy/create_app_role.sql` — read that file's own header comment before
running it; it's idempotent but not silent about it):

```bash
psql "postgres://postgres:<OWNER_DB_PASSWORD>@localhost:5432/ecommerce" \
  -v app_password="<ECOMMERCE_APP_DB_PASSWORD>" -v owner_role="postgres" \
  -f deploy/create_app_role.sql
```

The **application's own** `DATABASE_URL` (gunicorn's env — see §5) uses this role, not
the owner:

```
DATABASE_URL=postgres://ecommerce_app:<ECOMMERCE_APP_DB_PASSWORD>@localhost:5432/ecommerce
```

`manage.py migrate` and this role-creation script are the *only* two things that ever
connect as the owner. Everything else — gunicorn, the cron jobs — uses `ecommerce_app`,
which cannot `CREATE`, `ALTER`, or `DROP` anything (verified locally: see the Stage 13 log
entry in `specs/state.md` for the actual command output proving this, including a real
`CREATE TABLE` attempt failing with `permission denied for schema public` under that
role).

## 3. Environment

Copy `.env.example` to `.env` on the server and fill in every value marked required below.
**Never commit this file.**

```
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=<GENERATE_WITH_get_random_secret_key>
DEBUG=False
ALLOWED_HOSTS=mps.scentandstyle.pk

DATABASE_URL=postgres://ecommerce_app:<ECOMMERCE_APP_DB_PASSWORD>@localhost:5432/ecommerce

AWS_ACCESS_KEY_ID=<R2_ACCESS_KEY>
AWS_SECRET_ACCESS_KEY=<R2_SECRET_KEY>
AWS_STORAGE_BUCKET_NAME=<R2_BUCKET_NAME>
AWS_S3_ENDPOINT_URL=<R2_ENDPOINT_URL>

# Optional — see core/backup.py's module docstring for what this buys you.
AWS_BACKUP_BUCKET_NAME=

BACKUP_DIR=/srv/ecommerce/backups
BACKUP_PG_DUMP_PATH=pg_dump

# §41 error monitoring — Django's built-in mail_admins, no new dependency.
# Blank ADMINS means no emails are ever sent (not an error) — a human
# task to fill in real SMTP credentials before this does anything.
ADMINS=Owner:<OWNER_EMAIL>
SERVER_EMAIL=ecommerce@example.com
EMAIL_HOST=<SMTP_HOST>
EMAIL_PORT=587
EMAIL_HOST_USER=<SMTP_USER>
EMAIL_HOST_PASSWORD=<SMTP_PASSWORD>
EMAIL_USE_TLS=True
```

Generate `SECRET_KEY` with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Verify the whole file with the actual deploy check before starting anything:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py check --deploy
```

## 4. Static files and app code

```bash
pip install -r requirements/prod.txt
DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py collectstatic --noinput
```

`collectstatic` writes to `STATIC_ROOT` (`staticfiles/`) — this is the directory
`deploy/Caddyfile`'s `handle_path /static/*` serves directly from disk. Media is never
collected locally; it goes straight to R2 (`core/storage.py`'s `R2MediaStorage`, selected
by `config.settings.prod` alone, per CLAUDE.md's "never branch on DEBUG" rule).

## 5. gunicorn

Bind to a unix socket, never a public TCP port — this is what makes
`TRUST_X_FORWARDED_FOR` in `config/settings/prod.py` safe (see that setting's own
docstring): gunicorn must be reachable *only* through Caddy.

```ini
# /etc/systemd/system/ecommerce.service
[Unit]
Description=ecommerce gunicorn
After=network.target postgresql.service

[Service]
User=ecommerce
WorkingDirectory=/srv/ecommerce
EnvironmentFile=/srv/ecommerce/.env
ExecStart=/srv/ecommerce/.venv/bin/gunicorn config.wsgi:application \
    --bind unix:/run/ecommerce/gunicorn.sock \
    --workers 3
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now ecommerce
```

## 6. Caddy

`deploy/Caddyfile` is already set to `mps.scentandstyle.pk` — confirm the A record for that
name points at this host's IP before proceeding. Then:

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Confirm `https://<real-domain>/` actually loads and has a valid certificate before
continuing — Caddy's automatic HTTPS fails loudly (refuses to serve) if DNS isn't pointed
at this host yet, which is the point.

## 7. Cron

Two jobs, both Django management commands per CLAUDE.md ("background work is Django
management commands invoked by cron, nothing else"):

```cron
*/10 * * * * cd /srv/ecommerce && .venv/bin/python manage.py release_expired_reservations
0 3  * * *   cd /srv/ecommerce && .venv/bin/python manage.py backup
```

`backup` (`core/management/commands/backup.py`, Stage 13) dumps the database, uploads the
dump to R2 under `backups/db/`, mirrors media to `backups/media-mirror/` (or a dedicated
`AWS_BACKUP_BUCKET_NAME` if set), and applies the 30-day retention window — see
`core/backup.py`'s module docstring for the full design and the scope decisions it
records.

## 8. Restore drill (must actually be run once against production, not just locally)

The dump → restore → verify cycle was executed for real against local Postgres during
Stage 13's build (see `specs/state.md`'s Stage 13 log entry for the actual commands and
output: a `pg_dump -Fc` of the dev database, restored into a scratch database via
`pg_restore`, with row counts and a full content checksum proven to match byte-for-byte).
That proves the mechanism. It does not prove the *production* backup — a human still needs
to, once, after go-live:

```bash
# Pull the latest dump R2 holds, or use a local one from BACKUP_DIR.
createdb ecommerce_restore_drill
pg_restore -h localhost -U postgres -d ecommerce_restore_drill --no-owner /path/to/dump
psql -d ecommerce_restore_drill -c "SELECT count(*) FROM catalog_product;"
# ...compare against the live count...
dropdb ecommerce_restore_drill
```

## Human tasks (cannot be completed by an agent)

- [ ] Provision the server, point DNS at it, and confirm Caddy obtains a real certificate.
- [ ] Provide real R2 credentials (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` /
      `AWS_STORAGE_BUCKET_NAME` / `AWS_S3_ENDPOINT_URL`) — currently blank everywhere in
      this repo, including `.env`.
- [ ] Provide real SMTP credentials for `ADMINS`/`EMAIL_*` so the mail_admins error
      monitoring hook (§41, Stage 13) actually delivers anything.
- [ ] Run the restore drill above against the real production backup at least once, per
      §55's explicit requirement — the local proof from this stage's build is necessary
      but not sufficient.
- [ ] Real-device WhatsApp payload-limit measurement — see `docs/whatsapp-limits.md`.
- [ ] Validate a live product page's JSON-LD against Google's Rich Results Test — see
      `specs/state.md`'s Stage 12 human tasks entry.

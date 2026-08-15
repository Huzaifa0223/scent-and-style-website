# Deployment runbook — managed platform (Railway / Render)

The alternative to `docs/deploy.md`, which targets a VPS with Caddy in front of gunicorn.
Both are supported; pick one. This file exists because a managed platform removes the
front door Caddy provided, which changes exactly three things: static file delivery, how
cron is scheduled, and whether `pg_dump` exists.

Nothing here has been run against a real deployment — there isn't one yet. Every step
that needs proving is marked **VERIFY**. Treat an unverified backup as no backup.

---

## Why not Vercel

Recorded so the question does not get reopened without the reasoning. Vercel is
serverless: it has no persistent process, no filesystem, and its cron invokes HTTP
endpoints rather than management commands. This application needs all three.

The specific breakage, in order of severity:

1. `release_expired_reservations` runs every 10 minutes and is the only thing that
   releases reserved stock. Without it, every abandoned cart holds its items
   permanently and the store silently stops being able to sell. This is not
   housekeeping.
2. `manage.py backup` shells out to `pg_dump`, which needs a filesystem and the
   PostgreSQL client binaries.
3. `pg_trgm` and the search indexes need a real Postgres that the app owns.

Railway and Render run a persistent process with real scheduled jobs, so none of the
above has to be redesigned.

---

## Choosing between Railway and Render

| | Railway | Render |
|---|---|---|
| Config | `railway.toml` + `nixpacks.toml` | `render.yaml` (Blueprint) |
| Cron | Separate services, created in the dashboard | Declared in `render.yaml`, in version control |
| `pg_dump` | Guaranteed — `nixpacks.toml` installs `postgresql` | **VERIFY** — not documented on the native runtime |

**Render** keeps the cron schedule in git, which matters for the job that keeps stock
sellable. **Railway** guarantees the backup job can actually run. If backups matter more
than reviewable scheduling, take Railway; otherwise take Render and verify `pg_dump`
first thing.

---

## 1. Database

Both platforms provision managed PostgreSQL and expose `DATABASE_URL`.

- CLAUDE.md pins **PostgreSQL 18.4**. Neither platform is likely to offer that exact
  version yet. `render.yaml` requests major 17. Record the actual deployed version in
  `specs/state.md` — it is a locked decision being deviated from, not a detail.
- **VERIFY:** `migrate` must be able to run `CREATE EXTENSION pg_trgm`
  (`core/migrations/0001_enable_pg_trgm.py`). Managed Postgres allows this only for
  roles with sufficient privilege, and `pg_trgm` must be on the platform's allow-list.
  If this fails, **stop** — CLAUDE.md forbids substituting a different database or
  search implementation.
- **VERIFY:** `core/migrations/0003_set_word_similarity_threshold.py` issues
  `ALTER DATABASE ... SET pg_trgm.word_similarity_threshold`. That requires database
  ownership. If the platform's role cannot, search ranking silently falls back to
  whatever Postgres compiled in, which is the exact failure that migration exists to
  prevent.

Confirm both after the first deploy:

```sql
SELECT extname FROM pg_extension WHERE extname = 'pg_trgm';
SHOW pg_trgm.word_similarity_threshold;   -- expect 0.6
```

The least-privilege `ecommerce_app` role from `docs/deploy.md` §3 does not transfer:
managed platforms hand you one owner role. Recorded as a deviation.

---

## 2. Environment variables

Set on the web service **and on each cron job** — a scheduled job runs in its own
environment and will fail on a missing variable at run time, not at deploy time.

| Variable | Value |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `SECRET_KEY` | generate fresh; never the dev key |
| `DEBUG` | `False` — `prod.py` raises at import if truthy |
| `ALLOWED_HOSTS` | the platform hostname; `prod.py` raises at import if empty |
| `DATABASE_URL` | from the managed database |
| `SERVE_STATIC_FROM_R2` | `True` — see §3 |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | R2 token |
| `AWS_STORAGE_BUCKET_NAME` / `AWS_S3_ENDPOINT_URL` | R2 bucket |
| `AWS_S3_REGION_NAME` | `auto` |
| `AWS_BACKUP_BUCKET_NAME` | optional second bucket for backups |

---

## 3. Static files

There is no Caddy, and Django does not serve static once `DEBUG=False`, so without this
step every stylesheet, script and self-hosted font 404s.

`SERVE_STATIC_FROM_R2=True` switches `STORAGES["staticfiles"]` to
`core.storage.R2StaticStorage`, and the build step runs `collectstatic`, which uploads
to the R2 bucket already configured for media.

Note `static/css/app.css` is a build artefact and is gitignored — the build step fetches
the pinned Tailwind CLI and compiles it. Without that the site deploys with no
stylesheet at all.

WhiteNoise is the more usual answer and would let the app serve its own static files. It
is deliberately not used: it is a new runtime dependency, and CLAUDE.md's approved list
is explicit. If it is wanted, take it as a dependency decision on its own merits.

---

## 4. Cron

Both jobs come straight from `docs/deploy.md` §7 and must exist on either platform.

```
*/10 * * * *   python manage.py release_expired_reservations
0 3 * * *      python manage.py backup
```

**Render:** already declared in `render.yaml`. Nothing to do.

**Railway:** create two additional services from the same repo, each with a schedule and
the command above. Railway has no declarative cron, so these live only in the dashboard
— which is precisely why they are written down here.

**VERIFY, first day:** trigger `release_expired_reservations` manually and confirm it
completes. Then place a test order, let its reservation TTL expire, and confirm stock is
returned. If this job is not running, the failure is silent and looks like "items keep
going out of stock".

---

## 5. First deploy

1. Connect the repo; the platform reads `railway.toml`/`nixpacks.toml` or `render.yaml`.
2. Set the environment variables from §2.
3. Deploy. Migrations run in the pre-deploy step, once, before any worker takes traffic
   — deliberately not from the start command, which would race three gunicorn workers
   against the same schema.
4. Create the merchant account:
   ```
   python manage.py createsuperuser
   ```
5. Set `ALLOWED_HOSTS` to the real hostname and redeploy if the platform assigned it
   after the first build.

---

## 6. Post-deploy verification

- [ ] `/healthz/` returns 200 (both configs use it as the health check).
- [ ] `SELECT extname FROM pg_extension` shows `pg_trgm`.
- [ ] `SHOW pg_trgm.word_similarity_threshold` returns `0.6`.
- [ ] Search for a deliberate typo (`afnn` → `Afnan`) and confirm it still matches — this
      is the assertion that proves trigram search survived the move.
- [ ] A product page renders its image (R2 media) **and** is styled (R2 static).
- [ ] Placing an order reserves stock; letting it expire returns it.
- [ ] `manage.py backup` produces a dump in R2. **VERIFY on Render** — see §7.
- [ ] `manage.py check --deploy` reports no issues against the deployed settings.
- [ ] Restore drill: restore the dump into a scratch database and compare row counts.
      `docs/deploy.md` §8 has the procedure; it has been run locally but never against a
      real host.

---

## 7. Known gaps

- **`pg_dump` on Render.** Not documented as present on the native Python runtime, and a
  Dockerfile is not an option (CLAUDE.md forbids Docker in production). If absent:
  either have the build step fetch a client binary and point `BACKUP_PG_DUMP_PATH` at
  it, or use Render's managed database backups for the database half and keep
  `manage.py backup` for the media mirror. Do not leave the job scheduled and
  unverified.
- **PostgreSQL version** will not be 18.4. Record what is actually deployed.
- **Least-privilege database role** does not transfer; the platform provides one owner
  role.
- **Static assets are not content-hashed**, so `R2StaticStorage` caches for an hour with
  revalidation rather than the year-long immutable cache the media backend uses. A
  hashed-filename storage would allow the long cache back.

# E-Commerce Store

Single-merchant e-commerce application. Server-rendered Django, HTMX + Alpine for
interactivity, no SPA framework, no REST API. See `specs/REQUIREMENTS.md` for the full product
spec and `specs/roadmap.md` for the build plan; `specs/state.md` tracks where the project
actually stands.

## Stack

Python 3.11 · Django 5.2 · PostgreSQL 18 · HTMX 2 · Alpine 3 · Tailwind CSS 3.4 (standalone CLI,
no Node) · Pillow · django-storages + Cloudflare R2 · pytest + pytest-django + factory-boy ·
ruff · mypy (strict) · Caddy (production front door)

## Quickstart

Prerequisites: Python 3.11 (available as `py -3.11` on Windows / `python3.11` on Linux) and a
running PostgreSQL 18 instance with a database named `ecommerce`.

```powershell
# Windows
.\setup_dev.ps1
```

```bash
# Linux / macOS
./setup_dev.sh
```

Both scripts are idempotent — safe to run again after a `git pull`. They will:

1. Create a `.venv` using Python 3.11.
2. Install `requirements/dev.txt`.
3. Create `.env` from `.env.example` (generating a real `SECRET_KEY`) if one doesn't exist.
4. Download the Tailwind standalone CLI into `tools/` and the vendored HTMX/Alpine builds into
   `static/vendor/` (never CDN-loaded at runtime).
5. Build `static/css/app.css`.
6. Run migrations.
7. Seed a superuser from the `DJANGO_SUPERUSER_*` variables in `.env`, unless one already exists.

Edit `.env` first if your PostgreSQL credentials differ from the placeholder in
`.env.example`.

## Everyday commands

```bash
.venv\Scripts\python manage.py runserver     # dev server (Windows)
.venv/bin/python manage.py runserver         # dev server (Linux/macOS)

pytest                                        # test suite
pytest --cov --cov-report=term-missing        # with coverage
ruff check .                                  # lint
ruff format .                                 # format
mypy .                                        # strict type check
python manage.py makemigrations --check --dry-run   # catch model drift
```

Django admin: `/django-admin/`. Health check: `/healthz/` (no auth, no PII — safe for uptime
monitors).

## Settings

Four settings modules under `config/settings/`, selected via `DJANGO_SETTINGS_MODULE`:

| Module | Used by |
|---|---|
| `config.settings.dev` | Local development (`manage.py`'s default) |
| `config.settings.test` | The pytest suite |
| `config.settings.prod` | Production (`config.wsgi`'s default). Refuses to load with `DEBUG=True` or without `ALLOWED_HOSTS`. |

All non-merchant configuration (secrets, database URL, storage credentials) comes from the
environment via `django-environ` — see `.env.example` for the full list. Merchant-editable
values (store name, currency, delivery rates, etc.) live on the `StoreSettings` singleton, not
in environment variables or code.

## Project layout

See CLAUDE.md for the full app list and the standards every app follows. As of Stage 1:

```
config/     settings, urls, wsgi/asgi
core/       TimeStampedModel, typed config, storage backends, the money template filter
store/      StoreSettings singleton (identity, contact, currency, timezone)
templates/  base shell + separate storefront/ and portal/ shells, styled 404/500
```

Later stages add `catalog/`, `inventory/`, `search/`, `cart/`, `orders/`, and the rest — see
`specs/roadmap.md`.

## Background jobs

None yet. Stage 4 adds `release_expired_reservations` (cron, every 10 minutes) and Stage 13
adds the nightly backup job; both will be documented here once they exist.

## CI

`.github/workflows/ci.yml` runs on every push/PR to `main`: install → `ruff check` →
`ruff format --check` → `mypy` → `makemigrations --check --dry-run` → `pytest --cov` (with a
per-app coverage floor) → `manage.py check --deploy`. Uses a Postgres 18 service container to
match production.

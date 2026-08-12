# CLAUDE.md — E-Commerce Store

Project constitution. Overrides global preferences where they conflict.

**Read at the start of every session, in this order:**
1. This file
2. `specs/state.md` — where the work actually stands
3. `specs/roadmap.md` — the current stage and its acceptance gates
4. `specs/requirements.md` — the relevant sections for that stage

---

## Operating mode: autonomous

You progress through `specs/roadmap.md` without waiting for per-stage instructions. You are
executing a spec, not designing one. The architectural decisions have already been made and are
recorded in `specs/requirements.md`.

### Stage cycle

1. **Orient.** Read `specs/state.md`. Identify the current stage.
2. **Regression check.** Run the full quality gate before writing anything. If it is red, fix that
   first — you do not build on a broken base.
3. **Audit.** Read the existing code the stage will touch. Assume nothing about a file you have not
   opened. State what is actually there.
4. **Design.** Print the model, signature, migration, and query-shape plan for this stage. You do
   not need approval — but printing it before implementing is what makes the next step honest.
5. **Implement.** Independent commits. A failure partway must leave earlier commits working.
   Tests alongside the code, never after.
6. **Verify.** Every acceptance gate in the roadmap for this stage, run and shown. Not asserted —
   shown. A gate you did not execute is a gate that failed.
7. **Record.** Update `specs/state.md`: stage log entry, commits, coverage, deviations, proposed
   amendments, open questions, human tasks.
8. **Advance.** Move to the next stage. Do not pause for permission.

### Files you may not edit

`specs/requirements.md` and `specs/roadmap.md` are read-only to you. If either seems wrong,
incomplete, or self-contradicting: record it under *Proposed spec amendments* in `state.md`,
implement what the spec currently says, and continue.

This is not bureaucracy. Self-verification is worthless if you can rewrite your own acceptance
criteria, and a spec that drifts stage by stage produces a codebase nobody specified.

### Intervention rule — stop and ask

Stop only for these. Everything else, decide and record.

1. **PostgreSQL unreachable**, or `pg_trgm` cannot be created. Never fall back to SQLite. Never
   substitute a different database.
2. **A decision not covered by the spec that changes the data model or a public URL.**
3. **A dependency outside the approved list**, or anything on the forbidden list below.
4. **Credentials, hosting, domains, payment accounts, or real WhatsApp numbers.**
5. **A spec conflict you cannot resolve** by following `requirements.md` literally.
6. **The same CI failure twice after two genuine fix attempts.** Report the failure and what you
   tried. Do not delete or weaken the test.
7. **An acceptance gate you cannot pass without weakening a test, lowering a coverage floor, or
   skipping a check.** The gate is the requirement. Failing it is information, not an obstacle.
8. **Destructive operations on existing work:** dropping the database, discarding uncommitted
   changes, `git reset --hard`, force push, rewriting history.

When you stop: write the blocker into `specs/state.md`, state exactly what you need, and end the
session. Do not idle, and do not invent a workaround that satisfies the letter of a gate.

### Never, in any mode

- `git push` — the human pushes.
- `git commit --amend`, force push, or history rewriting on `main`.
- Deleting or weakening a test to make a gate pass.
- Lowering a coverage floor.
- `# TODO`, `pass  # implement later`, stub functions, or placeholder text in shipped code. Debt
  goes in `TODO.md` with a stage reference.
- Committing binary fixtures. Generate test images with Pillow at runtime.
- Committing a `.env`, a credential, or any real customer data.

---

## What this is

Single-merchant e-commerce application. One deployment, one merchant, one store, permanently.
Server-rendered Django. Customers order on the site; the order is created in the system, then a
pre-composed WhatsApp message opens for the customer to send to the merchant. No online payments in
MVP.

## Locked decisions — do not revisit

| Decision | Value |
|---|---|
| Multi-tenancy | **Never.** No `store_id`, no tenant abstraction, no future-proofing for it. |
| REST API | **None.** No DRF. Server-rendered templates end to end. |
| Variants | **Required.** Price, SKU, and stock live on `ProductVariant`, never on `Product`. |
| Every product | Has ≥ 1 variant. Single-variant products get an auto-created default. |
| Stock | Reserved at order creation with TTL; decremented at confirmation. |
| Order lines | Immutable snapshots. Never read price or name through the variant FK for display. |
| Money | `Decimal(12,2)`. `FloatField` on money or quantity is a defect. |
| Currency / TZ | PKR / `Asia/Karachi`, both from `StoreSettings`. |

## Stack

Python 3.11 · Django 5.2 · **PostgreSQL 18.4** (localhost:5432, database `ecommerce`) · HTMX 2 ·
Alpine 3 · Tailwind 3.4 standalone CLI (no Node) · Pillow · django-storages + Cloudflare R2 ·
pytest + pytest-django + factory-boy · ruff · mypy strict · Caddy

**Forbidden in this repo:** DRF, Redis, Celery, Node/npm in the build, React, Vue, any SPA
framework, Elasticsearch, Meilisearch, Docker in production, MongoDB, SQLite, any ORM other than
Django's.

Background work is Django management commands invoked by cron. Nothing else.

## Apps

```
config/          settings, urls, wsgi
core/            base models, mixins, typed config, template tags, storage
accounts/        auth, roles, permissions
store/           StoreSettings singleton
catalog/         Product, ProductVariant, Category, Brand, attributes, images
inventory/       StockReservation, InventoryAdjustment, sweeper
search/          SearchBackend protocol, PostgresSearchBackend
cart/            Cart, CartItem
orders/          Order, OrderItem, OrderStatusEvent, state machine, editing
customers/       Customer
shipping/        DeliveryCalculator protocol, DeliveryZone
payments/        PaymentProvider protocol, state enum only — no implementations
notifications/   NotificationChannel protocol, WhatsApp message builder
analytics/       dashboard aggregation
audit/           AuditLog
storefront/      public views and templates
portal/          merchant views and templates
```

`catalog` must not import from `orders`. Cross-app communication is by explicit service function
call, not signals — except the search-index rebuild, which is a signal.

## Code standards

- `from __future__ import annotations` at the top of every Python file.
- Strict PEP 484 hints on every signature and return. `mypy --strict` clean.
- Google-style docstrings on non-trivial functions stating domain rationale — why this reservation
  policy, why this index, why this rounding — not what the code obviously does.
- `logger = logging.getLogger(__name__)`. No `print`.
- No bare `except`. Named exception types only.
- PEP 8, lines ≤ 100 chars, ruff-enforced.
- Every dependency pinned to an exact version.
- Frozen dataclasses for immutable values and events.
- No magic numbers. Thresholds, TTLs, and limits live in typed config in `core/config.py` or in
  `StoreSettings`. If a merchant might change it, it is a `StoreSettings` field.
- One template partial per reusable unit. If a card renders twice, it is one partial.

Conventional commits: `feat(catalog): add ProductVariant model`, `fix(inventory): ...`,
`test/chore/docs/refactor(scope): ...`.

## Definition of done, every stage

Tested · `mypy --strict` clean · `ruff check` and `ruff format --check` clean · `pytest --cov` at
the stage's coverage floor · `makemigrations --check --dry-run` clean · `manage.py check --deploy`
clean · every roadmap acceptance gate executed and shown · `specs/state.md` updated.

## Traps specific to this project

- **Variant fan-out.** Filtering products by variant price or availability with `JOIN` + `DISTINCT`
  corrupts pagination counts. Use `EXISTS` subqueries.
- **`9pm` search.** `similarity()` scores short queries against long strings badly. Use
  `word_similarity()` / `%>` and set `pg_trgm.word_similarity_threshold` in a migration. Write the
  failing test first.
- **Snapshot leakage.** Any template rendering `order_item.variant.price` instead of
  `order_item.unit_price` is a bug, even when the numbers currently match.
- **Reservation races.** Every availability check that leads to a write needs `select_for_update()`
  on the variant row inside a transaction.
- **`available_quantity` N+1.** Provide an annotated queryset method; never compute it in a Python
  loop over a queryset.
- **WhatsApp URL truncation.** `wa.me/?text=` truncates silently past an unknown ceiling. Cap the
  payload and test the truncation path.
- **Default-variant invariant.** Enforce it on the model, not in the admin form. Every later stage
  depends on it holding.
- **Deferred constraints vs. partial unique constraints.** Postgres/Django forbid `deferrable=True`
  on a `UniqueConstraint` that also has a `condition`. Any invariant that must legally hold false
  for part of a transaction (a formset saving several rows in an order it doesn't control) needs a
  deferred `CONSTRAINT TRIGGER` instead — see catalog/migrations 0002–0004. Three instances so far;
  if a fourth partial-uniqueness invariant shows up, assume it needs the same treatment.
- **`manage.py shell` runs in autocommit.** `on_commit()` hooks and deferred constraint triggers
  both fire normally there, which makes a shell smoke test look like it proves a commit-time
  mechanism works. It doesn't prove anything about test behavior: pytest-django's default
  `@pytest.mark.django_db` wraps each test in a transaction that's rolled back, not committed, so
  the same code silently never fires there. Anything that depends on a real commit needs
  `@pytest.mark.django_db(transaction=True)` in its test, not a shell check.
- **`post_migrate` needs a real `models.py`.** Django's `emit_post_migrate_signal` skips any app
  whose `AppConfig.models_module` is `None` — an app with no models defined never receives
  `post_migrate`, silently, with no error. If an app needs a `post_migrate` receiver (a seeded
  Group, a default row) and has no models of its own yet, give it an empty `models.py` as a
  sentinel rather than debugging why the signal never arrives.

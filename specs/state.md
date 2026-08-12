# State

Durable project memory. The agent reads this first in every session and updates it at the end of
every stage. It is the answer to "where are we and what is not obvious from the code".

Keep it factual and short. Append to the log; do not rewrite history. If this file and the code
disagree, the code is right and this file is stale — fix it.

---

## Current position

**Stage:** 3 — Merchant portal: catalog management
**Status:** not started
**Last updated:** 2026-08-12
**CI:** workflow committed (`.github/workflows/ci.yml`), never executed — no push has been made
to any remote (the human pushes, per CLAUDE.md). Everything it runs has been run locally instead;
see the Stage 1 log entry for that output.

---

## Environment

| Item | Value |
|---|---|
| Repo | `D:\ecommerce-store` |
| PostgreSQL | 18.4, localhost:5432 |
| Database | `ecommerce` |
| DB user (dev) | `postgres` |
| Python | 3.11 |
| Branch | `main` |
| Remote | not configured |

---

## Stage log

Append one block per completed stage. Do not delete earlier entries.

```
### Stage N — <name>
Completed: YYYY-MM-DD
Commits: <hash> <subject>
         <hash> <subject>
Acceptance gates: all passed | passed except <n> — see Deviations
Coverage: <module> <pct>
Notes: anything a future session needs that the code does not make obvious
```

### Stage 1 — Foundation
Completed: 2026-08-12
Commits: d06b7ce chore: initialise repo, gitignore, and tooling config
         142d712 feat(core): add TimeStampedModel, typed config, storage, money filter, healthz
         69fe748 feat(store): add StoreSettings singleton with cached load and admin
         a50eeeb feat(config): add settings package, urls, wsgi/asgi entry points
         0e5b6a3 feat(templates): add base/storefront/portal shells and styled error pages
         5502f0a chore(ci): add GitHub Actions workflow and setup_dev scripts
         3de96db docs: add README and TODO
Acceptance gates:
  1. PARTIAL — setup_dev.ps1 run twice, both times exit 0, confirming re-run idempotency and the
     "artifact already present" skip branches. Also re-tested after deleting tools/tailwindcss.exe
     and static/vendor/*.js to exercise the actual download branches (also passed). NOT tested:
     venv-creation-from-nothing and .env-generation-from-.env.example, since this machine already
     had .venv and .env from earlier interactive setup — re-testing those destructively (delete
     .env, which holds the real DB password) was judged not worth the risk for a re-run. First
     genuinely fresh clone should confirm this branch.
  2. PASSED — /healthz/ returns 200 {"status":"ok","database":true}, verified via pytest and via
     a live runserver + curl.
  3. PASSED — verified via pytest (store/tests/test_admin.py, test_models.py): singleton row,
     PKR/Asia-Karachi defaults, has_add_permission/has_delete_permission hard-False, add/delete
     URLs return 403 even for a superuser.
  4. PASSED — store/tests/test_context_processors.py renders a template through the request-bound
     context processor twice, editing StoreSettings.name between renders; the second render
     reflects the edit. core/tests/test_cache.py separately proves the database cache table isn't
     a silent no-op (set/get round-trip asserted, and django_cache_table's existence in
     test_ecommerce confirmed directly via psql).
  5. PASSED — verified via pytest (config.settings.test runs with DEBUG=False by design) AND live:
     started runserver with DEBUG=False against config.settings.dev, curled an unknown URL, got
     the styled 404.html, not Django's debug traceback page.
  6. SOURCE-LEVEL ONLY — core/tests/test_templates.py asserts base.html's rendered source contains
     "vendor/htmx.min.js"/"vendor/alpine.min.js" and none of unpkg.com/cdn.jsdelivr/cdnjs. No live
     page renders base.html yet (no storefront/portal view exists before Stage 3/6), so no actual
     browser network request was observed. Re-verify at the network level once Stage 6 renders a
     real page.
  7. PASSED — ruff check: all checks passed. ruff format --check: clean. mypy --strict: no issues
     (35 source files). makemigrations --check --dry-run: no changes detected. pytest: 34 passed.
     Coverage: core 100%, store 100% (floor 80%). manage.py check --deploy: 0 issues, both under
     config.settings.dev and config.settings.prod (prod checked with a real random SECRET_KEY,
     DEBUG=False, ALLOWED_HOSTS set, and placeholder R2 credentials).
Coverage: core 100%, store 100% (floor 80%)
Notes:
  - setup_dev.sh (the Linux/macOS counterpart) has never actually been executed — this is a
    Windows dev machine. Syntax-checked with `bash -n` only. Its Python-3.11 detection, `sed -i`,
    and .venv/bin/python paths are unverified. First Linux run (a contributor, or a manual
    workflow_dispatch) should confirm it.
  - django-stubs-ext is a *runtime* dependency in requirements/base.txt, not dev.txt — it's not
    just type stubs, `django_stubs_ext.monkeypatch()` in config/settings/base.py is what makes
    `admin.ModelAdmin[StoreSettings]` subscriptable at import time, in every environment.
  - Django admin mounted at /django-admin/ (not the default /admin/) to avoid any future confusion
    with the custom merchant portal at /admin-portal/ (§1) — see Open questions.
  - PASSWORD_HASHERS keeps Argon2 first in config.settings.test too (not swapped for a faster
    hasher), per CLAUDE.md's literal "Argon2 first in PASSWORD_HASHERS" with no test carve-out.
    Revisit if the test suite's runtime becomes a real problem later.

### Stage 2 — Catalog domain model
Completed: 2026-08-12
Commits: e07f249 feat(core): add slug generation and image-derivative helpers
         9b058b0 feat(catalog): add domain model (requirements §2)
         1ba9ebf feat(catalog): add create_product service and deferred invariant trigger
         7cd4873 test(catalog): add factories and full test suite
         15e4780 docs: update README/TODO for Stage 2, add catalog coverage floor to CI
Acceptance gates: all passed
  1. Every invariant has a test proving it's enforced, including the failure case — see
     catalog/tests/. Default-variant creation, Category two-level rejection, AttributeValue
     (definition, slug) uniqueness, duplicate variant attribute-set rejection, one-primary-image
     and one-default-variant constraints (with promotion-on-delete for the former) all covered.
  2. Saving a product with no variants produces exactly one default variant — via
     catalog.services.create_product(), not a Product.save() override (see Notes — the original
     on_commit-based design was replaced mid-stage; a caller that bypasses the service still gets
     exactly one violation at commit, from the deferred DB trigger, not a second default variant).
  3. Three-level category save raises ValidationError — catalog/tests/test_category.py.
  4. Two variants of one product with identical attribute sets raise IntegrityError —
     catalog/tests/test_product_variant.py, plus a dedicated numeric-vs-lexical sort regression
     test (AttributeValue pks 2 and 10 attached in high-then-low order; signature must be "2,10").
  5. display_price returns the minimum across active variants, ignoring inactive ones — as an
     annotated ProductQuerySet.with_pricing() method, not a @property (see Notes).
  6. Image upload produces three derivatives (200/600/1400px, WebP+JPEG) with correct dimensions —
     verified against a 2000x1000 Pillow-generated runtime image (2:1 aspect ratio preserved:
     200x100/600x300/1400x700). No binary fixtures committed.
  7. `grep -rn "FloatField" .` returns nothing outside migrations — automated as
     tests/test_no_float_fields.py rather than a one-off manual check.
  8. Quality gate green: ruff check clean, ruff format clean, mypy --strict clean (53 source
     files), makemigrations --check --dry-run clean, 94 tests passed. Coverage: catalog 95%
     (models.py 96%, services.py 86%; floor 85%), core 100% (floor 80%), store 100% (floor 80%).
     manage.py check --deploy clean under both config.settings.dev and config.settings.prod.
Coverage: catalog 95%, core 100%, store 100% (floors 85%/80%/80%)
Notes:
  - **Mid-stage design correction, recorded because it's the most consequential thing that
    happened this stage.** The first implementation enforced "every product has >=1 variant" via
    `transaction.on_commit()` scheduled from `Product.save()`. This is broken for testing:
    `on_commit` callbacks only fire on a real COMMIT, and pytest-django's default `django_db`
    fixture wraps each test in a transaction that's rolled back, never committed — so the entire
    safety net was silently inert under the test suite the whole time it existed, and every test
    that appeared to exercise it was actually passing for the wrong reason (nothing had run at
    all). Caught before any test suite was written against it, not after. Replaced with
    `catalog.services.create_product()` (product + default variant, one transaction, synchronous —
    no commit-hook indirection) as the sanctioned creation path, plus a Postgres
    `CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED` pair (migration 0002) as the backstop
    for anything that bypasses the service. Deferred triggers have the same testability trap in
    reverse — they only fire at commit too — so the three tests that exercise the backstop
    directly use `@pytest.mark.django_db(transaction=True)` to force a real commit.
  - `display_price`/`has_price_range` (Product) and `available_quantity` (ProductVariant) were
    originally `@property`. Changed to annotated QuerySet methods
    (`Product.objects.with_pricing()`, `ProductVariant.objects.with_available_quantity()`) before
    any view code could depend on the property form — a property re-queries per instance, which
    would have failed Stage 6's `assertNumQueries` gate on the first list view that used it.
    `is_in_stock`/`is_low_stock` stayed as properties reading `stock_quantity` directly; Stage 4
    revisits them once reservations make availability differ from on-hand stock.
  - `attribute_signature` sorts via Python `sorted()` on the actual int `value_id`s (not SQL
    `order_by`, which — while already numeric on an integer column — made the guarantee implicit
    rather than obvious at the call site). Test proves it with ids 2 and 10 attached in an order
    that would expose a lexical-sort bug.
  - `catalog/admin.py` deliberately does not exist yet — roadmap Stage 2 says "models only, no
    portal UI." Stage 3 builds the real merchant-facing interface; Django admin was never intended
    to be that.
  - Every `ProductVariant.low_stock_threshold` starts at `core.config.DEFAULT_LOW_STOCK_THRESHOLD`
    (5) — a row default a merchant can change per variant immediately, not a StoreSettings field,
    since it isn't a single store-wide value.

---

## Deviations from spec

Anything built differently from `requirements.md` or `roadmap.md`, with the reason. An empty
section here after several stages means either the work went perfectly or deviations are not
being recorded. The second is far more likely.

```
- [Stage N] <what differs> — <why> — <reversible? what would it cost to align>
```

- [Stage 1] StoreSettings only has identity/contact/currency/timezone fields, not the full §40
  list (delivery strategy and rates, order settings/reservation TTL, notification templates, SEO
  defaults, social links) — those fields are added by the stages that first need them (4, 8, 9,
  12) rather than all at once now. Reversible; costs nothing to align since it's purely additive
  migrations later.
- [Stage 1] mypy strict has scoped `ignore_errors = true` overrides for `*.migrations.*` and
  `*.tests.*`/`conftest`, beyond what the roadmap spells out. Migrations are Django-generated/
  framework-shaped; pytest-django's injected fixtures (client, rf, django_user_model, ...) have no
  precise stubs, so strict annotation requirements there add noise without catching real bugs.
  Tests still must pass — only typing rigor on test code is relaxed. Reversible; would just mean
  annotating every test function's fixture parameters.

---

## Proposed spec amendments

Where the spec appears wrong, incomplete, or self-contradicting. **Do not edit
`requirements.md` or `roadmap.md`.** Record the proposal here, implement what the spec currently
says, and continue. The human resolves these.

```
- [Stage N] §<section> — <what the spec says> — <why it seems wrong> — <proposed change>
```

- [Stage 1] File naming — `CLAUDE.md` and `specs/roadmap.md` both reference `specs/requirements.md`
  (lowercase); the actual file is `specs/REQUIREMENTS.md` (uppercase). Invisible on this Windows
  checkout (case-insensitive filesystem) but will break any lowercase path reference on the Linux
  CI runner or a Linux/macOS contributor's machine. Proposed change: rename to
  `specs/requirements.md` — cosmetic, no content change, but I can't make it myself (read-only).
- [Stage 1] Tailwind binary location — `requirements.md` §A1 doesn't specify, but the general
  stack description plus common convention suggests "checked into `tools/`"; `roadmap.md` Stage 1
  explicitly says "download the Tailwind standalone binary to `tools/`" as part of setup_dev. I
  followed the roadmap: `tools/` is gitignored, setup_dev.ps1/.sh download the binary idempotently.
  Flagging in case the intent was actually to commit it (avoids a network dependency at setup
  time, at the cost of a ~40MB binary in every clone).
- [Stage 1] HTMX/Alpine "vendored" — initially implemented as a setup-time download into a
  gitignored `static/vendor/` (same pattern as the ~40MB Tailwind binary), then reconsidered:
  "vendored" more naturally means committed, and unlike the Tailwind binary these are two ~50KB
  files, cheap to track. Committed them directly instead — a fresh clone now has working
  HTMX/Alpine with zero network access; setup_dev.ps1/.sh still contain the download step (now
  effectively a no-op "already present" skip) so a version bump only requires deleting the file
  and re-running setup_dev. No longer flagging this as open; noting the reasoning for the record.
- [Stage 2] §2.1 — `Product.tags` is specified as an M2M field, but no `Tag` model appears in
  roadmap Stage 2's explicit model list ("Brand, Category, AttributeDefinition, AttributeValue,
  Product, ProductVariant, ProductAttributeValue, VariantAttributeValue, ProductImage"). An M2M
  field needs a target model, so I added a minimal `Tag(name, slug)` — not treating this as a real
  deviation since it's a necessary structural implication of a field the spec already asks for,
  but flagging in case a fuller Tag model (e.g. `is_published`, per-tag SEO fields) was intended
  and just not spelled out.

---

## Open questions

Questions that did not block progress but need an answer eventually.

```
- [Stage N] <question> — <what was assumed in the meantime>
```

- [Stage 1] Django's built-in admin mount path — neither spec file says where `django.contrib.
  admin` should live (only that the *custom* merchant portal is `/admin-portal/`, §1). Mounted it
  at `/django-admin/` to avoid any visual/URL confusion with the portal once Stage 3 builds it out.
  Assumed in the meantime: Django admin stays a thin StoreSettings-only surface (and whatever
  else warrants it) rather than becoming the merchant's primary interface — the portal is.

---

## Human tasks

Work only the human can do: real-device testing, credentials, hosting, domains, business
decisions. Not blockers unless a stage's acceptance gate depends on one.

```
- [ ] Measure the real wa.me payload ceiling on Android Chrome, iOS Safari, and WhatsApp Web;
      record in docs/whatsapp-limits.md and set WHATSAPP_MESSAGE_MAX_CHARS (stage 9)
- [ ] Cloudflare R2 bucket and credentials (needed for stage 13, not before)
- [ ] Domain and hosting decision (stage 13)
- [ ] Merchant's real WhatsApp Business number for store settings
- [ ] Decide whether existing product data needs migrating — affects whether CSV import (stage 16)
      moves earlier
```

---

## Blockers

Only populated when execution has actually stopped. Each entry states what was tried, why it
failed, and precisely what is needed to unblock. Clear the entry when resolved.

```
- [Stage N] <blocker> — tried: <what> — need: <what exactly>
```

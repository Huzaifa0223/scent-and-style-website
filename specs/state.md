# State

Durable project memory. The agent reads this first in every session and updates it at the end of
every stage. It is the answer to "where are we and what is not obvious from the code".

Keep it factual and short. Append to the log; do not rewrite history. If this file and the code
disagree, the code is right and this file is stale — fix it.

---

## Current position

**Stage:** 3 — Merchant portal: catalog management
**Status:** in progress, paused for human review. Product create/edit and the variant formset are
now built and gate-verified (this pass); image management and publish/unpublish/feature/archive
actions remain unbuilt — the human re-authorized the formset work specifically, not the rest of
the stage, so stopping here again rather than continuing into those. See the checkpoint report at
`specs/report.md` for the state *before* this pass (still accurate for everything except the "Not
started" list below, which this pass shortens).
**Last updated:** 2026-08-12
**CI:** workflow committed (`.github/workflows/ci.yml`), never executed — no push has been made
to any remote (the human pushes, per CLAUDE.md). Everything it runs has been run locally instead;
see the Stage 1 log entry for that output.

**What's landed so far (all committed, quality gate green):**
`accounts/` (login/logout, `PortalPermissionRequiredMixin`, seeded "Staff" Django Group),
`portal/` product list + Category/Brand/Attribute CRUD + product create/edit with the variant
inline formset, a project-wide design system (`docs/design.md`, `tailwind.config.js` tokens,
self-hosted IBM Plex). **Not started:** image management (upload, drag-reorder, primary selection,
delete/replace), publish/unpublish/feature/archive actions.

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
         3d59bd5 fix(catalog): make default-variant invariant a deferred trigger, close gaps
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
  - **Post-stage review pass (before Stage 3 started) found three more gaps; two fixed, one
    recorded below as an open question.** First: `variant_one_default_per_product` was a partial
    `UniqueConstraint` (`condition=Q(is_default=True))`. Postgres/Django forbid combining a unique
    constraint's `condition` with `deferrable=True`, so it was immediate — meaning every
    default-variant swap had to unset the old default *before* setting the new one, in that exact
    statement order, to avoid a transient two-defaults state raising mid-transaction. Stage 3's
    variant formset can't guarantee that order (form-save order isn't "old default first"), so
    this is now a deferred `CONSTRAINT TRIGGER` (migration 0003), same mechanism and same reasoning
    as the "at least one variant" trigger from migration 0002. Second and third: the invariant
    coverage claimed complete under gate 1 had two real gaps — deleting a product's *only* image
    was never tested (the promotion path's `.first()` returning `None` was correct but
    unverified, and nothing would have caught a future refactor that assumed a next image always
    exists), and `ProductVariant.image`'s `SET_NULL` behavior on the referenced `ProductImage`
    being deleted was never exercised at all. Both now have tests
    (`catalog/tests/test_product_image.py`). Lesson for later stages: a `manage.py shell` smoke
    test runs in autocommit, where `on_commit` and deferred constraints both fire normally — it
    will not reproduce pytest's default rolled-back-transaction semantics, so "I checked it in the
    shell" is not evidence a commit-time mechanism works under the test suite. Stage 4's
    reservation concurrency tests hit the same trap.

### Stage 3 — Merchant portal: catalog management (in progress, paused for review)
Not yet a completed-stage entry — see `specs/report.md` for the checkpoint from before this pass,
and the top of this file's "Current position" for what's landed vs. outstanding now. Notes below
are worth keeping regardless of how the paused work resolves.

Commits through the first pause: `029f20b` fix(catalog) default-variant promotion, `e419e76`
feat(accounts,portal) auth + portal shell + catalog CRUD, `9a5a15e` feat(design) design system.

Commits this pass (product create/edit + variant formset, resumed after advisor design review
per the human's explicit instruction): `57407b9` fix(catalog) deferred attribute-signature
constraint + default-promotion guard, `56ce9d1` feat(portal) product create/edit views and
variant formset.

**Gate status, updated this pass:**

| Gate | Status |
|---|---|
| 1. 3-variant/2-attribute product, publish | **Provable now** — `portal/tests/test_product_form.py::test_gate1_...` |
| 2. Last-variant-delete refused with a message | **Provable now** — `test_gate2_...`, formset `clean()`, not the DB trigger, is what the merchant sees |
| 3. Image reorder persists | Not provable — image management not built this pass |
| 4. Staff blocked (403) from store settings/user management | Provable — unchanged from the first pause |
| 5. `assertNumQueries` flat 5→50 (product list) | Provable — unchanged from the first pause |
| 5b. Same, for the variant formset's own N+1 (roadmap's named trap for this deliverable, not the acceptance-gate list, but tested the same way) | **Provable now** — `test_edit_page_query_count_stays_flat_as_variant_count_grows`, flat at 12 queries from 1 to 5 variants |
| 6. Quality gate green, 80% coverage on `portal` | **Provable now** — see numbers below |

Quality gate, actual numbers this pass: `ruff check` — all checks passed. `ruff format --check` —
all files formatted. `mypy .` — no issues in 77 source files. `makemigrations --check --dry-run` —
no changes detected. `pytest` — 150 passed. Coverage: `portal` 96% (floor 80%), `catalog` 96%
(floor 85%), `core`/`store`/`accounts` 100% (floor 80% each). `manage.py check --deploy` clean
under prod settings.

**The Staff-group flush bug — a three-layer diagnosis, worth the full chain for Stage 4 and
Stage 17, both of which will hit adjacent traps:**
1. *Migration-timing layer.* A data migration that queries `Permission.objects.filter(
   content_type__app_label="catalog")` can run **before** those Permission rows exist. Django
   creates each app's default permissions via `post_migrate`, which fires once, only after *every*
   migration in the current run has already applied — a `RunPython` operation runs *during* that
   sequence. On a database that's been migrated incrementally over many separate `migrate` calls
   (this project's dev DB, built up stage by stage) the permissions already exist from earlier
   runs, masking the bug; on a database migrated fresh in one shot (CI, a new clone, pytest's
   `--create-db`) they don't yet exist at that point, and the migration silently creates a group
   with zero permissions. Fixed by calling Django's own `create_permissions()` against the real
   (non-historical) app registry before querying, inside the migration.
2. *Flush layer.* Even with (1) fixed, a `@pytest.mark.django_db(transaction=True)` test's
   teardown calls Django's `flush` command, which truncates every table (including `auth_group`)
   and then re-fires `post_migrate` to restore baseline data — restoring Django's own default
   Permissions (`create_permissions` is itself a `post_migrate` receiver) but *not* anything a
   migration's `RunPython` did, since that's not signal-driven. Confirmed empirically: one
   `transaction=True` test running anywhere in the suite permanently wiped the Staff group for the
   rest of that physical database's life (verified by querying the test DB directly via `psql`
   after a fully-green pytest run). Fixed by adding a `post_migrate` receiver in
   `accounts/apps.py` that reasserts group membership every time migrations settle — `post_migrate`
   fires after both a normal `migrate` *and* a `flush`, which is exactly the coverage the one-time
   migration was missing.
3. *Silent-skip layer — the one that actually explains why (2)'s fix didn't work on the first
   try.* Django's `emit_post_migrate_signal` skips any app whose `AppConfig.models_module` is
   `None` — which is exactly what happens when an app has no `models.py` at all. `accounts` had no
   models (no models needed — it only adds Group/Permission wiring to Django's own `auth`
   models), so its `post_migrate` signal was **never being sent**, meaning the layer-2 receiver
   silently never fired, for either a fresh `migrate` or a `flush`. The fix was adding an empty
   `accounts/models.py` purely so Django's app-loading sets `models_module` to a truthy value.
   This is a real trap, not an edge case: **any future app built without a `models.py` — a
   pure-service app, a pure-views app — that ever needs a `post_migrate` receiver will hit the
   exact same silent failure**, and it will look like the receiver's logic is wrong when the
   receiver is actually just never being called at all. Stage 4's inventory sweeper and Stage 17's
   granular-permissions work are the most likely places this recurs.
- **Open question.** `accounts.apps._sync_staff_group` reasserts the *exact* same permission set
  on every `post_migrate` (both a real `migrate` and a `flush`). That means it also **reverts any
  manual permission change** made through `/django-admin/auth/group/` — if the Owner hand-edits
  the Staff group's permissions outside this code, the next migrate or flush silently takes the
  edit back. Acceptable for Stage 3 (nobody has a reason to hand-edit this group yet, since it's
  catalog-only and freshly seeded). Stage 17 ("staff role and granular permissions") replaces this
  blunt sync-to-a-fixed-set behavior with real permission management and needs to account for this
  — either by making the sync additive-only (never revoke), or by dropping the post_migrate
  resync entirely once there's a portal UI that's the actual source of truth for group membership.
- Gate 4's "store settings and user management" is tested against `/django-admin/`, not a new
  portal view — confirmed empirically that a plain `is_staff=False` user gets redirected (302) by
  django-admin's own login gate rather than denied (403), so the gate-4 test fixture is
  `is_staff=True` (can reach the django-admin login) with Staff-group catalog permissions only (no
  `store`/`auth` permissions) — matching what a real deploy would look like for a trusted employee
  who's never been granted those two permissions specifically.
- Design system (`docs/design.md`) established project-wide, not portal-only — Stage 6's
  storefront inherits the same Tailwind tokens and self-hosted IBM Plex Sans/Mono, diverging in
  layout and voice only, per requirements §1's two-interface split.
- No standalone variant-delete endpoint exists. `portal/product_views.py` is the only place a
  `ProductVariant` is created, edited, or deleted from the portal; deletion happens exclusively
  through the formset's own submission (`formset.deleted_forms`, gated by
  `BaseProductVariantFormSet.clean()`), so it can't bypass that validation. If a future stage ever
  adds a per-row "quick delete" button outside the full form, it needs that same ≥1-variant check
  threaded through explicitly — don't add one without it.

**Product create/edit + variant formset (this pass) — built after an advisor design review per
the human's explicit instruction, which caught two real gaps before any code was written:**
`portal/product_forms.py` (`ProductForm`, `ProductVariantForm`, `BaseProductVariantFormSet`),
`portal/product_views.py` (`ProductCreateView`/`ProductUpdateView`, sharing `_ProductFormsetView`),
`templates/portal/product_form.html`. Gates 1 and 2 now provable; see Gate status below.
- **A third invariant hit the same deferrable-with-condition wall as migration 0003's default
  variant, so it got the same fix.** `variant_unique_attribute_set_per_product` was a partial
  `UniqueConstraint` (`condition=~Q(attribute_signature="")`) — immediate, since Postgres/Django
  forbid combining a unique constraint's `condition` with `deferrable=True`. That breaks two edits
  the formset must support in one transaction: swapping two variants' attribute sets, and deleting
  one variant while reassigning its attributes to a survivor — both legitimately hold a transient
  duplicate signature mid-transaction. Migration 0004 replaces it with a deferred `CONSTRAINT
  TRIGGER`, same mechanism as 0002/0003. Two new tests
  (`catalog/tests/test_product_variant.py`) prove both previously-impossible edits now succeed.
- **`ProductVariant.delete()`'s promotion-on-delete had a real, previously undetected bug: the
  guard condition described in the class docstring was never actually written into the method
  body.** `test_deleting_old_default_after_explicit_reassignment_leaves_the_new_default_alone`
  (written before the fix, per CLAUDE.md's "tests alongside the code") failed against the
  unguarded version, confirming the bug empirically rather than by inspection. Fixed:
  `if was_default and not product.variants.filter(is_default=True).exists():`. This is what makes
  the formset's "save survivors, then delete removed variants" order safe — an explicitly
  reassigned default is already in place by the time the old default is deleted, so the guard
  correctly no-ops instead of racing a second promotion onto a third, unrelated variant.
- **The formset never calls `.save()`.** `BaseModelFormSet.save_existing_objects()` only saves a
  form when `form.has_changed()` — computed from raw submitted data vs. initial, not
  `cleaned_data` — so a default that `clean()` auto-promotes on an otherwise-untouched form would
  be silently skipped by Django's own save path. The view iterates every surviving form and saves
  it unconditionally instead, and reads deletions from `formset.deleted_forms` (available without
  calling `save()`) rather than `formset.deleted_objects` (only populated by `save()` — using it
  here would have silently deleted nothing).
- **`ProductVariantForm.attribute_values`'s `initial` must come from `VariantAttributeValue` rows,
  or editing a product would silently clear every unmodified variant's attributes** — its value
  isn't a model field (the relation is a through table), so `ModelForm` never populates it
  automatically. Verified two ways: a direct unit test on the form's `initial`, and an HTTP-level
  test where an "untouched" variant's row is resubmitted exactly as the browser would echo it back
  (existing `attribute_values`, unchanged) while a second variant is edited to collide with it —
  proving the collision is caught by `clean()` rather than surfacing as an `IntegrityError` from
  `sync_attribute_signature()` once one variant's row is genuinely untouched by the merchant.
- **N+1 in the edit page's variant formset — roadmap Stage 3's own named trap, caught by a
  `CaptureQueriesContext` test before commit, not after.** Two independent sources, both fixed:
  (1) `ProductVariantForm.__init__` read each existing variant's attributes via
  `.values_list("value_id", flat=True)` — always issues its own fresh query regardless of
  prefetching, since only `.all()` with no further queryset method reads a prefetch cache. Fixed
  by prefetching `variant_attribute_values` on the formset's queryset (passed in from the view)
  and reading via `.all()` instead. (2) Every form's `attribute_values` field carries its own
  deep-copied `ModelMultipleChoiceField.queryset` (`BaseForm.__init__` deep-copies every field per
  form instance), and `ModelChoiceIterator.__iter__` re-iterates that queryset on every render —
  one query per variant just to build the `<option>` list, independent of (1). Sharing the same
  queryset *object* across forms doesn't fix this: `_set_queryset` clones via `.all()` on every
  assignment, and `ModelChoiceIterator` calls `.iterator()` (which never touches `_result_cache`)
  unless the queryset carries a `prefetch_related` lookup — confirmed against Django's own source
  comment on that branch. The actual fix: evaluate the choices queryset once in
  `BaseProductVariantFormSet.add_fields()` and assign a materialised `list[(pk, label)]` to
  `field.choices` directly, bypassing `ModelChoiceIterator` for rendering entirely (`field.queryset`
  is untouched and still does its own, unavoidable, POST-only validation query). Measured before
  and after with the same `CaptureQueriesContext` technique gate 5 already uses: 13→21 queries
  (1→5 variants) before either fix, 13→17 after prefetching alone, 12→12 after the materialised-
  choices fix — flat, and the *absolute* count dropped rather than just flattened.
  `portal/tests/test_product_form.py::test_edit_page_query_count_stays_flat_as_variant_count_grows`
  is the permanent regression test.
- `pyproject.toml`'s `[tool.ruff.lint.per-file-ignores]` `"**/forms.py"` pattern (RUF012/ANN401 —
  Django `Meta.fields` lists and `__init__(*args, **kwargs)` passthrough) widened to
  `"**/*forms.py"` to also cover `portal/product_forms.py`, which exists as its own module rather
  than living in `portal/forms.py` only because the formset logic is substantial. Recorded here
  per the comment already in that file demanding it.
- The Stage 2 open question about `catalog.services.create_product()` not calling
  `validate_unique()` (a duplicate `slug` would surface as a raw `IntegrityError`) turns out not to
  apply to this form: `slug` is excluded from `ProductForm.Meta.fields` entirely (auto-generated in
  `Product.save()`), and `core/slugs.py`'s `unique_slugify()` already appends `-2`, `-3`, ... on
  collision rather than raising — verified by reading it, not assumed. Marked resolved *for this
  specific caller* in Open questions below; the underlying question still applies to any future
  caller that passes an explicit `slug`.

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
- [Stage 2] **Resolved for `portal.product_forms.ProductForm` specifically (Stage 3, this pass) —
  still open for any other caller.** `catalog.services.create_product()` calls `Product.save()`,
  which runs `self.clean()` but never `validate_unique()` — a duplicate explicit `slug` (or any
  other `unique=True` field) surfaces as a raw Postgres `IntegrityError`, not a Django
  `ValidationError`. This doesn't affect `ProductForm`: `slug` is excluded from
  `ProductForm.Meta.fields` entirely (it's auto-generated in `Product.save()`), and
  `core/slugs.py`'s `unique_slugify()` already appends `-2`, `-3`, ... on collision rather than
  raising — read directly, not assumed. Still applies to any future caller that passes an explicit
  `slug` value (a management command, a CSV import row with a pre-set slug) — that caller would
  still need its own `validate_unique()`/uniqueness pre-check.
- [Stage 3] `accounts.apps._sync_staff_group` reasserts the exact same fixed permission set on
  every `post_migrate` (a real `migrate` *and* a `flush`), which means it also reverts any manual
  permission edit made through `/django-admin/auth/group/` on the Staff group. Full diagnosis and
  the Stage 17 implication are in this file's Stage 3 notes, above. Assumed in the meantime:
  nobody hand-edits this group before Stage 17 replaces the sync mechanism.
- [Stage 2] `catalog.services._generate_unique_sku()` (and `core.slugs.unique_slugify()`) have a
  check-then-create race: `filter(...).exists()` then `create()`, two statements, no locking
  between them. Two concurrent product creations can pick the same candidate SKU/slug; the
  `unique=True` constraint still catches it as an `IntegrityError` (no silent duplicate), so the
  failure mode is safe, just not graceful. Assumed in the meantime: acceptable for a single-
  merchant admin-driven catalog where concurrent creates are rare. Stage 4 establishes
  `select_for_update()` discipline for real concurrency (stock reservations) — revisit whether
  the same pattern is worth applying here at that point, rather than fixing it in isolation now.

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

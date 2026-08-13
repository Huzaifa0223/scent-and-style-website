# State

Durable project memory. The agent reads this first in every session and updates it at the end of
every stage. It is the answer to "where are we and what is not obvious from the code".

Keep it factual and short. Append to the log; do not rewrite history. If this file and the code
disagree, the code is right and this file is stale — fix it.

---

## Current position

**Stage:** 6 — Storefront: browse, filter, sort (not started)
**Status:** Stage 5 is complete — see the Stage 5 log entry below for the full acceptance-gate and
quality-gate record. Stage 6 has not been started.
**Last updated:** 2026-08-13
**CI:** workflow committed (`.github/workflows/ci.yml`), never executed — no push has been made
to any remote (the human pushes, per CLAUDE.md). Everything it runs has been run locally instead;
see the Stage 1 log entry for that output.

**What's landed so far (all committed, quality gate green):**
`accounts/` (login/logout, `PortalPermissionRequiredMixin`, seeded "Staff" Django Group),
`portal/` product list + Category/Brand/Attribute CRUD + product create/edit with the variant
inline formset + product image management (upload, drag-reorder, primary selection, delete,
replace) + publish/unpublish/feature/unfeature/archive quick actions + a merchant inventory page,
`inventory/` (`StockReservation`, `InventoryAdjustment`, the reservation service layer, the
`release_expired_reservations` sweeper), `search/` (`Product.search_text` denormalisation +
rebuild signals, `PostgresSearchBackend` blending `ts_rank` with trigram word-similarity, the
`rebuild_search_index` command, an HTMX type-ahead endpoint), a project-wide design system
(`docs/design.md`, `tailwind.config.js` tokens, self-hosted IBM Plex). Stages 1-5 are fully built;
Stage 6 (storefront browse/filter/sort) is next and not started. No `storefront` app exists yet —
Stage 5's type-ahead endpoint lives in `search/` instead, since it didn't need one to exist (see
Stage 5 notes).

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

### Stage 3 — Merchant portal: catalog management
Completed: 2026-08-12
Commits: 029f20b fix(catalog) default-variant promotion
         e419e76 feat(accounts,portal) auth + portal shell + catalog CRUD
         9a5a15e feat(design) design system
         57407b9 fix(catalog) deferred attribute-signature constraint + default-promotion guard
         56ce9d1 feat(portal) product create/edit views and variant formset
         ae024fc docs: record product formset lessons in CLAUDE.md and state.md
         e8ea571 fix(catalog) deferred one-primary-image constraint + promotion guard
         091ee05 feat(portal) product image management
         d8f2081 docs: record image management gate 3 and fixes in state.md
         4dffa39 test(portal) assert on message level, not escaped wording
         475fddd docs: correct mypy scope claim, record SECRET_KEY deploy-check trap
         c28114a feat(portal) add product publish/unpublish/feature/unfeature/archive
Acceptance gates: all passed
  1. A merchant can create a product with three variants across two attributes and publish it,
     without touching Django admin — `portal/tests/test_product_form.py::test_gate1_...`. Two
     publish paths exist and both satisfy this gate: `ProductForm`'s own `status` field (used by
     the gate-1 test, set directly on create) and the dedicated `ProductPublishView` quick action
     added this pass (`portal/tests/test_product_actions.py`), which is what a merchant actually
     clicks from the product list row. The form field is canonical for "set status while editing
     everything else"; the action view is canonical for the one-click case the roadmap lists
     separately. Recording which is which so a future session doesn't have to guess.
  2. Deleting a variant that is the last remaining variant is refused with a clear message —
     `test_gate2_...`; the formset's own `clean()`, not the DB trigger, is what the merchant sees.
  3. Reordering images persists and survives a reload —
     `portal/tests/test_image_management.py::test_gate3_reordering_persists_and_survives_a_reload`.
  4. A staff user is blocked (403, not a hidden link) from store settings and user management —
     `portal/tests/test_permissions.py`, tested against `/django-admin/` (the portal has no
     store-settings/user-management page of its own yet — Stage 17's job).
  5. `assertNumQueries` stays flat as the fixture count grows from 5 to 50 on the product list —
     `test_query_count_stays_flat_as_fixture_count_grows_from_5_to_50`. Re-verified after this
     pass added four `{% include %}`s and five `{% url %}` resolutions per row for the new quick
     actions: flat at **8 queries at both 5 and 50 products** — URL reversal and template includes
     cost no queries, so the row actions didn't move this number.
  5b. Same technique, for the variant formset's own N+1 (roadmap's named trap for this deliverable,
      not the acceptance-gate list, but tested the same way) —
      `test_edit_page_query_count_stays_flat_as_variant_count_grows`, flat at 12 queries from 1 to
      5 variants.
  5c. Same technique, for the image formset's N+1 (same named trap) —
      `test_edit_page_query_count_stays_flat_as_image_count_grows`, flat at 14 queries from 1 to 5
      images.
  6. Quality gate green, coverage floor 80% on `portal` — see numbers below.

Quality gate, final numbers: `ruff check` — all checks passed. `ruff format --check` — all files
formatted (90 files). `mypy .` (whole tree — CLAUDE.md's definition of done and CI both run it
unscoped; an earlier draft of this entry reported a `mypy portal/ catalog/` scoped run instead,
which was wrong and is corrected here rather than carried forward, since scoping mypy to only the
apps a pass touched is exactly how an error in an untouched file would reach CI unnoticed) — no
issues in 82 source files. `makemigrations --check --dry-run` — no changes detected. `pytest
--create-db` — 187 passed. Coverage: `portal` 97% (floor 80%), `catalog` 96% (floor 85%).
`manage.py check --deploy` clean under `config.settings.prod` (DEBUG=False, ALLOWED_HOSTS set, a
real random `SECRET_KEY` via `get_random_secret_key()` — see Notes below, placeholder R2
credentials). `manage.py check` clean under `config.settings.dev`.
Coverage: portal 97%, catalog 96% (floors 80%/85%)
Notes:

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

**Product image management (this pass).** `portal/image_forms.py` (`ProductImageUploadForm`,
`ProductImageReplaceForm`), `portal/image_views.py` (`ProductImageUploadView`,
`ProductImageReorderView`, `ProductImageDeleteView`, `ProductImageReplaceView`), the Images section
of `templates/portal/product_form.html` (SortableJS drag-reorder, per-row primary radio, replace
and delete as hidden sibling `<form>`s referenced via the file input's `form="replace-form-N"`
HTML5 attribute so they don't nest inside the reorder `<form>`). Gate 3 now provable; see Gate
status above.

- **The fourth instance of the deferrable-with-condition trap**, same as the default-variant and
  attribute-signature constraints before it: `productimage_one_primary_per_product` was a partial
  `UniqueConstraint` (`condition=Q(is_primary=True)`), immediate because Postgres/Django forbid
  combining a unique constraint's `condition` with `deferrable=True`. That breaks a combined
  reorder+re-primary submit, which briefly holds two (or momentarily zero) primary images
  mid-transaction depending on statement order. Confirmed the constraint's shape by reading
  `catalog/models.py` directly *before* writing the reorder handler, per the human's explicit
  instruction, rather than discovering it after a handler failed. Migration 0005 replaces it with a
  deferred `CONSTRAINT TRIGGER`, same mechanism as 0002/0003/0004. Two tests
  (`catalog/tests/test_product_image.py`) prove the swap-primary and delete-and-reassign-primary
  cases both now succeed, mirroring the variant precedent exactly.
- **`ProductImage.delete()`'s promotion-on-delete had the same latent bug as
  `ProductVariant.delete()`** — a guard described in the docstring but never written into the
  method body. `test_deleting_old_primary_after_explicit_reassignment_leaves_the_new_primary_alone`
  written first, confirmed it failed against the unguarded code, then fixed:
  `if was_primary and not product.images.filter(is_primary=True).exists():`.
- **N+1 in the image formset, same shape as the variant formset's own named trap, caught by a
  `CaptureQueriesContext` test written before the feature existed** (trivially green with zero
  images at the time; the real measurement came after the feature was built). Each image row's
  "hero image for: SKU" note reads `ProductVariant.image`'s reverse accessor
  (`related_name="variants"`) — without prefetching, one query per image. Fixed by
  `product.images.prefetch_related("variants")` in `_ProductFormsetView._render()`. Flat at 14
  queries from 1 to 5 images.
- **Permission separation is a real endpoint split, not a shared view with a branch.** Upload and
  reorder need `catalog.add_productimage`/`catalog.change_productimage`; delete needs
  `catalog.delete_productimage`. The seeded Staff group (`accounts/permissions.py`) has the first
  two but never delete, on any app — so `ProductImageDeleteView` is its own endpoint specifically
  so a staff user can add, reorder, and replace images but never remove one. Tested directly
  (`test_staff_without_delete_permission_cannot_delete_an_image`, expects 403).
- **Two real bugs an advisor review caught before this pass was reported done, both fixed and
  regression-tested — worth recording since neither was visible from the passing test suite that
  existed at the time:**
  1. The reorder handler's `enumerate(order)` assigned dense positions `0..N-1` over only the
     *submitted* ids. If a submit ever omits an image (a stale page after another tab deleted one,
     a partial submit), the omitted image kept its old position — which now collides with whatever
     the submitted images were just reassigned to, and `Meta.ordering = ["position", "id"]` breaks
     the tie silently rather than raising. Existing tests all submitted every image, so this passed
     clean. Fixed by applying the submitted order first, then appending any unsubmitted images
     after in their existing relative order, so positions stay dense and distinct regardless of
     whether the submit is complete. Regression test:
     `test_reorder_with_an_omitted_image_does_not_collide_positions`.
  2. `test_deleting_an_image_nulls_the_variant_fk_and_warns_the_merchant` claimed to mirror Stage
     2's direct-delete test but didn't test the case that actually matters: both tests deleted the
     *only* image, exercising only the `next_image is None` branch of the promotion guard. Neither
     exercised deleting a referenced image while a second image survives — the case where the
     promotion guard and the variant's `SET_NULL` fire in the same `delete()` call. Rewrote the
     test to add a second, non-primary image before deleting the primary one, and assert both
     `variant.image_id is None` and that exactly one image is primary afterward.
- **A separate, later review (the human's own, not the advisor's) caught an access-control gap
  before any of this was reported done: the reorder handler accepted any submitted image id without
  checking it belonged to the product in the URL.** `ProductImageDeleteView`/`ProductImageReplaceView`
  already scoped their `get_object_or_404` lookups with `product=product`, but the reorder handler
  only silently skipped (`images.get(id)` → `None` → `continue`) ids that weren't in the current
  product's image set — meaning a crafted `order` or `primary_image` referencing another product's
  image id would be silently dropped rather than rejected, which is the wrong failure mode for a
  request that shouldn't have been accepted at all. Fixed: the view now returns `400` if any
  submitted id in `order` or `primary_image` doesn't belong to the product. Regression tests:
  `test_reorder_rejects_an_image_id_belonging_to_another_product`,
  `test_reorder_rejects_a_primary_selection_belonging_to_another_product`,
  `test_delete_under_the_wrong_product_pk_returns_404`,
  `test_replace_under_the_wrong_product_pk_returns_404` (the latter two proving the existing
  delete/replace scoping, which was already correct).
- **The replace file input's `form="replace-form-N"` HTML5 attribute — the mechanism that lets a
  file input inside the reorder `<form>` submit to a separate, hidden `<form>` elsewhere in the
  DOM — cannot be exercised by the Django test client at all**, since there's no DOM/JS engine
  behind it; every existing replace test POSTs directly to the endpoint, bypassing the HTML
  association entirely. Verified live instead: started the dev server, logged in via Chrome
  automation, uploaded a file to a row's `<input form="replace-form-N">`, clicked that row's
  Replace button, and confirmed via the dev server's own access log that the request landed on
  `POST /admin-portal/products/<id>/images/<id>/replace/` (not the reorder endpoint) and that the
  image's stored file, position, and `is_primary` changed exactly as the replace endpoint alone
  would produce — confirmed directly against the dev database. Temporary superuser, product, and
  uploaded file all removed afterward; nothing from this check is in the dev database or repo.
- Confirmed SortableJS is committed at `static/vendor/sortable.min.js` (1.15.6, pinned — same
  "vendored means committed" reasoning as HTMX/Alpine's Stage 1 amendment) and loaded via
  `{% static %}` in `templates/portal/base.html`, not a CDN; `extra_body` is a real block on that
  template, so `templates/portal/product_form.html`'s `{{ block.super }}` renders the vendored
  `<script>` tag before its own inline `Sortable(...)` init runs.
- `test_upload_with_an_invalid_file_shows_an_error_and_adds_nothing` originally asserted the
  HTML-escaped literal `Couldn&#x27;t add that image` in the response body — brittle against any
  rewording or punctuation change to the message text. Fixed to assert on
  `django.contrib.messages.get_messages(response.wsgi_request)`'s `level_tag == "error"` instead,
  which survives a reword entirely.
- **`manage.py check --deploy` under `config.settings.prod` needs a genuinely random
  `SECRET_KEY`, not just any 50+-character string.** Django's `security.W009` check
  (`django.core.checks.security.base`) rejects a key that has fewer than 5 unique characters or is
  prefixed `django-insecure-`, in addition to the length floor — a hand-typed placeholder like
  `"deploy-check-<timestamp>-random-secret-key-value"` passes the length check but still fails
  `W009` on the uniqueness heuristic. The working invocation generates one properly:
  `SECRET=$(python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")`,
  then passes it via the environment alongside `DEBUG=False`, `ALLOWED_HOSTS`, and placeholder
  `AWS_*` values (`.env`'s own `DEBUG=True` is picked up by `environ.Env.read_env()` on import and
  is *not* overridden by a same-named shell environment variable set after the fact in the same
  command line — the override must be set before Django's settings module is imported, which an
  inline `VAR=value command` prefix satisfies and a `.env` edit does not). Recording this so the
  next session that needs to re-run this check doesn't rediscover it by trial.

**Publish/unpublish/feature/unfeature/archive (final pass, closing out Stage 3).**
`portal/product_actions.py` (`ProductPublishView`, `ProductUnpublishView`, `ProductArchiveView`,
`ProductFeatureView`, `ProductUnfeatureView`), row action buttons on
`templates/portal/product_list.html` via a new shared partial
(`templates/portal/_row_action_button.html` — the button shape repeats up to four times per row,
so it's a partial rather than four copies of the same inline Tailwind class string, per CLAUDE.md's
"one partial per reusable unit"). This closes the last gap in Stage 3 — every acceptance gate is
now provable; see Acceptance gates above.
- **Same endpoint-per-action shape as the image management split, and the same reasoning
  restated for a case where it produces a *different* answer.** Each action is its own view,
  POST-only (no `get()` defined, so Django's `View.dispatch()` 405s anything else), each declaring
  its own `permission_required`. Unlike the image split, all five resolve to the *same* Django
  permission (`catalog.change_product`) rather than different ones — Django's built-in codenames
  don't distinguish "publish" from "archive"; both are a change to an existing `Product` row, not a
  create or delete. The seeded Staff group already holds `change_product`, so Staff can use all
  five actions, same as it can already edit a product through the full form.
- **No transition is blocked by current status, deliberately.** Publish works from any status,
  including reversing an archive — there is no separate "unarchive" action because the roadmap's
  five-action list doesn't include one and publish already covers that transition. Requirements
  specifies an explicit allowed-transition map for *orders* (§25) but says nothing of the kind for
  product status, so adding one here would be an invented constraint, not a spec requirement.
  Archiving a featured product leaves `is_featured` untouched — unfeaturing is a separate,
  deliberate action a merchant fires on its own, not an implicit side effect of archiving.
- **The archive decision, checked before writing any code and recorded here (not only in
  `product_actions.py`'s module docstring) since this is what Stage 6 will need to read.** Grepped
  the whole repo for anything that references a product by status before deciding what archive
  should do: only `portal.views.ProductListView` (the status filter) and
  `portal.product_forms.ProductForm` (the status field) do, and neither is affected by what archive
  itself does — no `cart`, `orders`, `inventory`, `search`, or `storefront` app exists yet
  (roadmap Stages 4/6/7/8), so nothing in this codebase today holds a reference to a product by
  status that archiving could break. Decision, for those stages to honor once built: **archive is
  a pure status transition** — `Product.status = ARCHIVED` and nothing else, no variant
  deactivated, no image touched, nothing deleted. Two obligations this creates downstream:
  (1) Stage 6's storefront browse/search/PDP must filter on `status=PUBLISHED` (the same field the
  portal list already filters on) to hide archived and draft products from customers; (2) archiving
  must stay non-destructive specifically because a future `OrderItem` is already specified as an
  immutable snapshot that never reads back through the variant FK for display (CLAUDE.md's locked
  decision) — that snapshot's FK must keep resolving even after the product it snapshotted is later
  archived. A variant's own `is_active` flag stays a separate, independent lever a merchant can
  still set regardless of the product's status; archive does not touch it.
- Advisor review before this pass was reported done caught two things, both fixed: a test
  (`test_archive_...does_not_touch_variants`) asserted `variant.stock_quantity == product.variants.
  get().stock_quantity` — both sides re-read the same freshly-saved row, so the comparison was
  tautological and would have passed regardless of what archive did to stock. Fixed to capture the
  value before the POST and compare against that. Also flagged that gate 5 hadn't been re-run since
  the template it measures changed; re-run explicitly and reported above (flat at 8, unchanged).

### Stage 4 — Inventory and stock reservation
Completed: 2026-08-13
Commits: a275730 feat(inventory,store) StockReservation/InventoryAdjustment models
         27d89fc fix(catalog) available_quantity as a Subquery annotation
         93c1a76 feat(inventory) reservation service layer + concurrency tests
         79c841f feat(inventory) release_expired_reservations sweeper command
         0a6cafc feat(portal) merchant inventory page
         091cce8 chore: inventory coverage floor in CI, fifth ANN401 pattern
Acceptance gates: all passed
  1. Reserve then confirm decrements on-hand and clears the reservation —
     `inventory/tests/test_services.py::test_gate1_reserve_then_confirm_decrements_stock_and_clears_reservation`.
  2. Reserve then expire releases the reservation and leaves on-hand untouched —
     `test_gate2_reserve_then_expire_releases_and_leaves_stock_untouched`.
  3. Reserve then cancel releases without touching on-hand —
     `test_gate3_reserve_then_cancel_releases_without_touching_stock`.
  4. Restore after a post-confirmation cancellation increments on-hand —
     `test_gate4_restore_after_post_confirmation_cancellation_increments_stock`.
  5. **Concurrency test** — two simultaneous reservations for the last unit, exactly one succeeds,
     the other fails with `InsufficientStockError`. Real threads, real separate database
     connections, `transaction=True` (`inventory/tests/test_concurrency.py::
     test_two_concurrent_reservations_for_the_last_unit_exactly_one_succeeds`). Verified, not
     assumed, to have teeth: run once against a build of `reserve()` with `select_for_update()`
     removed, 104/200 iterations (52%) oversold; restored, 0/200. That verification script is not
     committed (it required editing `services.py` to prove a negative); the permanent, deterministic
     guard is `test_reserve_locks_the_variant_row_with_select_for_update`, which asserts `FOR UPDATE`
     actually appears in the captured SQL rather than relying on timing.
  6. The sweeper is safe to run twice concurrently — `test_gate6_sweeper_is_safe_to_run_twice_concurrently`
     (two real threads, both call `release_expired_reservations()`, total released across both
     equals the fixture count exactly once). True by construction, not just by test: a bulk
     `DELETE ... WHERE expires_at <= now()` needs no lock at all — see Notes.
  7. Every adjustment writes an `InventoryAdjustment` row —
     `test_gate7_manual_adjustment_writes_an_inventory_adjustment_row`, plus `commit_reservation`
     and `restore` each have their own dedicated assertion on the audit row they write.
  8. Quality gate green. Coverage floor 90% on `inventory` — see numbers below.

Quality gate, final numbers: `ruff check` — all checks passed. `ruff format --check` — all files
formatted (105 files). `mypy .` (whole tree, unscoped) — no issues in 97 source files.
`makemigrations --check --dry-run` — no changes detected. `pytest --create-db` — 224 passed.
Coverage: `inventory` 98% (`services.py` 100%, `models.py` 90% — only two untested `__str__`
methods; floor 90%). `manage.py check --deploy` clean under `config.settings.prod` (DEBUG=False,
ALLOWED_HOSTS set, a real random `SECRET_KEY` via `get_random_secret_key()`, placeholder R2
credentials). `manage.py check` clean under `config.settings.dev`.
Coverage: inventory 98% (floor 90%)
Notes:

**Design was printed and reviewed by advisor before any code was written, per the human's explicit
instruction — the review caught three real issues, all fixed before implementation:**
1. `is_low_stock` was originally going to derive from `available_quantity`, same as `is_in_stock`.
   Advisor caught that this conflates two different questions: `is_in_stock` is customer-facing
   ("can this be bought right now" → availability), `is_low_stock` is merchant-facing ("I have 3
   left on the shelf, reorder" → on-hand). Basing low-stock on availability would make it flicker
   on and off as unrelated reservations are created and expire against the same physical stock,
   telling a merchant to reorder when they have plenty on the shelf. Fixed: `is_low_stock` derives
   from `stock_quantity`, `is_in_stock` from `available_quantity` — different expressions,
   documented in `with_available_quantity()`'s own docstring so a future reader doesn't "fix" the
   inconsistency back.
2. The three places that decide "is this reservation still active" (`reserve()`'s own check, the
   `with_available_quantity()` annotation, the sweeper's bulk delete) originally mixed Python's
   `timezone.now()` and the database's `Now()`. Advisor flagged this as a real inconsistency, not
   theoretical — three call sites deciding the same predicate from two different clocks. Fixed: all
   three compare against `Now()` (`django.db.models.functions`), never `timezone.now()`, except for
   the one place that must produce an actual Python value to store (`expires_at`'s own write).
3. The original concurrency test (barrier-synchronised threads only) could pass even with
   `select_for_update()` removed — the oversell window is microseconds wide and a barrier alone
   doesn't force it. Verified empirically before trusting gate 5 (see gate 5 above for the numbers)
   and added a second, deterministic test that asserts the lock is actually issued
   (`test_reserve_locks_the_variant_row_with_select_for_update`), rather than relying on timing
   alone to occasionally expose its absence.
4. (Naming, not a design issue) `adjust()`'s quantity parameter was originally `new_quantity`;
   advisor flagged that `restore(quantity=...)` is a delta and `adjust(new_quantity=...)` is
   absolute — same-looking argument, two different meanings, one call away from silently corrupting
   stock. Renamed to `absolute_quantity`.

**A second, independent review — the user's own, mid-implementation, before the portal page was
built — caught a real fan-out bug that both the design print and the advisor review missed:**
`with_available_quantity()`'s first implementation used `Sum("reservations__quantity", filter=
Q(reservations__expires_at__gt=Now()))` — a join-based aggregate, the same idiom
`ProductQuerySet.with_pricing()` already uses safely for `display_price`. The difference: that
method is on `Product`, which has no *second* to-many relation routinely joined alongside its own
aggregate. This one is on `ProductVariant`, which already has `variant_attribute_values` (another
to-many reverse relation) — and the moment a caller's queryset joins *that* relation too (Stage 3's
attribute filtering does this routinely; Stage 6's listing page is expected to combine variant
availability with other per-variant joins), two to-many tables joined into one query multiply rows
before `GROUP BY` collapses them back down, so the sum silently overcounts by whatever multiplier
the other join contributed. Verified, not assumed: temporarily reverted to the join-based form and
ran `inventory/tests/test_available_quantity_fan_out.py` — both tests failed exactly as the
mechanism predicts (2 reservations × 2 attribute values read as `reserved_quantity=10`, not 5; a
second scenario with 3×3 read as 9, not 3). Restored a `Subquery`/`OuterRef` form (evaluated
independently per outer row, immune to whatever else the caller's queryset joins) and reran — both
tests pass. `reserved_quantity` is now its own named annotation (not just embedded inside
`available_quantity`'s expression) so the portal inventory page can display it directly, and so
`is_in_stock`/`is_low_stock` reference it/`stock_quantity` rather than re-deriving it. A third test
(`test_the_safe_pattern_for_combining_with_pricing_and_with_available_quantity`) documents the
actually-safe way to combine `with_pricing()` and `with_available_quantity()` for Stage 6:
`Prefetch()`, which runs as its own query and can never fan out against a JOIN-based annotation on
a different queryset.
- `with_available_quantity()` resolves `StockReservation` via `django.apps.apps.get_model(
  "inventory", "StockReservation")` rather than a top-level `from inventory.models import
  StockReservation` — catalog must not import from an app that depends on it (the same direction
  CLAUDE.md states for catalog/orders). This is the Django-idiomatic way to build a real `Subquery`
  queryset from app B inside app A's queryset method without a static import creating that
  dependency at the Python import-graph level.
- **`StockReservation` has no `order` FK yet — a real technical blocker, not a style choice,
  resolved before writing any code.** The roadmap's Stage 4 deliverable line says "order FK nullable
  until stage 8," but `orders.Order` doesn't exist until Stage 8 builds it, and Django cannot define
  a `ForeignKey` to a model in an app that isn't installed (`manage.py check` would fail with E300).
  Read "nullable until stage 8" as describing the field's eventual shape, not something Stage 4
  could literally build now; the field will be added via `AddField` when Stage 8 creates
  `orders.Order`. Recorded under Proposed spec amendments below.
- **`InventoryAdjustment.reason` is always caller-determined or hardcoded, never a free-choice
  parameter for the merchant.** `adjust()` (manual) always writes `Reason.MANUAL` — no ambiguity,
  that path is only ever taken for manual counts. `commit_reservation()` always writes
  `Reason.ORDER_CONFIRMED` — same reasoning. `restore()` takes `reason` as a required parameter
  because the caller (Stage 8/10's order workflow) is the one who knows whether this is a
  cancellation or a return; that distinction doesn't belong to the inventory service layer.
- **The portal inventory page is Owner-only, not Staff — a permission decision already made by a
  prior stage, not a fresh one.** `accounts/permissions.py`'s `_STAFF_PERMISSION_APP_LABELS =
  ("catalog",)` docstring already says "requirements §32's fuller orders/inventory/customers scope
  arrives in roadmap Stage 17, which extends `_STAFF_PERMISSION_APP_LABELS`" — Staff is deliberately
  meant to have zero `inventory` app permissions until then. `InventoryListView`/`InventoryAdjustView`
  are gated on `inventory.view_stockreservation`/`inventory.add_inventoryadjustment` rather than any
  `catalog.*` permission specifically so this holds without special-casing — Staff has no grant on
  those codenames, so `PortalPermissionRequiredMixin` blocks them (403) automatically. Tested
  directly (`portal/tests/test_inventory.py::test_staff_cannot_view_the_inventory_page`,
  `test_staff_cannot_post_an_adjustment`).
- **Open question, not fixed this stage.** Stage 3's `ProductVariantForm` (the product edit page's
  variant formset) still includes `stock_quantity` as a directly-editable field — set on the roadmap
  itself ("variant inline formset (SKU, price, compare-at, stock, ...)"), and edits through it write
  straight to the row via `variant.save()`, bypassing `inventory.services.adjust()` entirely and
  writing no `InventoryAdjustment` row. This is a real gap in the audit-completeness gate 7 claims
  to guarantee, but removing the field would contradict Stage 3's own explicit, already-shipped
  roadmap deliverable and break its existing gate-1 test. Left as-is, consistent with how this
  codebase already treats Django admin bypassing service-layer validation (`catalog/services.py`'s
  own docstring: "the deferred constraint trigger... is the backstop for anything that bypasses it
  \[the service\] (Django admin, a raw script)") — a DB-level backstop rather than a hard guarantee
  every write path is audited. Revisit if audit completeness ever needs to be airtight (the future
  `audit.AuditLog` app, or Stage 17's fuller inventory permissions).
- Fifth `[tool.ruff.lint.per-file-ignores]` `ANN401` pattern added:
  `"**/management/commands/*.py"` — a management command's `handle(*args, **options)` must match
  Django's own `BaseCommand` signature, same reasoning as the existing CBV/form overrides. Generic
  across apps (not `inventory`-specific) since Stage 13's backup job will be another one. The
  section's own comment says a fifth pattern must be recorded here rather than just appended silently
  — this is that record.
- `release_expired_reservations`'s idempotency and concurrency-safety are true by construction, not
  just by test: a bulk `DELETE ... WHERE expires_at <= now()` needs no `select_for_update()` at all
  — two sweepers racing each other simply both issue the same statement; whichever commits first
  deletes the matching rows, the other matches zero of them and returns 0. No lock contention beyond
  what Postgres already does for any `DELETE`, no double-processing, no error path. Cron entry (every
  10 minutes) documented in `README.md`.
- Portal inventory page verified live in a browser (not just the Django test client): logged in,
  confirmed on-hand/reserved/available/status render correctly for a variant with an active
  reservation, set a new stock count via the inline adjustment form and confirmed the success
  message and recalculated available quantity, and confirmed the low-stock filter correctly
  excludes a variant once its stock is raised above the threshold. Temporary superuser and fixture
  product removed afterward; nothing from this check is in the dev database or repo.

### Stage 5 — Search
Completed: 2026-08-13
Commits: b392d6f feat(catalog) search_text denormalisation and rebuild signals
         ba017f9 feat(search) PostgresSearchBackend covering all six §15.1 cases
         6d1bb86 feat(search) rebuild_search_index command and type-ahead endpoint
         8375053 fix(catalog) disable GIN fastupdate on search indexes
         0ed4469 fix(search) use contains not icontains for suggest()'s trigram match
         48c686e fix(search) blend TrigramWordSimilarity into search() ranking
Acceptance gates: all passed
  1. **§15.1 table written as tests first, watched fail, then implemented.** All six cases —
     `search/tests/test_backend.py`, one fixture per case (`afnan 9pm`, `9pm`, `AFNAN`, `afnn`,
     `9PM afnan`, partial SKU `EDP-9PM-100` against a longer stored SKU), plus decoys that must
     *not* match and an unpublished-product exclusion check. The test file was written and run
     against a nonexistent `search.backends` module first — confirmed
     `ModuleNotFoundError: No module named 'search.backends'` — before `PostgresSearchBackend` was
     written.
  2. Renaming a product updates `search_text` without a manual command —
     `catalog/tests/test_search_indexing.py::test_renaming_a_product_updates_search_text_without_a_manual_command`.
  3. `rebuild_search_index` is idempotent and reports a count —
     `search/tests/test_rebuild_search_index_command.py` (reports total and recomputed-count
     separately since a fresh product's `search_text` is already correct via the live signal, so
     "recomputed" is legitimately 0 right after creation; a raw-`.update()`-bypassed-the-signal
     scenario proves the count is real, not always zero; a second consecutive run recomputes
     nothing).
  4. **1,000-product fixture, timed, EXPLAIN-verified index usage** —
     `search/tests/test_performance.py`. This gate surfaced a real bug; see Notes below — it does
     not pass by asserting a weaker claim than the roadmap asks for.
  5. No view imports `PostgresSearchBackend` directly — `search/tests/test_views.py::
     test_no_view_module_imports_postgressearchbackend_directly`, an AST-parsed check (not a
     substring grep — a substring check false-positived on `backends.py`'s own docstring
     mentioning the class by name) across every `*views.py` file in the repo.
  6. Quality gate green. Coverage floor 90% on `search` — see numbers below.

Quality gate, final numbers: `ruff check` — all checks passed. `ruff format --check` — all files
formatted (121 files). `mypy .` (whole tree, unscoped) — no issues in 113 source files.
`makemigrations --check --dry-run` — no changes detected. `pytest --create-db` — 257 passed.
Coverage: `search` 100% (all files), `catalog/search_indexing.py` 100%, `catalog/signals.py` 100%.
`manage.py check --deploy` clean under `config.settings.prod` (DEBUG=False, ALLOWED_HOSTS set, a
real random `SECRET_KEY`, placeholder R2 credentials). `manage.py check` clean under
`config.settings.dev`.
Notes:

**A second advisor review, after the stage otherwise looked complete, caught that the roadmap's
"ranking blending `ts_rank` with `word_similarity`" deliverable was only half-shipped.**
`TrigramWordSimilarity` had never actually been used — the printed design's `.order_by("-rank",
"-word_sim")` had quietly become `.order_by("-rank", "-created_at")` during implementation, and
nothing caught it: `search()` used `%>` for *matching* but the similarity score was never computed
for *ranking*, so every typo-only or partial-SKU-only match (no tsvector lexeme overlap at all)
ties at `rank=0` and silently falls back to creation order. Gate 1's assertions are membership
(`product in results`), which passes regardless of position — this is exactly the kind of gap a
membership-only test can't see. Confirmed both ways before and after the fix: three products
differing only in edit-distance from the query, deliberately created in the *opposite* of quality
order, returned worst-match-first before adding `TrigramWordSimilarity` to `order_by()` and
best-match-first after — recorded permanently as
`search/tests/test_backend.py::test_results_are_ordered_by_relevance_not_just_creation_order`. Gate
4's EXPLAIN was re-run with the new annotation present (it lives in SELECT/ORDER BY, not WHERE, so
shouldn't affect the plan the way `rank__gt=0` did) — confirmed still index-backed, unaffected.

**Gate 4 (EXPLAIN proves index usage) failed for a real reason three times before it passed for
the right one — GIN's `fastupdate` pending list, not row count.** First attempt used a 1,000-row
fixture and got a plain `Seq Scan`; assumed the table was just too physically small (21 pages) for
the GIN index to look cheaper than a sequential scan regardless of selectivity, and grew the
fixture to 3,000, then 5,000, then 10,000 rows — all still `Seq Scan`, cost scaling linearly with
row count the whole time, which is itself evidence the *index* side of the cost comparison wasn't
moving, only the table side was. Advisor caught the actual mechanism on the first pass: GIN indexes
default to `fastupdate=on`, so entries from a bulk insert land in an unordered "pending list" that
only `VACUUM` flushes — not `ANALYZE`. Until flushed, `gincostestimate` prices every index scan for
scanning that whole pending list, so the planner correctly (from its own, stale, perspective)
prefers the sequential scan. **This is a fourth "looks verified but isn't" trap in the family
CLAUDE.md already documents three of** (the three deferred-constraint-trigger cases, and
`manage.py shell`'s autocommit): a direct diagnostic — `SELECT reltuples, relpages FROM pg_class`
right after `ANALYZE` — showed perfectly accurate table statistics (1000.0 / 21, matching the real
count exactly) while the query plan stayed wrong, because `ANALYZE` updates table-level statistics,
not the GIN index's own internal pending-list state. Checking the table's stats proved nothing
about the index's.

Confirmed the mechanism directly rather than trusting the diagnosis: `VACUUM ANALYZE` (not
`ANALYZE`) flipped the plan to `BitmapOr` across both GIN indexes at the same 1,000-row fixture.
Rather than accept a test that depends on autovacuum's timing (which would also mean *production*
search silently degrades to a sequential scan after every catalog import, with no error, until
autovacuum happens to run — a real risk for a single merchant whose edits are infrequent bursts
against constant search read traffic), both GIN indexes are now declared with `fastupdate=False`
(`catalog/models.py`, migration `catalog/0007_search_indexes_fastupdate_off`). Confirmed this
removes the dependency on `VACUUM` entirely: a plain `ANALYZE` after a fresh bulk insert is now
enough for the planner to choose `BitmapOr` correctly, and the gate 4 test runs as a normal
`@pytest.mark.django_db` fixture (rolled back, not committed) rather than needing
`transaction=True` plus a manual teardown. **Migration 0007 drops and recreates both GIN indexes on
`catalog_product` — relevant to whoever runs the deploy; on a table with real production data this
is a rebuild, not a free schema change.** `GATE_4_FIXTURE_SIZE` is 1,000, matching the roadmap
literally — the earlier 3,000+ fixture sizes were a documented-then-discarded wrong turn, not a
real deviation, and nothing about that path survived into the committed test.

**A second, separate index-usability bug, advisor-caught in a post-implementation review (not
caught by the six-case tests, since none of them go through `suggest()`):** `suggest()`'s original
`search_text__icontains=normalized` compiles to `UPPER(search_text) LIKE UPPER('%...%')` on
Postgres — the `UPPER()` wrapper on the indexed column makes `product_search_trgm_gin`
structurally unusable, confirmed with `SET enable_seqscan = off`: `icontains` still couldn't reach
the index at all (fell back to the `status` index plus a residual per-row filter), while `contains`
used `product_search_trgm_gin` via a `Bitmap Index Scan`. Fixed by switching to `search_text__contains`
— since `search_text` is stored pre-lowercased and the query is `.lower()`'d before use, this is
semantically identical, not a correctness-for-speed trade-off; it also makes true a claim
`compute_search_text()`'s own docstring was already making about why pre-lowering matters. Not a
separate gate 4 requirement (gate 4 covers `search()`, not `suggest()`), so no dedicated EXPLAIN
test exists for this path — recorded here instead.

**Query shape matters for gate 4, and was verified against real Postgres before being written into
`search/backends.py`, not assumed from the ORM API:** filtering on a `SearchRank` annotation
(`.filter(rank__gt=0)`) forces `ts_rank` evaluation into the WHERE clause, which the planner cannot
satisfy from the GIN index — confirmed via `.explain()` that this form is *always* a `Seq Scan`,
independent of the pending-list issue above. The index-usable form annotates the vector and filters
`.filter(search=ts_query)` (Django's `@@` translation); `SearchRank` is used for `order_by` only.
`GinIndex(SearchVector(...), ...)` itself (the tsvector index's expression) was also verified before
use: Django generates the two-argument `to_tsvector('simple'::regconfig, COALESCE(search_text, ''))`
form with an explicit `::regconfig` cast, which is genuinely immutable and Postgres accepts directly
— no raw-SQL `RunSQL` fallback was needed, unlike what the pre-implementation design review flagged
as a real possibility.

**A real, unrelated migration-dependency bug found while verifying the above, fixed before it ever
reached a fresh `--create-db` run:** the autogenerated `catalog/migrations/0006_search_indexes.py`
only declared a dependency on `catalog/0005`, not on `core/0001_enable_pg_trgm` — Django has no way
to infer that dependency from a `GinIndex(..., opclasses=["gin_trgm_ops"])` declaration, since it's
an opclass reference, not an FK. Without it, migration order between the two apps is unconstrained,
and a fresh `migrate` failed with `operator class "gin_trgm_ops" does not exist for access method
"gin"` the first time this was tested end-to-end (it had been silently working locally only because
`core/0001` happened to already be applied from Stage 1, long before this session). Fixed by adding
the dependency explicitly, with a comment explaining why `makemigrations` can't generate it itself.

**Test-database staleness across separate `pytest` invocations, not a Stage 5 regression, but
repeatedly hit while iterating on this stage and worth recording precisely so the next session
doesn't lose an hour to it too.** Running `pytest -q` (no `--create-db`) partway through this stage
produced `store.models.StoreSettings.DoesNotExist` failures in tests that have nothing to do with
search — reproduced even running `pytest store/` in complete isolation. Cause: Stage 4's
`inventory/tests/test_concurrency.py` uses `@pytest.mark.django_db(transaction=True)`, which commits
for real rather than rolling back; those commits persist in the physical `test_ecommerce` database
across separate `pytest` process invocations (each a new process, same on-disk test database) unless
`--create-db` rebuilds it fresh. Confirmed directly: `pytest store/ -q` failed, `pytest store/ -q
--create-db` passed cleanly. **Every quality-gate number recorded in this file's Stage 4 and Stage 5
entries was captured with `--create-db`** — CI always builds a genuinely fresh Postgres service
container per run, so this can't occur there, but a local session reusing the test database across
many separate `pytest` calls (as happens naturally over a long session) will eventually hit it
again. Not fixed — recorded as the correct way to get a trustworthy number, not a bug to patch.

- Sixth `[tool.ruff.lint.per-file-ignores]` `ANN401` pattern added: `"**/signals.py"` — a signal
  receiver's `**kwargs`, and the sender-instance argument on an `m2m_changed` receiver specifically
  (untyped since the same receiver fires for either side of the relation), must match Django's own
  dispatch signature, same reasoning as the existing CBV/form/command-override patterns. First (and,
  per CLAUDE.md, only sanctioned) use is `catalog/signals.py`. The section's own comment says a new
  pattern must be recorded here rather than just appended silently — this is that record.
- **No `storefront` app exists yet, and Stage 5's HTMX type-ahead endpoint needed a URL/view home
  now, not later — unlike Stage 4's `order` FK, this wasn't a hard Django blocker, so nothing was
  deferred.** `search/views.py` + `search/urls.py`, mounted directly at `/search/` in
  `config/urls.py` (same pattern as `/healthz/`), rather than waiting for Stage 6 to stand up
  `storefront/`. `templates/search/_search_input.html` (the `hx-trigger="keyup changed
  delay:200ms, search"` debounced box) exists but is **not rendered by anything yet** — no view,
  template, or test includes it, so its `{% url 'search:suggest' %}` tag has never actually been
  evaluated; a URL-name rename would break it silently right now. It isn't `{% include %}`'d into
  `templates/storefront/base.html`'s pre-existing `storefront_search` block yet — there is no
  storefront page to host it in until Stage 6 builds one. Verify this partial actually renders as
  part of whatever Stage 6 page first includes it; don't assume it from this stage.
- **Deploy step for any environment with pre-existing product data: `search_text` is not
  retroactively populated.** The column has existed since Stage 2 (`default=""`), and
  `catalog/signals.py`'s rebuild only fires on a save/delete *after* this stage's code is live — a
  product that already existed and hasn't been touched since stays invisible to search until
  `python manage.py rebuild_search_index` runs once. Ran it against the dev database as part of
  this stage: `Rebuilt search_text for 0 of 0 product(s)` — the dev database currently has no
  products at all (every manual verification fixture this stage was cleaned up after use), so
  nothing was actually stale locally. Relevant the moment real catalog data exists in any
  environment before this code does — a first deploy, or a staging database seeded ahead of this
  stage landing.
- `catalog/signals.py`'s `_on_product_tags_changed` receiver only handles `Product.tags`'s two real
  call directions (`product.tags.add(...)`, `reverse=False`, `instance` is the `Product`; and
  `tag.products.add(...)`, `reverse=True`, `instance` is the `Tag`, `pk_set` holds affected product
  ids) — both are tested directly, including the less-common reverse direction
  (`test_adding_a_tag_from_the_reverse_side_updates_search_text`).
- `search_text` is pre-lowercased at write time (`compute_search_text()`), deliberately, so neither
  GIN index expression nor any query needs its own `lower()`/`UPPER()` wrapping — the `icontains`
  bug above is exactly what happens when that discipline slips at one call site.
- `pg_trgm.word_similarity_threshold` is set to `0.6` via `core/migrations/0003` — the same value
  as Postgres's own compiled-in default, locked in explicitly per CLAUDE.md's trap note rather than
  left implicit. Not a guess: verified the `ALTER DATABASE ... SET` mechanism itself actually takes
  effect on new connections (not just coincidentally already matching the default) by round-tripping
  it to `0.45` and back on a live connection before trusting it; verified `0.6` is sufficient for the
  binding cases (`afnn`/`Afnan` typo, `EDP-9PM-100` as a genuine substring of a longer stored SKU)
  against real Postgres data before writing it into `core/config.py`.

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
- [Stage 4] Roadmap's Stage 4 deliverable line — `StockReservation (variant, order FK nullable
  until stage 8, quantity, expires_at indexed)` — describes a field Stage 4 cannot literally build:
  `orders.Order` doesn't exist until Stage 8 creates it, and Django cannot define a `ForeignKey` to
  a model in an uninstalled app (`manage.py check` would fail with E300, a real, checked error, not
  a style concern). Read as describing the field's eventual shape rather than a literal Stage 4
  instruction. Proposed change: `StockReservation` ships without `order` in Stage 4; Stage 8 adds it
  via `AddField` once `orders.Order` exists, starting nullable as the roadmap already says.
- [Stage 6] Roadmap's Stage 6 goal line says "§11–§18, mobile-first," but `REQUIREMENTS.md` has no
  headings numbered §11–15 or §18 — its actual sections in that range are "§16–17. Filtering and
  sorting" and, further down, "§34–38. Storefront quality requirements" (SEO, social sharing,
  performance, accessibility, mobile), plus §42 (DB indexes) and §44–46 (errors/empty/loading).
  Between them these cover every deliverable Stage 6's own list names, so nothing is actually
  missing — the roadmap's section numbers just don't match the requirements doc's own numbering
  scheme, the same class of drift as the `requirements.md`/`REQUIREMENTS.md` casing mismatch
  already recorded above. Not a blocker: built against the roadmap's explicit deliverable/gate list
  plus §16–17, §34–38, §42, §44–46's actual content. Proposed change: renumber the roadmap's Stage 6
  goal line to cite the sections that actually exist.

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
- [Stage 4] Stage 3's `ProductVariantForm` still edits `stock_quantity` directly (a roadmap-mandated
  field on that formset), bypassing `inventory.services.adjust()` and writing no
  `InventoryAdjustment` audit row. Full reasoning in this file's Stage 4 notes, above. Assumed in
  the meantime: acceptable, matching how this codebase already treats Django admin bypassing
  service-layer validation elsewhere (a documented gap, not a silent one). Revisit when audit
  completeness needs to be airtight (the future `audit.AuditLog` app, or Stage 17).

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

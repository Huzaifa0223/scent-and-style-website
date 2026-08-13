# State

Durable project memory. The agent reads this first in every session and updates it at the end of
every stage. It is the answer to "where are we and what is not obvious from the code".

Keep it factual and short. Append to the log; do not rewrite history. If this file and the code
disagree, the code is right and this file is stale — fix it.

---

## Current position

**Stage:** 11 — Public order tracking (not started)
**Status:** Stage 10 is complete — see the Stage 10 log entry below for the full acceptance-gate
and quality-gate record. Order status transitions, order editing (quantity/add/remove/price-
override), the status timeline, and the merchant-initiated WhatsApp status-update panel (wired to
Stage 9's `build_status_update_message()`) are all live in the portal, gated Owner-only pending
Stage 17's Staff permission extension. Two real bugs in `transition_status()`'s stock-restore
condition were caught and fixed before this stage was reported done — see its Notes. The
`WHATSAPP_MESSAGE_MAX_CHARS` real-device measurement and the confirmation page's visual no-JS check
(both Stage 9 human tasks) remain outstanding — see *Human tasks* below.
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
`rebuild_search_index` command, an HTMX type-ahead endpoint, now wired into every storefront page's
header), `storefront/` (home page with featured/new-arrivals/category tiles, category and listing
pages with composable filters + facet counts + sort + pagination, PDP with a variant selector,
lightbox gallery, and skeleton loaders), `cart/` (session-keyed `Cart`/`CartItem`, HTMX-driven badge
and drawer, add/increment/decrement/remove/clear with no page reload), `customers/` (`Customer`
matched on normalised phone), `payments/` (`PaymentProvider` protocol + state enum only, no
implementation), `shipping/` (`DeliveryZone`, the three `DeliveryCalculator` strategies), `orders/`
(`Order`/`OrderItem` with full snapshot fields, the `ORD-{seq}-{rand}` order-number sequence, the
`create_order()` transaction, single-page checkout, a session-scoped confirmation page),
`notifications/` (`NotificationChannel` protocol, `WhatsAppLinkChannel`, order-confirmation message
building with budget-aware truncation, six status-update templates on `StoreSettings`, now wired
into the portal order detail page's "Notify customer" panel), a project-wide design system
(`docs/design.md`, `tailwind.config.js` tokens, self-hosted IBM Plex). Stage 10 adds the order
status state machine (`orders/status.py`'s explicit transition map, `orders/state_machine.py`'s
`transition_status()` — the first real caller of Stage 4's `commit_reservation()`), order editing
(`orders/editing.py`: quantity/add-line/remove-line/price-override, each routed through new
`inventory.services` functions — `release_reserved()`, `consume()`, and three per-order bulk
wrappers — so `orders/` never touches `StockReservation` directly), `OrderStatusEvent`/
`OrderEditEvent` audit models, and the portal order list/detail UI.
Stages 1-10 are fully built; Stage 11 (public order tracking) is next and not started.

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

### Stage 6 — Storefront: browse, filter, sort
Completed: 2026-08-13
Commits: 2a3dc60 feat(storefront): add product listing, PDP, and home page
         64aeb41 feat(storefront): wire search, add new arrivals, lightbox, and skeleton loaders
Acceptance gates: all passed
  1. Filters compose (category + brand + price range + an attribute facet) with correct facet
     counts that reflect the *other* active filters — `storefront/tests/test_filtering.py` (389
     lines, one fixture per composition case). Verified live in a browser too: applying a filter,
     reloading via the URL alone, reproduced the identical filtered state (see gate 2).
  2. Filter state survives a reload and the back button — true by construction, not by a specific
     mechanism that could regress: every filter round-trips through the query string
     (`storefront/filtering.py`'s `ListingFilters`), there is no session state to lose. Confirmed
     live in a browser during the original pass (recorded in the commit this builds on).
  3. Selecting a variant on the PDP updates price, availability, and gallery hero without a reload —
     Alpine `x-data` driven off `variants_data`/`gallery_images` (`json_script`-embedded, not
     interpolated into an HTML attribute — see Notes, this was a real bug caught and fixed in the
     original pass). `storefront/tests/test_product_detail_view.py`.
  4. An out-of-stock variant cannot be added to the cart and the PDP names it specifically — the Add
     to Cart button's `:disabled` binds to `variant.available_quantity <= 0`, and the button's own
     label switches to "Out of Stock"; the availability line reads "Out of stock — this option is
     currently unavailable.", not a generic message.
     `test_pdp_exposes_every_variant_with_price_and_availability_for_the_selector`.
  5. `assertNumQueries` bounded and flat as fixture count grows, on **all three** storefront list/
     detail views — the listing page and the home page (`test_query_count_stays_flat_as_fixture_
     count_grows_from_5_to_50` in both `storefront/tests/test_product_list_view.py` and
     `storefront/tests/test_home_view.py`, 5→50 products, home page's featured+new-arrivals rails
     included). The PDP has no fixture-count axis to grow against (one product per request), so its
     query-count guard is a flat assertion instead. The home-page guard did not exist before this
     pass — see Notes, "What the prior session's undocumented commit actually left unbuilt".
  6. Every list and detail view has a defined empty state and a skeleton loader. Empty states:
     product listing ("No products match these filters", with a clear-filters link) and the home
     page's featured/new-arrivals sections ("No featured products yet" / "No products yet") existed
     from the original pass. Skeleton loaders did not exist anywhere in the codebase before this
     pass — added this pass to product cards (shared by listing, home-featured, and home-new-
     arrivals via `_product_card.html`) and the PDP gallery hero. Mechanism: each image sits in an
     `x-data="{ loaded: false }"` wrapper with a `bg-border-subtle animate-pulse` placeholder shown
     via `x-show="!loaded"` and the real `<img>` shown via `x-show="loaded"`, set by
     `x-init="loaded = $el.complete"` (handles the already-cached case, where the browser's `load`
     event would otherwise never fire after Alpine attaches its listener) and `@load="loaded = true"`
     otherwise. Custom, storefront-styled 404/500 pages (error states) already existed project-wide
     since Stage 1 — `templates/404.html`/`500.html`, "Back to the store" CTA, no Django debug
     traceback — re-verified applicable here, not rebuilt.
  7. Quality gate green — see numbers below.

Quality gate, final numbers (this pass): `ruff check` — all checks passed. `ruff format --check` —
all files formatted. `mypy .` (whole tree, unscoped) — no issues in 123 source files.
`makemigrations --check --dry-run` — no changes detected. `pytest --create-db` — 297 passed.
Coverage: `storefront` 100%, `search` 100% (both floor 80%/90%). `manage.py check --deploy` clean
under `config.settings.prod` (DEBUG=False, ALLOWED_HOSTS set, a real random `SECRET_KEY` via
`get_random_secret_key()`, placeholder R2 credentials). `manage.py check` clean under
`config.settings.dev`.
Coverage: storefront 100%, search 100% (floors 80%/90%)
Notes:

**Process failure this stage exists to document, not just the feature gaps it caused — this is
what `specs/state.md` exists to prevent, and it happened anyway.** A prior session committed
`2a3dc60 feat(storefront): add product listing, PDP, and home page` — the home page, category and
listing pages, the PDP with its variant selector, and `storefront/filtering.py` — directly onto
`main`, with a real, substantive commit message describing live-browser-verified gates 1-4. But it
never updated this file's **Current position** section (which still read "Stage 6 — not started,"
"No `storefront` app exists yet" for an entire session after the app had shipped) and never wrote
this stage-log entry. The only trace of Stage 6 having started at all was one `[Stage 6]` bullet
added to *Proposed spec amendments* (the roadmap's `§11-18` numbering mismatch) — everything else
about that commit's own scope was undocumented. This was caught at the start of this session by
reading `git log` against `specs/state.md` and finding they disagreed, not because state.md said
anything was wrong.

**What that drift concretely cost: two roadmap deliverables were effectively marked done (by
omission — nothing flagged them as missing) while genuinely unbuilt, and one Stage 5 loose end
was never picked up.**
- **Skeleton loaders** (named explicitly in gate 6, and in roadmap Stage 6's own deliverable list)
  did not exist anywhere in the codebase — confirmed by `grep -rn "skeleton" .` returning zero
  matches outside `roadmap.md` itself before this pass started.
- **The lightbox** (named explicitly in the PDP's deliverable list — "gallery ... lightbox") did not
  exist. The gallery's thumbnail row swapped the hero `<img>`'s `src` via a plain inline `onclick`;
  clicking the hero image itself did nothing. There was no enlarged/full-screen view at all.
- **Stage 5's search box was never wired into a page.** `templates/search/_search_input.html`'s own
  comment already said "Stage 6 includes this into `storefront/base.html`'s `storefront_search`
  block" — that block existed, empty, and stayed empty through all of `2a3dc60`. A customer visiting
  the live Stage-6 storefront had no way to search at all. `templates/search/_suggestions.html`'s
  own comment also already flagged that its rows had no `<a href>` to a PDP "until Stage 6 builds
  that page" — Stage 6 built the page and still never added the link.

None of this was a hard blocker anyone hit and deferred — the code that would have caught it
(`grep -rn "skeleton"`, opening `templates/storefront/base.html` and reading its own
`storefront_search` block) was never run against the finished work before it was declared done via
silence (an unstated "current position," not an explicit claim of completion). Fixed this pass; see
gate 6 above for the skeleton mechanism, and "Search wiring" below for the search fix.

**What this pass actually built, on top of `2a3dc60`:**
- **Search wiring.** `templates/storefront/base.html`'s `storefront_search` block now
  `{% include %}`s `search/_search_input.html` (rendered on every storefront page, header
  reflowed with `flex-wrap` so it doesn't break mobile layout). `search/_suggestions.html`'s rows
  are now `<a href="{% url 'storefront:product_detail' ... %}">`-wrapped. Both partials' own
  comments (quoted above) rewritten to stop describing themselves as not-yet-wired.
- **New Arrivals**, named separately from "Featured" in roadmap Stage 6's own deliverable list and
  genuinely absent (`HomeView` only ever queried `is_featured=True`). Added as its own `HomeView`
  context key (`new_arrivals`, latest 8 published products by `-created_at`, deliberately not
  deduplicated against `featured_products` — "featured" and "newest" are independent curations, a
  product can legitimately be both) and its own home-page section with its own empty state.
- **Lightbox**, hand-rolled in Alpine rather than vendoring Alpine's official Focus plugin (would
  have meant a new frontend dependency for one modal, and CLAUDE.md's intervention rule 3 flags
  "a dependency outside the approved list" as a stop-and-ask case — the vanilla-JS trap below is
  ~15 lines and avoids that question entirely). Opens on clicking the hero image, closes on
  Escape/click-outside/close button, Previous/Next cycle through every image. **Ships with a real
  keyboard focus trap and focus restoration — added only after the human flagged mid-pass that the
  first version didn't have one and §37 requires keyboard navigability.** Mechanism: `openLightbox()`
  records `document.activeElement` before opening and moves focus to the close button;
  `closeLightbox()` restores it; a `@keydown.tab` handler on the dialog wraps focus between the
  dialog's first and last focusable `<button>` (computed live via `querySelectorAll`, so it
  automatically excludes Previous/Next when there's only one image, since `x-show` removes them from
  the tab order rather than just hiding them visually).
- **Skeleton loaders** — mechanism described under gate 6 above. Applied to `_product_card.html`
  (one partial, so listing/home-featured/home-new-arrivals all inherit it for free — CLAUDE.md's "one
  partial per reusable unit") and the PDP hero image.
- **`assertNumQueries` on the home page** — didn't exist before this pass (the human flagged this
  too: "two rails, two prefetches... currently has no query-count guard"). Same 5→50 technique as
  the listing page's own gate-5 test. Flat, confirmed.

**Everything above was verified live in a real browser, not just asserted by a passing test suite
— the human's explicit instruction after the first pass's skeleton/lightbox tests turned out to
assert source strings (`b"animate-pulse" in response.content`, `b'x-init="..." ' in response.content`)
that would pass whether the feature actually worked or not.** What was actually checked, and how:
- **Skeleton toggling against Alpine's real `loaded` state**, not just the presence of the CSS
  class: read `Alpine.$data(el)` directly via the browser's own JS console (through the automation
  tool's `javascript_exec`), forced `loaded` false then true on both the PDP hero and a product
  card, and asserted `getComputedStyle(...).display` on the skeleton div and the `<img>` flipped
  correctly each time — confirmed on a fresh page load for both. **One real false alarm during this
  check, worth recording so nobody re-investigates it:** the very first attempt on the product-card
  skeleton showed the image staying hidden after `loaded` was set `true`; re-run immediately after
  with a fresh page navigation (rather than reusing state from a script that had run moments after
  a `navigate` call, before Alpine had necessarily finished attaching) came back clean, and every
  subsequent repeat was clean. Treated as a test-script timing artifact, not a product defect — no
  code changed as a result, and the mechanism itself (`x-show` bound directly to a plain reactive
  boolean) has no code path that could reproduce a stuck skeleton.
- **The lightbox's focus trap, in both directions, with real keyboard events**, not synthetic
  clicks: opened the lightbox (focus landed on Close, confirmed via `document.activeElement`),
  pressed Shift+Tab from Close and confirmed focus wrapped to Next (the last focusable), pressed Tab
  from Next and confirmed it wrapped back to Close, then Tab again and confirmed it advanced
  normally to Previous. Pressed Escape and confirmed both `lightboxOpen` went false *and*
  `document.activeElement` returned to the hero button that opened it (focus restoration, not just
  visual close). Separately confirmed click-outside (`@click.self`) also closes and restores focus
  the same way. Previous/Next were confirmed to cycle correctly including wrap-around
  (0 → next → 1 → prev → 0 → prev → 2, the last index).
- **The search suggestion linking to the PDP**: typed a product name into the header search box on
  a real page, watched the HTMX-swapped dropdown render the matching product, clicked it, and
  confirmed the browser navigated to `/product/<slug>/`.
- Coordinate-based and element-ref-based clicks through the browser automation tool's own
  `computer`/`find` tools did not reliably register against the gallery's Alpine `@click` handlers
  during this session (state didn't change after the click); dispatching the same click via
  `element.click()` through the automation tool's JS-execution capability worked every time and is
  indistinguishable from a real click as far as Alpine's event listener is concerned. Real keyboard
  input (Tab/Shift+Tab/Escape) through the automation tool worked correctly throughout — the
  keyboard-driven focus-trap verification above did not need this workaround. Recorded in case a
  future session hits the same tooling quirk and wonders whether it's the app or the tool.
- Given the source-string tests turned out to be weak evidence on their own, they were trimmed to
  one minimal smoke assertion each (`b"animate-pulse"`, `b'role="dialog"'`) with a docstring pointing
  here for the real evidence, rather than deleted outright — they still catch "the markup vanished
  entirely," which a live check run once in one session does not keep catching on every future
  change.
- Home page hero is a plain text banner (store name + "Shop All Products" CTA), not an image-based
  marketing hero — roadmap's own `§13` citation for the home page doesn't exist in
  `REQUIREMENTS.md` (same numbering-mismatch class already recorded under *Proposed spec
  amendments*, Stage 1's `requirements.md`/`REQUIREMENTS.md` casing entry), so there is no spec text
  describing what a hero should contain. Left minimal rather than invented; Stage 12 (SEO and
  performance pass) is the more natural place to add real marketing imagery once the merchant has
  any to provide.
- The dev database (not the test database) was found holding leftover fixture data from earlier
  stages' live-verification passes that had never been cleaned up — 5 generic products
  ("Product 0"-"Product 4"), roughly 90 orphaned "Category N" rows, and `StoreSettings.name`
  overwritten to "Updated Name" (default `"My Store"`). Only the 3 `ProductImage` rows this
  session's own verification created were removed — the human's explicit instruction was to leave
  everything not created this session alone, since it might be data the human is using rather than
  debris. Not cleaned up; flagged here for whoever eventually does.

### Stage 7 — Cart
Completed: 2026-08-13
Commits: 95870d1 feat(cart): add Cart/CartItem, session-keyed cart with HTMX badge and drawer
Acceptance gates: all passed
  1. Adding beyond `available_quantity` is refused with the actual available number in the message
     — `cart/tests/test_services.py::test_add_item_refuses_beyond_available_quantity_with_the_real_number`
     and the same at the HTTP layer in `cart/tests/test_views.py`, plus the increment endpoint
     specifically (`test_increment_beyond_available_quantity_is_refused_with_the_real_number`).
     Verified live: incrementing a 3-in-stock line to a 4th unit left the quantity at 3 and rendered
     "Only 3 left in stock." both in the drawer and, via the PDP's `#pdp-add-error` OOB slot, next to
     the Add to Cart button.
  2. A cart item whose variant goes out of stock between add and view is flagged, not silently
     dropped — `test_cart_lines_flags_a_variant_that_went_out_of_stock_after_adding` and
     `test_a_cart_item_that_goes_out_of_stock_after_add_is_flagged_not_dropped`. The stored
     `CartItem.quantity` is never auto-reduced; only the *rendered* purchasable portion and the
     subtotal reflect the shortfall, so the customer's original request stays visible.
  3. A variant deactivated after being added is handled without a 500 — covered at both the service
     and view layer, and taken one step further than the roadmap's own wording: **a variant
     *deleted* after being added is handled the same way**, since `CartItem.variant` is
     `on_delete=SET_NULL`, not `CASCADE` (the human's explicit instruction for this stage). Both
     cases collapse into the same `purchasable_quantity = 0` / "no longer available" handling in
     `cart.services.cart_lines()` — one condition with two causes, not two special cases. Verified
     live in a browser for both: deactivating the sole variant in a cart (via direct DB edit, no
     portal UI change involved) and then triggering any mutation re-rendered the line as flagged,
     no 500, quantity preserved, subtotal recalculated to exclude it; deleting a variant after
     giving its product a second one (a product must always have ≥1 variant — unrelated invariant,
     had to route around it in both the live check and the automated tests) produced the same
     flagged rendering with "Item unavailable" in place of the product name. The PDP's own
     `Add to Cart` button does not currently grey out for a deactivated (not out-of-stock) variant —
     the server still correctly refuses it ("That item is no longer available.", confirmed live) —
     recorded as an open question below since fixing the PDP display is a Stage 6 concern this
     stage didn't set out to reopen.
  4. No page reload on any cart mutation — every endpoint returns a fragment (200), never a
     redirect; `test_increment_decrement_remove_clear_never_500_and_never_redirect` asserts
     `response.get("Location") is None` on all four. Verified live: the cart drawer's `x-data="{
     cartOpen }"` lives on a wrapper that's never itself swapped (only
     `#cart-drawer-content` inside it is, via `hx-target`), so incrementing a line with the drawer
     open left it open afterward — screenshotted before and after to confirm, not just asserted from
     reading the markup.
  5. Quality gate green. Coverage floor 85% on `cart` — see numbers below.

Quality gate, final numbers: `ruff check` — all checks passed. `ruff format --check` — all files
formatted (143 files). `mypy .` (whole tree, unscoped) — no issues in 135 source files.
`makemigrations --check --dry-run` — no changes detected. `pytest --create-db` — 340 passed.
Coverage: `cart` 100% (`models.py`/`services.py`/`views.py`/`context_processors.py` all 100%; floor
85%). `manage.py check --deploy` clean under `config.settings.prod` (DEBUG=False, ALLOWED_HOSTS set,
a real random `SECRET_KEY`, placeholder R2 credentials). `manage.py check` clean under
`config.settings.dev`.
Coverage: cart 100% (floor 85%)
Notes:

**Design directive from the human, given before any code was written, both points followed
literally rather than reinterpreted:** (1) `CartItem` FKs to `ProductVariant`, never `Product`, and
every availability check goes through `ProductVariant.objects.with_available_quantity()` (Stage 4's
annotation) rather than reading `stock_quantity` directly — `cart.services` never touches
`stock_quantity` at all, only ever reads the annotated `available_quantity`. (2) Gate 3 covers both
deactivation *and* deletion, with `on_delete=SET_NULL` (nullable) rather than `CASCADE` — see gate 3
above for how both collapse into one code path.

**Adding to a cart never creates a `StockReservation`, deliberately, per CLAUDE.md's locked
decision that stock is reserved at *order* creation.** `cart.services`'s docstring states this
explicitly since it's the kind of thing a future session could "fix" by wiring `inventory.services.
reserve()` into `add_item()`, which would be wrong — that would reserve stock the moment something
enters a cart, long before a customer commits to buying it, defeating the whole reason CLAUDE.md's
table separates "reserved at order creation" from "decremented at confirmation." Every availability
check here is advisory (a plain `with_available_quantity()` read, no row lock), re-validated
authoritatively under `select_for_update()` at Stage 8's checkout — this layer's job is keeping the
cart's *displayed* state honest between now and then, not guaranteeing a unit survives to checkout.

**Cart rows are created lazily.** `services.get_cart()` (read-only, used by the globally-registered
context processor on every page render) never touches the session or the database if no session
key exists yet; `services.get_or_create_cart()` (mutation views only) is the only path that creates
a session and a `Cart` row, so browsing the storefront doesn't write a row per anonymous visitor who
never adds anything. This split is covered directly
(`test_get_cart_returns_none_without_creating_anything`,
`test_get_or_create_cart_creates_a_session_and_a_cart_row_once`).
- **A real bug this design caught before it shipped, not after:** two pre-existing tests
  (`core/tests/test_templates.py`, `store/tests/test_context_processors.py`) render a template
  directly through a bare `RequestFactory` request that never passed through `SessionMiddleware` —
  a legitimate, narrow pattern for unit-testing template rendering in isolation. The newly-global
  `cart` context processor runs on *every* template render, including theirs, and `get_cart()`'s
  first version assumed `request.session` always exists (true for every real request —
  `SessionMiddleware` is unconditional in `MIDDLEWARE` — but not for a request built by hand).
  Caught by running the full suite, not just `cart/`'s own tests, before considering this stage
  done. Fixed with `getattr(request, "session", None)` rather than assuming the attribute exists.

**`cart_lines()` is two queries total regardless of item count** — the cart's own items, then every
referenced variant's availability in one `with_available_quantity()` query, joined in Python via a
dict keyed by variant id. Verified two ways, both directly asserting query counts rather than
inferring flatness from reading the code: `cart/tests/test_services.py::
test_cart_lines_query_count_stays_flat_as_item_count_grows_from_1_to_5` (1→5 items, service layer)
and `cart/tests/test_views.py::test_query_count_stays_flat_as_item_count_grows_from_2_to_20`
(2→20 items, through a full page render, since `cart_lines()` now runs on every storefront page via
the context processor — a regression here costs the whole site, not just the drawer, which is why
this gets the same flat-growth treatment as the storefront listing page's own gate 5 test even
though Stage 7's own gate list doesn't name `assertNumQueries` explicitly).

**HTMX POST is new to this project — search's endpoint (Stage 5) is GET-only, portal's mutations
(Stage 3) are plain `<form method="post">` submits, so no CSRF-for-HTMX precedent existed yet.**
Added a global `htmx:configRequest` listener in `templates/base.html` (root shell, shared by both
`storefront/base.html` and `portal/base.html`) that reads the `csrftoken` cookie and sets
`X-CSRFToken` on every HTMX request, rather than requiring each new HTMX-triggering element to carry
its own `{% csrf_token %}`. **This is a global change to a template `portal` also extends, made
while building a storefront-only feature — flagged explicitly since portal currently has zero HTMX
POST usage of its own and would otherwise have no reason to reveal this in its own test suite.**
Confirmed harmless there today (nothing in `portal` triggers an `htmx:configRequest` event, since
none of its POSTs go through HTMX), and correct for the day something in `portal` does. Verified
directly, not just reasoned about: `cart/tests/test_views.py::test_csrf_is_enforced_on_the_add_endpoint`
uses `Client(enforce_csrf_checks=True)` (the Django test client's default silently *disables* CSRF
enforcement, which would have hidden a broken listener) and asserts a request with no token still
gets a `403` — proving CSRF protection is genuinely still active on this endpoint, not bypassed by
the fix. Live-browser verification (a real request going through the JS listener) is the same
add/increment/etc. flow already covered above, all of which required a valid CSRF header to succeed
at all.
- `test_add_with_a_non_numeric_variant_id_is_refused_without_a_500` originally asserted the escaped
  *or* unescaped form of "Couldn't add that item." — passed regardless of which actually rendered,
  proving nothing about the real output (the human caught this directly). `{{ error }}` is
  auto-escaped (no `|safe`), so the apostrophe always renders as `&#x27;`; fixed to assert only that
  form, confirmed against the real response before trusting it.
- Deployment note for whoever runs this stage's migration for the first time on a non-fresh
  database: this session's own dev database needed an explicit `manage.py migrate` before the cart
  widget would render at all (`ProgrammingError: relation "cart_cart" does not exist`) — caught only
  because live verification actually loaded a page, not from `makemigrations --check` or the test
  suite, both of which operate against their own always-fresh databases and would never have
  surfaced this. Not a defect in this stage's migration itself, just a reminder that `--check` proves
  the migration *file* is correct, never that it's been *applied* anywhere real.

### Stage 8 — Checkout and order creation
Completed: 2026-08-13
Commits: 9640d3f fix(catalog): guard product_must_have_variant trigger against same-transaction delete
         343fb38 feat(orders): add checkout and order creation — Stage 8
Acceptance gates: all passed
  1. **Snapshot test:** create an order, then change the product's price and name, then delete the
     product — the order still displays the original name, SKU, and unit price.
     `orders/tests/test_services.py::test_gate1_snapshot_survives_a_price_change_a_rename_and_a_product_deletion`.
     Verified live in a browser too, not just asserted: placed a real order, renamed and repriced
     the product via the shell, then `product.delete()`'d it, reloaded the confirmation page — it
     still showed the original name and Rs. 750.00, no 500, `item.variant_id` correctly `None`.
  2. Every displayed order value comes from the snapshot — `tests/test_order_snapshot_leakage.py`
     greps every template under `templates/orders/` (except `checkout.html`, which legitimately
     renders live *cart* data pre-purchase, not an `OrderItem` snapshot — documented in the test's
     own docstring so a future reader doesn't "fix" the exclusion away) for `.variant.price` and
     `.variant.product.name`. Verified to have teeth, not just pass by construction: temporarily
     injected `{{ item.variant.price }}` into `order_confirmation.html`, confirmed the test failed
     with the exact offending line named, then removed it and confirmed green again.
  3. A failure mid-creation rolls back completely: no orphan order, no orphan reservation —
     `test_gate3_a_failure_mid_creation_rolls_back_completely` (one insufficient-stock line among
     two rolls back both, including the line that would have succeeded alone; the cart itself
     survives the rollback too, still holding both items).
  4. Availability changing between cart view and submit produces a per-line error naming the
     product — `test_gate4_availability_changed_since_add_produces_a_per_line_error_naming_the_product`
     (service layer) and `test_checkout_post_with_a_stock_shortfall_shows_the_per_line_error_and_creates_nothing`
     (HTTP layer, asserting the actual rendered page).
  5. Order numbers are unique under a concurrent-creation test —
     `test_gate5_concurrent_order_creation_for_the_last_unit_exactly_one_succeeds`: two real threads,
     two different carts, one shared last-unit variant, `transaction=True`, real separate
     connections — same methodology as Stage 4's `reserve()` concurrency test, applied here through
     the *whole* `create_order()` transaction rather than just `reserve()` in isolation. Exactly one
     order created, exactly one reservation, and the two order numbers (had both somehow succeeded)
     are asserted distinct as a second, independent check.
  6. Each of the three delivery strategies calculates correctly, including the free-delivery
     threshold combined with city rates — `shipping/tests/test_calculators.py`, one test per
     strategy plus the combined-with-a-city-rate case
     (`test_city_based_calculator_waives_the_zone_rate_above_its_own_threshold`) and the
     factory (`get_delivery_calculator()`) building the right concrete strategy from
     `StoreSettings` for all three, including the "threshold strategy selected but no threshold
     configured" misconfiguration case (falls back to flat-rate charging, not silently free).
  7. Quality gate green. Coverage floor 90% on `orders` — see numbers below.

Quality gate, final numbers: `ruff check` — all checks passed. `ruff format --check` — all files
formatted (179 files). `mypy .` (whole tree, unscoped) — no issues in 171 source files.
`makemigrations --check --dry-run` — no changes detected. `pytest --create-db` — 395 passed.
Coverage: `orders` 99% (`forms.py`/`services.py`/`urls.py`/`views.py` all 100%, `models.py` 97% —
only the two `__str__` methods, same accepted precedent as Stage 4's `inventory` models; floor
90%), `customers` 97%, `shipping` 99%, `payments` (no floor — `protocols.py`'s `Protocol` body is
by definition unexecuted, same reasoning as "UI-only code exempt"), `catalog` 97% (floor 85%,
unaffected by the trigger fix). `manage.py check --deploy` clean under `config.settings.prod`
(DEBUG=False, ALLOWED_HOSTS set, a real random `SECRET_KEY`, placeholder R2 credentials).
`manage.py check` clean under `config.settings.dev`.
Coverage: orders 99% (floor 90%), customers 97%, shipping 99% (no roadmap-stated floor; used 80%
in CI), payments not floor-checked
Notes:

**Design was printed and reviewed by an independent advisor before any code was written, per the
human's explicit instruction — two review passes, both substantive, the first only after a failed
retry.** The first advisor call failed mid-run on an API connection error before producing any
findings (the human chose to retry rather than proceed without it). Before the retry, the human's
own review of the printed design caught four real issues, all folded into the design the advisor
then reviewed a second time:
1. The original design proposed combining `select_for_update()` with
   `with_available_quantity()`'s `Subquery`-based annotation in one query to lock variants and read
   availability together. This either errors or locks only the outer `ProductVariant` rows while
   leaving the `StockReservation` rows the subquery aggregates over completely unlocked — silently
   checking less than it looks like it checks. Split into two queries: a plain
   `select_for_update()` lock, then a separate unlocked `with_available_quantity()` read while the
   lock is held.
2. That locking query needed `.order_by("pk")` — locking several variant rows with no deterministic
   order deadlocks when two carts share the same variants in different orders.
3. The original design claimed `reserve()`'s own re-check (inside the per-line reservation-creation
   loop) was "redundant" given the upfront pre-check. Dropped that claim: it's only redundant if the
   pre-check's lock actually covers what it needs to, which point 1 put in doubt for the *original*
   design. Even after the fix, the safer and more accurate framing (used in the final code and
   comments) is that `reserve()`'s own lock+check is the actual, sole, provably-race-safe mechanism
   (Stage 4's own proven guarantee), and the pre-check exists only to produce a good multi-line error
   message before committing to anything — not to be the safety net itself.
4. The original design claimed locking the `Cart` row at the top of the transaction prevented a
   double-submit (two rapid clicks creating two orders). It doesn't, fully: two requests from one
   session can still resolve to two different `Cart` rows, or race `Cart` creation itself. The lock
   is kept (still a partial, real guard for the common case), but double-submit is recorded below as
   an open question, not claimed solved.

**The second advisor pass (after the corrected design, this time completing successfully) caught
one more real issue the human's own review and the first four corrections had missed:** the
corrected design still didn't say explicitly which read `subtotal` should use. `cart.services.
cart_lines()` (step 1, unlocked, taken before the transaction's own lock) and the locked
`with_available_quantity()` read (step 3/4) are two independent reads of the same variant's price;
using the first for `subtotal` and the second for each `OrderItem.unit_price` would let a
mid-checkout reprice produce an `Order` whose `subtotal` doesn't equal the sum of its own
`OrderItem.line_total`s — silently, and exactly the "two call sites answering the same question
from two different reads" class of bug this project's reviews have caught before (Stage 4's
`available_quantity` fan-out, Stage 4's Python-clock-vs-DB-clock inconsistency). Fixed:
`create_order()` never touches `cart_lines()`'s own price read at all — it reads `cart.items.all()`
directly for quantities/variant-ids only, and every price (`subtotal` and every
`OrderItem.unit_price`) comes from `variant_by_item_pk`, populated once during the same validation
pass that already locked and read availability.

The second pass also caught two smaller, real bugs: the order-number alphabet
(`23456789ABCDEFGHJKMNPQRSTUVWXYZ`) still contained `L` despite §22's explicit "no 0/O, no 1/I/l" —
fixed (31 characters, `31³ = 29,791` combinations, the number already cited when explaining why
rate-limiting rather than the alphabet is the real security control); and `DeliveryZone.city` was
`unique=True` on the raw string while `CityBasedCalculator` matches `city__iexact` — Django admin
(the only CRUD surface this stage) could have created both `"Lahore"` and `"lahore"` as separate,
individually-valid rows, making the case-insensitive lookup non-deterministic between them — fixed
with a `UniqueConstraint(Upper("city"), ...)`.

**A real, unrelated bug in Stage 2's own trigger code was found and fixed mid-stage, not
worked around in the test that found it.** Gate 1's snapshot test is the first test in this
codebase to create a product and then fully delete it (product row and its variant both) within
one transaction — every prior stage's tests that delete a product do so against a fixture that was
created and committed in an earlier, separate transaction. `catalog_product_must_have_variant()`
(migration 0002, the `AFTER INSERT ON catalog_product` deferred trigger) queued its "does this
product have a variant" check from the original `INSERT`, with no guard for the product itself
having also been deleted by the time the deferred check actually fires (at commit, or at
`pytest-django`'s teardown `SET CONSTRAINTS ALL IMMEDIATE`) — so a product created and fully deleted
in the same transaction incorrectly raised "must have at least one variant" for a product that no
longer existed at all. `catalog_variant_delete_leaves_product_with_variant` (the `AFTER DELETE`
sibling trigger, same migration) already guarded against exactly this shape of problem (`IF EXISTS
(SELECT 1 FROM catalog_product WHERE id = OLD.product_id) AND ...`); migration 0008 brings the
`INSERT`-side trigger in line with it. Confirmed both the failure and the fix directly (a standalone
script reproducing the bug against a real Postgres connection, not just trusting the pytest
traceback), and added a permanent regression test
(`catalog/tests/test_product.py::test_deleting_a_freshly_created_product_in_the_same_transaction_is_allowed`,
`transaction=True` — the same deferred-constraint trap CLAUDE.md's Traps section already documents
three instances of; a fourth, this one on the INSERT side rather than a partial-unique-index
conversion). Unlikely to matter in real production usage (creating and fully deleting the same
product in one request is rare), but it's a real gap in an invariant this project otherwise treats
as load-bearing everywhere, so it's fixed rather than left as a test-only workaround.

**`inventory.services.reserve()` now requires `order: Order` as a keyword argument (breaking
change, decided after the human weighed required-vs-optional explicitly).** Every real caller after
this stage has an order — cart never calls `reserve()` (Stage 7's own design), so `create_order()`
is `reserve()`'s first real production caller — and a reservation with no order is meaningless
after this stage ships. The ~14 existing call sites in `inventory/tests/test_services.py` and
`test_concurrency.py` (Stage 4) were updated to pass `order=OrderFactory()` (a new
`orders/factories.py`, itself a new test-only dependency from `inventory`'s tests onto `orders` —
consistent with the schema-level dependency `StockReservation.order` already creates). The two
concurrency tests needed their `Order`s created **before** spawning worker threads (main-thread
`orders = {"t0": OrderFactory(), "t1": OrderFactory()}`, committed under `transaction=True` same as
`variant`), not inside each thread's own `attempt()` — creating them per-thread would have raced
factory-boy's sequence counters across threads on top of the reservation race the test already
exists to exercise, muddying what's actually being tested.

**`ProductVariant.display_label`** — `storefront/views.py`'s private `_variant_label()` (Stage 6)
moved to a plain property on the model, since `OrderItem.variant_label`'s snapshot needs the exact
same "Red / 50ml" logic and two independent copies of it is exactly the kind of drift this project
avoids elsewhere (`display_price`, `available_quantity`, ...). N+1-safe only when
`variant_attribute_values__value` is prefetched — true both at the PDP (already prefetched, Stage
6) and in `create_order()`'s own locked variant query (prefetch added there specifically because
the advisor's second pass caught its absence — see below).

**A second, independent finding from the advisor's second pass, folded in during implementation:
the locked variant query in `create_order()` needed `.prefetch_related("variant_attribute_values__
value")` for `display_label` to actually be N+1-safe there** — `with_available_quantity().select_related("product")`
alone doesn't cover it, and Stage 8's own acceptance gates don't include an explicit
`assertNumQueries` check for checkout the way Stages 3/6/7 do for their own list views, so nothing
would have caught this by accident. Added, and a query-count test
(`test_query_count_stays_flat_as_line_count_grows_from_1_to_5`) added anyway, even though it's not
a named gate — measured the real per-line cost directly via `CaptureQueriesContext` (5 queries/line:
one `OrderItem` insert plus `reserve()`'s own fixed four) rather than guessing a budget, so the
assertion has real headroom above genuine cost instead of being either too tight (flaking on
`reserve()`'s own legitimate cost) or too loose (missing a real regression).

**Customer race handling — a design point the advisor's second pass corrected after checking
Django 5.2's actual source, not just its documented behaviour.** `Customer.phone` is `unique=True`,
so two concurrent first orders from the same brand-new phone number race. The human's original
instruction was "use `update_or_create` and handle `IntegrityError`"; the advisor verified directly
against the installed `django.db.models.query` source that Django 5.2's `update_or_create()`
already takes `select_for_update()` on both its initial lookup *and* its post-`IntegrityError`
retry — meaning the loser of the race blocks on the winner's lock and returns the winner's row, and
never re-raises past `get_or_create_customer()` for the scenario being guarded against. The explicit
`except IntegrityError: Customer.objects.get(phone=phone)` fallback was **dropped**, not kept as
defensive belt-and-suspenders — it was unreachable under every scenario this codebase can actually
produce (nothing ever deletes a `Customer` mid-race), and unreachable code is a real coverage-floor
problem at this project's 90% floor on `orders`/`customers`, not just clutter. Recorded in the
function's own docstring so a future session doesn't "fix" the missing except block back in.

**Stage 8's own scope boundary against Stage 9, checked against the roadmap before writing any
checkout view code, not assumed.** Stage 9 ("WhatsApp handoff") owns the *entire* WhatsApp
message/redirect experience, including — per the roadmap's own Stage 9 deliverables line — "the
confirmation page always showing the order number, a copy-order-details button, and a
re-open-WhatsApp link". Stage 8 builds a genuinely minimal confirmation page (order number, line
items, totals, delivery address) that Stage 9 will extend with the WhatsApp-specific chrome, not
because the roadmap explicitly assigns Stage 8 a confirmation page at all, but because checkout
structurally needs *somewhere* to redirect to once an order exists, and building nothing would leave
checkout non-functional. `OrderConfirmationView` deliberately does not attempt any WhatsApp-related
behaviour.

**Checkout's `city` field is a required free-text `CharField`, not the `<select>` §20 literally
describes ("city — drives delivery charge")** — deviation, decided during design and confirmed by
the advisor, not silently made. Sourcing the select's options from `DeliveryZone` would make
checkout unsubmittable for any flat-rate/free-threshold merchant with zero configured zones (no
portal CRUD exists yet to populate them either — see the open question below). Recorded here and
under Deviations.

**`OrderConfirmationView`'s session-scoping is a deliberate security boundary, not an
afterthought.** `order_number` alone is only ~30,000 combinations wide (§22's own stated ceiling)
and Stage 11's actual rate-limited public tracking page doesn't exist yet — so the confirmation view
is scoped to `request.session["last_order_id"]`, set only by a successful `create_order()` call
immediately before redirect, and 404s for any `order_number` in the URL that isn't the exact order
this session just placed (tested directly:
`test_confirmation_404s_for_the_wrong_order_number_even_with_a_valid_session`). Verified live too:
navigating to a fabricated order number in the same browser session that had just placed a real
order still 404'd.

- The dev database needed an explicit `manage.py migrate` again before live verification could run
  (`customers`/`payments`(no migration)/`shipping`/`orders` migrations, plus `inventory`'s
  `AddField` and `catalog`'s trigger fix) — same reminder as Stage 7's entry: `makemigrations
  --check` proves the migration file is correct, never that it's been applied anywhere real. Applied
  before this session's live checkout run.
- CI gap fixed while adding this stage's own coverage-floor lines: `cart`'s Stage 7 floor (85%) was
  never actually added to `.github/workflows/ci.yml`, meaning CI was never actually enforcing it —
  confirmed the floor genuinely passes (100%) before adding the line, not just adding the line and
  hoping.
- Live-verified end to end in a browser: added an item to cart, opened checkout, confirmed the
  "same as mobile" checkbox correctly hides/shows the WhatsApp field (Alpine, `x-model`/`x-show`),
  submitted with a real Pakistani mobile number, landed on the confirmation page with a genuinely
  generated `ORD-10000-MSC` number, correct subtotal/delivery/total math against the configured
  flat-rate strategy, and cart badge reset to 0. Then (gate 1 above) renamed, repriced, and deleted
  the underlying product via the shell and reloaded the confirmation page to confirm the snapshot
  held. All fixture rows (order, customer, cart, category — the product/variant were already gone
  from the gate-1 check) removed by explicit primary key afterward, nothing left in the dev database.

### Stage 9 — WhatsApp handoff
Completed: 2026-08-13
Commits: 384842e feat(notifications): add WhatsApp handoff — Stage 9
         4ac3c7a docs: complete Stage 9 log entry in state.md
Acceptance gates: all passed
  1. A 30-item order produces a message within the budget, with the truncation notice and a
     working tracking URL —
     `notifications/tests/test_message_builder.py::test_gate1_a_30_item_order_truncates_within_budget_with_notice_and_tracking_url`
     (30 real `OrderItem` rows, `whatsapp_message_max_chars=500`, asserts `len(message) <= 500`,
     the "…and N more items" notice present, the tracking URL present, and that the
     totals/delivery/tracking tail always survives truncation regardless of how many items got
     cut). A second test proves the *inverse* — a generous budget truncates nothing, all 30 items
     present. **`WHATSAPP_MESSAGE_MAX_CHARS` (`StoreSettings.whatsapp_message_max_chars`,
     default 1000) is an unverified, deliberately conservative placeholder, explicitly not
     recorded as a measured limit anywhere** — the human's own instruction for this stage was
     specific: don't guess at a number and call it verified. See `docs/whatsapp-limits.md`
     (created this stage, currently all blanks) and the *Human tasks* entry below.
  2. The order exists and is visible in the portal whether or not the customer ever sends the
     message — structurally true since Stage 8 (`create_order()` commits before any WhatsApp
     string is even built) and re-asserted directly this stage:
     `test_gate2_the_order_exists_before_and_independent_of_any_whatsapp_interaction` proves the
     order is queryable immediately after checkout's POST returns, before
     `OrderConfirmationView` — the only place that calls `message_builder` — has been requested at
     all. No portal order list/detail exists yet to literally check "visible in the portal"
     through (Stage 10's job); this is the structural guarantee that gate actually rests on.
  3. No module outside `notifications/` constructs a WhatsApp string —
     `tests/test_whatsapp_string_construction.py`, a repo-wide grep for the forbidden domain
     substring across every `.py`/`.html` file outside `notifications/`. Verified to have teeth,
     not just pass by construction: injected the substring into `orders/urls.py`, confirmed the
     test failed naming that exact file, removed it, confirmed green again. Two real false
     positives surfaced and fixed *before* trusting the test — see Notes.
  4. **The confirmation page renders fully with JavaScript disabled — the redirect is an
     enhancement, not the mechanism.** The order number, the full message text, and (when a
     merchant WhatsApp number is configured) the `wa.me` link are all in the server-rendered HTML
     itself: `test_confirmation_page_always_has_the_order_details_message_in_the_rendered_html`
     asserts on the response body from the Django test client, which never executes JavaScript at
     all — this is already a genuine no-JS proof for content presence, not a stand-in for one.
     Confirmed live too, via `fetch()` against the running dev server from a same-origin tab
     (retrieves raw HTML without executing any of the page's own `<script>` tags, so this is
     exactly the no-JS case): order number, `id="whatsapp-link"` with the correct `href`,
     `id="whatsapp-message-text"` containing the full message, and the copy button were all
     present in the response body before any script ran. **What this session could *not* do:
     visually confirm the rendered page in a real browser with JavaScript actually toggled off** —
     the Chrome extension this session's browser automation runs through can only reach page
     content, not `chrome://` settings or DevTools, which is a genuine capability limit, not
     something worth spending more time routing around (confirmed by trying three approaches — a
     direct `chrome://settings/content/javascript` navigation, F12, and Ctrl+Shift+I — before the
     human explicitly said to stop). Recorded as a human task below, not silently marked done.
  5. Quality gate green — see numbers below.

Quality gate, final numbers: `ruff check` — all checks passed. `ruff format --check` — all files
formatted (190 files). `mypy .` (whole tree, unscoped) — no issues in 181 source files.
`makemigrations --check --dry-run` — no changes detected. `pytest --create-db` — 416 passed.
Coverage: `notifications` 96% (`message_builder.py`/`channel.py` both 100%; `protocols.py` 0% —
the `Protocol` body is by definition unexecuted, same accepted precedent as `payments/protocols.py`;
floor 90%), `orders` 99%, `store` 100%. `manage.py check --deploy` clean under
`config.settings.prod` (DEBUG=False, ALLOWED_HOSTS set, a real random `SECRET_KEY`, placeholder R2
credentials). `manage.py check` clean under `config.settings.dev`. One transient run without
`--create-db` showed 4 unrelated `store` test failures — confirmed as the already-documented
test-database-staleness artifact (a `transaction=True` test committing for real across separate
`pytest` process invocations, same mechanism Stage 5's notes already describe), not a real
regression; re-ran with `--create-db` and it was clean, matching every other stage's own numbers
in this file.
Coverage: notifications 96% (protocols.py excluded from the floor check, matching payments/'s
precedent), orders 99%, store 100% (floors 90%/90%/80%)
Notes:

**`WHATSAPP_MESSAGE_MAX_CHARS`'s placement and value, decided against the human's explicit
instruction not to fabricate a verified number.** Lives on `StoreSettings` (`whatsapp_message_max_chars`,
merchant-configurable, per the roadmap's own "conservative default in StoreSettings" wording), not
a `core/config.py` constant — this is exactly the kind of value CLAUDE.md's own rule already
covers ("if a merchant might change it, it is a StoreSettings field"). Default is **1000**
characters of raw message text, chosen only as a deliberately conservative placeholder — smaller
than every publicly-documented `wa.me` URL-length concern this session could find without a real
device, at the cost of triggering truncation more eagerly than a verified number might need to.
`docs/whatsapp-limits.md` states this explicitly at the top ("Status: not yet measured") with a
table for the human to fill in per §21's own instruction (Android Chrome, iOS Safari, WhatsApp
Web), rather than silently treating a guess as done. A `MinValueValidator(200)` floor on the field
stops a merchant from fat-fingering an unusably tiny number; the truncation algorithm's own
degenerate case (a budget too small even for a zero-item order's header+footer) is handled by
returning the full over-budget message honestly rather than crashing — covered directly by
`test_a_budget_too_small_even_for_a_zero_item_order_degrades_without_crashing`, which also proved
a coverage gap (a branch that looked untested) was a real, reachable path, not dead code.

**The truncation algorithm adds item lines one at a time, re-checking the full candidate (items so
far + the "…and N more" notice + the totals/delivery/tracking footer) against the budget on every
step**, rather than computing a byte budget for the item section in isolation — this is what
guarantees the totals/delivery/tracking tail is never itself the thing that gets cut off, matching
what a merchant or customer would actually need from a truncated message (item detail is the part
that's safe to summarise; the total a customer owes and the tracking link are not). Verified this
tail survives truncation directly, not just assumed:
`test_gate1_a_30_item_order_truncates_within_budget_with_notice_and_tracking_url` asserts
"Subtotal"/"Total"/"Deliver to" are all still present in the truncated output.

**Two real false positives in the gate-3 grep test, found before trusting it, both from the same
root cause: prose that *names* the forbidden substring without *constructing* one.** Stage 2's
own no-float-on-money-fields grep (`tests/test_no_float_fields.py`) only excludes *itself* from
its scan — it has no mechanism for a *different* file's docstring to safely discuss the term it's
checking for in prose. This stage's first draft of both the FloatField-adjacent comment in this
new grep test's own docstring, and two unrelated comments in `orders/views.py`/`orders/tests/
test_views.py` explaining *why* a blank merchant WhatsApp number degrades a certain way, tripped
their respective greps for exactly this reason. Fixed by rewording the prose to avoid the literal
trigger substrings rather than weakening either grep's precision — matches this project's existing
preference (Stage 2, Stage 5) for simple, blunt, reliable checks over clever ones that could miss
a real violation.

**Two real bugs caught by the human mid-implementation, both fixed before the first live-verification
pass, not after:**
1. The original "copy order details" button called `navigator.clipboard.writeText()`
   unconditionally and set the button's "Copied!" state regardless of whether that call actually
   succeeded. `navigator.clipboard` is a secure-context API — unavailable on a plain `http://`
   deployment outside `localhost` — so on real production traffic (this project has no HTTPS
   requirement recorded anywhere yet) the copy would silently fail while the button claimed
   success. Fixed: the message text is now always rendered in a visible, selectable
   `<textarea readonly>` (not hidden inside a JS-only-reachable `json_script` blob, which the
   first draft used) — recoverable by the customer even if every JS path on the page fails, which
   `test_confirmation_page_always_has_the_order_details_message_in_the_rendered_html` asserts
   directly. The copy button itself now only reports success after a real `writeText()` resolution,
   falling back to `textarea.select()` + `document.execCommand('copy')` (deprecated but still
   broadly supported) when the Clipboard API isn't available, and simply leaves the text selected
   for a manual Ctrl/Cmd+C if even that fails.
2. `StoreSettings.whatsapp_number` defaults to blank, and the original design let
   `WhatsAppLinkChannel.build_url(phone="", ...)` degrade to a real, documented WhatsApp behaviour
   (a link that opens the message ready to send to *any* contact the person picks) — correct in
   general, but wrong for this specific call site, since the whole point of the confirmation
   page's WhatsApp button is reaching *the merchant specifically*. Fixed: `OrderConfirmationView`
   now checks `StoreSettings.whatsapp_number` before building a URL at all, and omits the "Open
   WhatsApp" button entirely (not a broken/unaddressed one) when it isn't configured — the order
   number and the copyable message text remain regardless.
   `test_confirmation_page_omits_the_whatsapp_button_when_the_merchant_number_is_unconfigured`
   covers it; confirmed live too (cleared `whatsapp_number`, fetched the confirmation page, saw the
   link genuinely absent while the order number and textarea stayed present).

**Live-verified the full checkout-to-WhatsApp handoff against real WhatsApp infrastructure, not a
mock.** Placed a real order, and the confirmation page's JS auto-redirect (same-tab
`window.location.href`, 1.2s delay, reading the href already rendered on `#whatsapp-link` rather
than building a second copy of the URL) actually landed on `api.whatsapp.com`'s own "Chat on
WhatsApp with +92 300 1112222" page, showing the exact pre-composed message — order number, item,
subtotal/delivery/total, delivery address, and tracking URL, all correctly formatted — ready to
send. This is the strongest evidence available that the message format and the link-building logic
are actually correct against the real service, short of the device-level truncation measurement
that's still a human task.

**Stage 9/10 scope boundary, checked against the roadmap before writing any code, matching the
same discipline Stage 8 applied to the Stage 8/9 boundary.** §26's "merchant-initiated status-update
messages from the order detail page" names a portal page (order detail) that doesn't exist until
Stage 10. Built and tested `build_status_update_message()` fully in isolation this stage — six
status templates on `StoreSettings`, editable, each rendering correctly with a real order plus a
documented, tested graceful-degradation path for an unrecognised placeholder — but no portal button
calls it yet, since there's no portal order detail page to put one on. Recorded here explicitly,
same pattern as Stage 5's search endpoint existing before Stage 6 wired it into a page, so Stage 10
knows this exists and is ready to be wired in rather than rediscovering it.

**The `/track/` tracking URL Stage 9's messages already reference does not resolve to anything
yet — a deliberate forward reference, not an oversight.** Building even a minimal stub tracking
view now was considered and rejected: Stage 11 ("Public order tracking") owns real
security-sensitive scope for this exact page (rate limiting by IP, phone-match verification,
identical responses for "not found" vs. "phone doesn't match"), and a "harmless" placeholder now
risks either blurring that scope or needing to be thrown away. `_tracking_url()`
(`notifications/whatsapp/message_builder.py`) only ever includes the link when
`StoreSettings.site_url` is configured (blank by default — no example.com placeholder is ever sent
to a real customer), and the path constant `TRACKING_URL_PATH = "/track/"` is the contract Stage 11
must satisfy. Until then, a customer who clicks it gets a 404 — the honest state, not a silently
broken feature.

### Stage 10 — Order management and editing
Completed: 2026-08-13
Commits: d1cc37e feat(orders,inventory,portal): add order management and editing — Stage 10
         (this entry's own docs commit follows separately)
Acceptance gates: all passed
  1. Every allowed transition succeeds; every disallowed one is rejected with a 4xx —
     `orders/tests/test_state_machine.py::test_gate1_every_entry_in_the_allowed_transition_map_actually_succeeds`
     (walks every edge in `ALLOWED_TRANSITIONS` independently) and
     `test_gate1_a_disallowed_transition_raises` at the service layer;
     `portal/tests/test_order_views.py::test_gate1_a_valid_status_transition_succeeds` and
     `test_gate1_an_invalid_status_transition_is_rejected_with_a_4xx` at the HTTP layer (asserts
     `response.status_code == 400` specifically, not just "not 200"). Live-verified: the portal's
     status dropdown only ever offers the current status's legal next steps (confirmed at Pending
     Confirmation, Confirmed, and Processing), which is itself proof `allowed_transitions` renders
     correctly — the illegal-transition 400 path itself was exercised via the test client, not
     manually, since the UI structurally can't submit one.
  2. Editing a line quantity upward reserves the delta; downward releases it —
     `orders/tests/test_editing.py::test_gate2_a_quantity_increase_while_pending_reserves_the_delta`
     /`test_gate2_a_quantity_decrease_while_pending_releases_the_delta`, asserting the actual
     `StockReservation` row quantities, not just the `OrderItem`. Live-verified: raised a real
     order's quantity 3 -> 5 through the portal UI, confirmed via a direct DB query that the delta
     (not the whole new quantity) was reflected correctly and `stock_quantity` stayed untouched
     while still Pending Confirmation.
  3. A line-price override changes the total and writes an audit row showing both values —
     `test_gate3_a_price_override_changes_the_total_and_writes_an_audit_row_with_both_values`,
     which calls `event.refresh_from_db()` before asserting on `before`/`after` specifically to
     prove the `JSONField(encoder=DjangoJSONEncoder)` round-trip, not just the in-memory dict.
     Live-verified: overrode a line's price 750 -> 600 through the portal UI, watched subtotal/total
     recalculate and the Edit history panel render "Price overridden — ... " with the actor and
     timestamp.
  4. Editing a dispatched order is refused — `test_gate4_editing_a_dispatched_order_is_refused`
     (all four edit actions) and, at the HTTP layer,
     `test_gate4_editing_a_dispatched_order_via_http_is_refused_with_a_4xx`. Live-verified: walked
     a real order from Confirmed through Processing and watched the detail page's item rows lose
     every Set/Remove/Add-line control, replaced with "This order is processing and can no longer
     be edited." — confirming editing locks out starting at Processing, not just Dispatched, per
     the literal two-status whitelist (see Open questions).
  5. Cancel-after-confirm restores exactly the confirmed quantity —
     `test_gate5_cancel_after_confirm_restores_exactly_the_confirmed_quantity`. A real bug in the
     first draft of `transition_status()` was caught here before any of this was reported done: it
     only special-cased the `Confirmed -> Cancelled` edge specifically, but the transition map also
     legally allows cancelling from `Processing`, `Ready to Dispatch`, and `Failed Delivery` — every
     one of which already ran `commit_all_for_order()` at the Confirmed step and has no reservation
     left, so cancelling from any of them with the narrower condition would have silently left stock
     decremented forever with no order left to ever use it. Fixed to `to_status == CANCELLED`
     without the `from_status == CONFIRMED` qualifier — self-caught while writing
     `test_gate1_every_entry_in_the_allowed_transition_map_actually_succeeds`, not by a review pass.
  6. The timeline renders every transition in order with actor and timestamp —
     `test_gate6_timeline_lists_every_transition_in_order_with_actor_and_timestamp`, which also
     proves the very first row (`from_status=""`, `actor=None`) is the order's own creation event,
     written by `create_order()` itself — the timeline is never empty for a freshly-placed order.
     Live-verified: the status timeline panel rendered "pending_confirmation — Order placed by
     customer / Customer" as its first row before any merchant action, then each subsequent
     transition with `stage10owner` and a real timestamp.
  7. Quality gate green — see numbers below.

Quality gate, final numbers: `ruff check` — all checks passed. `ruff format --check` — all files
formatted (203 files). `mypy .` (whole tree, unscoped) — no issues in 189 source files.
`makemigrations --check --dry-run` — no changes detected. `pytest --create-db` — 491 passed.
Coverage: `orders` 95% (`editing.py`/`state_machine.py`/`status.py` all 100%; `models.py` 96%, the
only gaps two more untested `__str__` methods, same accepted pattern as every prior stage; floor
90%), `inventory` 97% (`services.py` 99%; floor 90%), `portal` 93% (`order_forms.py`/`order_views.py`
both 100%; floor 80%). `manage.py check --deploy` clean under `config.settings.prod` (DEBUG=False,
ALLOWED_HOSTS set, a real random `SECRET_KEY`, placeholder R2 credentials). `manage.py check` clean
under `config.settings.dev`.
Coverage: orders 95%, inventory 97%, portal 93% (floors 90%/90%/80%)
Notes:

**The two things flagged before implementation started were both real design forks, not just
reminders — worth recording why each landed where it did.**

1. *`build_status_update_message()` had to be wired in without rebuilding it, and the recipient
   turns out to be the opposite number from Stage 9's confirmation page.* Stage 9 built and fully
   tested the function and all six status templates but had no caller — `OrderDetailView`'s context
   now calls it directly (a cheap string-format call, no reason for a separate HTTP round-trip) and
   builds the `wa.me` link via `WhatsAppLinkChannel().build_url(phone=order.
   customer_whatsapp_number, ...)`. The confirmation page (Stage 9) addresses the merchant — the
   customer is telling the merchant a new order exists. This page addresses the customer — the
   merchant is telling them their order's status changed. Getting this backwards (addressing
   `StoreSettings.whatsapp_number` here, matching the confirmation page's pattern by habit) would
   have silently sent every status update to the merchant's own number instead of the customer's;
   caught while designing, not after, by re-reading §26's own sentence ("a pre-composed `wa.me` link
   opens addressed to the customer") rather than assuming the prior stage's pattern generalized.
2. *Every reservation/stock change from an edit or a status transition routes through named
   `inventory.services` functions — `orders/` never imports or constructs a `StockReservation`.*
   This required two genuinely new functions (`release_reserved()`, the partial-quantity
   counterpart `reserve()` never needed until now; `consume()`, a direct decrement with `reserve()`'s
   own availability check but no reservation row, for editing an already-`Confirmed` order) and
   three bulk per-order wrappers (`commit_all_for_order`/`release_all_for_order`/
   `restore_all_for_order`) so `orders/state_machine.py` and `orders/editing.py` only ever say
   "commit/release/restore/consume this order's stock" in one call, never enumerate
   `StockReservation` rows themselves. The alternative — reading `StockReservation.objects.filter(
   order=order)` directly from `orders/` to get IDs to hand to the existing per-reservation
   functions — was considered and rejected before writing any code, since it would have made the
   boundary a convention ("orders/ doesn't *write* StockReservation, but does read it") rather than
   a fact ("orders/ never imports the model at all") — the latter is what the instruction actually
   asked for and what a future `grep -rn StockReservation orders/` can verify mechanically.

**A second bug an early test-writing pass caught, independent of the gate-5 bug above.** The
original `transition_status()` also missed that `Failed Delivery -> Cancelled` is a legal edge in
`ALLOWED_TRANSITIONS` (a delivery attempt failed, the merchant gives up and cancels) — same fix as
gate 5's, since both are instances of the same underlying rule ("cancelling from anywhere past
Confirmed must restore stock, not just from Confirmed itself").

**`OrderEditEvent` is a new model the spec doesn't name explicitly** — §23 says only "writes an
audit row capturing before and after values," and roadmap Stage 10 says the same. Recorded under
Deviations below, not as a problem: `audit.AuditLog` (§33) is P1/Stage 15 and doesn't exist yet, so
this is scoped narrowly to order edits the same way `InventoryAdjustment` (Stage 4) is scoped to
stock changes rather than waiting on a general audit app. `before`/`after` are `JSONField(null=True,
encoder=DjangoJSONEncoder)` rather than typed columns, since the shape genuinely differs by
`edit_type` (quantity+price for a quantity change; a full item snapshot, with one side legitimately
`None`, for add/remove) — `null=True` specifically so "there was nothing here yet" (add/remove's
missing side) round-trips as SQL `NULL`, not an empty dict indistinguishable from a real empty
value.

**Order editing's actual availability arithmetic depends on which side of the Confirmed transition
the order is on, and the two sides use genuinely different mechanisms — this is the load-bearing
design fact for this whole stage, not an implementation detail.** While `Pending Confirmation`,
stock is only ever *reserved* (Stage 4's `StockReservation`, never touching `stock_quantity`); an
edit there calls `reserve()`/`release_reserved()`. The moment an order becomes `Confirmed`,
`commit_all_for_order()` (this stage's own new wiring — see below) permanently decrements
`stock_quantity` and deletes every reservation the order held, so there is nothing left to adjust a
delta against; an edit there instead calls `consume()`/`restore()` directly against
`stock_quantity`, under the same variant-row lock `reserve()` already uses. Both branches live in
`orders/editing.py`'s own `if locked_order.status == PENDING_CONFIRMATION: ... else: ...` — reading
either function without keeping this fork in mind makes half of it look redundant with the other
half; it isn't.

**Stage 4's `reserve()`/`commit_reservation()` had never actually been wired to a real order
lifecycle before this stage — `transition_status()`'s `Pending Confirmation -> Confirmed` edge is
the first real caller of `commit_reservation()` (via the new `commit_all_for_order()` wrapper)
anywhere in the codebase.** Grepped for existing callers before writing any code, per the pattern
this session's prior stages already established (Stage 3's archive-decision grep, Stage 9's
tracking-URL forward-reference check) — confirmed `commit_reservation()` was tested in isolation
since Stage 4 but never invoked by application code, meaning no order had ever actually had its
stock permanently decremented at confirmation before this stage's status-transition view existed.

**The status-transition map reads the requirements' arrow chain as strictly sequential — no
skip-ahead — which is a genuine design choice, not the only reasonable reading.** `orders/status.py`
requires `Confirmed -> Processing -> Ready to Dispatch -> Dispatched` in that literal order; a
merchant who never uses "Ready to Dispatch" as a distinct step can't jump `Processing -> Dispatched`
directly. Requirements doesn't say either way. Recorded as an open question below rather than
silently picked, since a real merchant workflow might want to skip steps and this map would refuse
it with a 400.

**Live-verified end to end against the running dev server**, not just the test suite: created a
real order via the actual checkout flow (cart -> `create_order()`), logged into the portal as a
temporary superuser, and walked quantity edit, price override, add-line by SKU, and a
`Pending Confirmation -> Confirmed -> Processing` status transition — each one checked directly
against the database (not just the rendered page) to rule out a stale-render false positive after
one screenshot appeared not to reflect an edit (it was a browser rendering artifact of the
screenshot tool, not a real bug — confirmed by querying the DB directly and by reloading the page,
both showing the edit had in fact applied). The `wa.me` link on the Confirmed status's "Notify
customer" panel was read directly via the page's accessibility tree (not just eyeballed) and
confirmed addressed to `923005551234` (the fixture's customer WhatsApp number), never
`923001112222` (the fixture's `StoreSettings.whatsapp_number`). Temporary superuser, category,
products, and order all removed afterward via a scratch script that was itself deleted; nothing
from this check is in the dev database or repo. The invalid-status-transition 400 path could not be
triggered through the live UI (the status dropdown structurally only ever offers legal next steps,
which is itself the correct behavior) — that path's HTTP-level proof is the Django test client
assertion in gate 1, not a live click.

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
- [Stage 8] Checkout's `city` field is a required free-text `CharField`, not the `<select>` §20
  literally describes ("city — drives delivery charge"). Sourcing a select's options from
  `DeliveryZone` would make checkout unsubmittable for any flat-rate/free-threshold merchant with
  zero configured zones, and no portal CRUD exists yet to populate them (Django admin only this
  stage). Reversible; the natural fix is a portal `DeliveryZone` CRUD (no roadmap stage currently
  assigns one — see Proposed spec amendments) followed by switching this field to a
  `ModelChoiceField`/dynamic select once one exists.
- [Stage 10] `OrderEditEvent` is a model neither `requirements.md` nor `roadmap.md` names —
  both say only "writes an audit row capturing before and after values." Added a small,
  purpose-scoped model (order FK, actor, edit_type, description, before/after JSON) rather than
  waiting on `audit.AuditLog` (§33, P1/Stage 15, doesn't exist yet), the same reasoning
  `InventoryAdjustment` (Stage 4) already established for stock-change audit rows. Reversible;
  once Stage 15 builds a general audit app, `OrderEditEvent` rows could be migrated into it or left
  as a specialised sibling — not decided here.

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
- [Stage 8] §24 lists `payment_method` among fields that are "all nullable — §28", but §28 itself
  says "`payment_method` defaults to `whatsapp_pending`" — a field that always has a real default
  is never actually null in practice, and the two sentences are in tension for this one field only
  (every other payment field in the same list genuinely is nullable and unused in MVP). Resolved in
  favour of §28's more specific instruction: `payment_method` is `CharField(default="whatsapp_pending")`,
  not nullable. Proposed change: correct §24's grouping to exclude `payment_method` from the
  "all nullable" list, or correct §28 if a nullable `payment_method` was actually intended.
- [Stage 8] §29 describes derived `total_orders`/`total_spent`/`last_order_at` on `Customer` and a
  customer-profile-with-order-history page, but no roadmap stage — checked end to end — ever
  assigns a page to build that profile view (same gap class as Stage 1's Django-admin-mount-path
  question: a real product surface with no stage owning it). Not built speculatively this stage;
  `Customer` itself ships with just the fields explicitly named (`name`, `phone`,
  `whatsapp_number`, `email`). Proposed change: add an explicit "Customers" deliverable to some
  stage (Stage 10's order-management work is the most natural fit, since it already builds portal
  order list/detail UI) rather than leaving it unassigned. **Not resolved by Stage 10** — that
  stage's roadmap entry doesn't list a customer-profile page among its own deliverables/gates, so
  none was built; still open.

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
- [Stage 7] The PDP's `Add to Cart` button (Stage 6) only ever greys out for `available_quantity <=
  0` — it does not currently account for `is_active`, so a variant deactivated while a customer is
  looking at its PDP still shows "In stock" / an enabled button. The server-side refusal is
  authoritative and already correct (`cart.services.add_item()` checks `is_active` and returns
  `CartMutationError(available_quantity=0)`, rendering "That item is no longer available." on
  click — confirmed live), so this is a UX gap, not a correctness one. Assumed in the meantime:
  acceptable, since the roadmap's Stage 6 gate 4 ("an out-of-stock variant cannot be added ... and
  the PDP says so specifically") only names out-of-stock, not deactivation, and fixing it means
  threading `is_active` into `ProductDetailView`'s `variants_data`/Alpine state — a Stage 6 template
  this stage didn't set out to reopen. Revisit alongside any future PDP work, or Stage 12's quality
  pass.
- [Stage 8] Double-submit at checkout (two rapid clicks, or two tabs, creating two orders from the
  same cart) is not fully solved. `create_order()` locks the `Cart` row at the start of the
  transaction, which serializes two requests that both resolve to the *same, already-existing* Cart
  row — but two requests can still resolve to two different `Cart` rows, or race `Cart` creation
  itself, neither of which the lock touches. The advisor's second review confirmed this explicitly
  (a correction to the original design's claim that the lock solved it). Assumed in the meantime:
  low real-world frequency (checkout is a full-page POST, not a repeatable HTMX action like cart's
  own mutations), and the actual failure mode if it does happen is "two legitimate orders" — not
  data corruption, not overselling (each order still independently re-validates and reserves stock
  under `reserve()`'s own lock). Revisit if it turns out to matter in practice — an idempotency
  token on the checkout form, or disabling the submit button client-side, are the two obvious
  fixes, neither implemented here since neither is spec-required.
- [Stage 10] `EDITABLE_STATUSES` is read as the literal two-status whitelist from §23's operative
  sentence ("While an order is Pending Confirmation or Confirmed, the merchant may...") rather than
  the looser "blocked from Dispatched onward" restatement in the same section — meaning editing is
  refused for `Processing` and `Ready to Dispatch` too, not just `Dispatched` and beyond. Assumed
  in the meantime: the narrower, more literal reading is safer to ship than the more permissive
  one, and easy to widen later (add two statuses to a frozenset) if the intent was actually
  broader. Revisit if a merchant workflow needs to negotiate a discount or quantity change after
  an order has moved into active processing.
- [Stage 10] `orders/status.py`'s `ALLOWED_TRANSITIONS` requires the main pipeline
  (`Confirmed -> Processing -> Ready to Dispatch -> Dispatched`) to proceed strictly in order, with
  no skip-ahead — a merchant who doesn't use "Ready to Dispatch" as a distinct step can't jump
  `Processing -> Dispatched` directly; the attempt is refused with a 400 like any other disallowed
  transition. Requirements doesn't specify either way. Assumed in the meantime: strict sequencing,
  since it's the literal reading of the arrow chain and the safer of two guesses. Revisit if a real
  merchant workflow needs to skip a step.
- [Stage 10] `release_expired_reservations()` (Stage 4's sweeper) still only deletes lapsed
  `StockReservation` rows — it does not transition the owning `Order` to `Expired`, even though
  that status exists specifically for "reservation lapsed" (§23) and Stage 10 now has the
  `transition_status()` machinery that could drive it. A `Pending Confirmation` order whose
  reservation the sweeper releases is left stuck at `Pending Confirmation` with no stock actually
  held, and `Expired` is reachable today only via a merchant manually selecting it in the portal.
  Not wired this stage — the roadmap's Stage 10 deliverables list doesn't mention the sweeper, and
  inventing an automatic order-status side effect on a background job wasn't asked for. Revisit
  either as a small Stage 10 follow-up or explicitly assigned to a future stage.

---

## Human tasks

Work only the human can do: real-device testing, credentials, hosting, domains, business
decisions. Not blockers unless a stage's acceptance gate depends on one.

```
- [ ] Measure the real wa.me payload ceiling on Android Chrome, iOS Safari, and WhatsApp Web;
      record in docs/whatsapp-limits.md and set WHATSAPP_MESSAGE_MAX_CHARS (stage 9)
- [ ] Visually confirm the order confirmation page (stage 9) with JavaScript actually disabled in
      a real browser. What's already verified without this: the Django test client (which never
      executes JavaScript) asserts the order number, the full WhatsApp message text, and the
      wa.me link are all present in the server-rendered HTML; a same-origin fetch() against the
      live dev server confirmed the same thing against real server output before any script runs.
      What's not verified: the actual rendered appearance/usability with a real browser's JS
      engine switched off — the Chrome extension this agent's browser automation runs through
      cannot reach chrome://settings or DevTools to toggle that (a capability limit, confirmed by
      trying three approaches before giving up, not skipped)
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

# Roadmap

Execution plan for the e-commerce store. This file replaces per-stage briefs. The agent works
through stages in order, autonomously, updating `specs/state.md` after each one.

**Authority order:** `specs/requirements.md` (what to build) → this file (in what order, and what
"done" means) → `CLAUDE.md` (how to build it). The agent may not edit `requirements.md` or this
file. Proposed changes go in `specs/state.md` under *Proposed spec amendments*.

**Stage rules**

- Stages are strictly ordered. Do not start stage N+1 before stage N's acceptance gates pass.
- Every stage ends with the full quality gate green: `ruff check`, `ruff format --check`,
  `mypy` (strict), `pytest --cov` at the coverage floor, `makemigrations --check --dry-run`,
  `manage.py check --deploy`.
- Commits are independent within a stage. A failure partway through must leave earlier commits
  working.
- Each stage's *Traps* section lists the failure modes specific to that work. Read them before
  designing, not after the tests fail.
- P0 stages 1–13 are the release. Do not pull P1 work forward, however small it looks.

---

## Environment (confirmed)

| Item | Value |
|---|---|
| Repo | `D:\ecommerce-store` |
| PostgreSQL | **18.4**, localhost:5432 |
| Database | `ecommerce` |
| DB user | `postgres` (dev only — production uses a least-privilege role) |
| Python | 3.11 |

This supersedes the "PostgreSQL 16" line in `requirements.md` §A1 and in `CLAUDE.md`. Everything
the spec relies on — `pg_trgm`, `word_similarity`, GIN indexes, `tsvector` — is present in 18.x.
CI must use a Postgres 18 service container to match.

---

# P0 — the release

## Stage 1 — Foundation

**Goal:** a fresh clone reaches a running, styled, tested, CI-green Django project in one command.

**Deliverables**

- Git repo, `.gitignore`, `README.md`, `TODO.md` (with a `## Debt` heading).
- `pyproject.toml`: ruff (line length 100; rules include `I`, `UP`, `B`, `ANN`, `RUF`), mypy
  `strict = true` with `mypy_django_plugin`, pytest-django config.
- `requirements/base.txt`, `dev.txt`, `prod.txt` — every version pinned exactly, no ranges.
- `setup_dev.ps1` and `setup_dev.sh`: venv, install, `.env` from `.env.example`, download the
  Tailwind standalone binary to `tools/`, migrate, seed a superuser from env vars, print next
  steps. Idempotent — running twice must succeed.
- `config/settings/{base,dev,prod,test}.py` via `django-environ`. `USE_TZ = True`,
  `TIME_ZONE = "Asia/Karachi"`, Argon2 first in `PASSWORD_HASHERS`, database cache and sessions.
  `prod.py` raises `ImproperlyConfigured` if `DEBUG` is truthy, and sets the `SECURE_*` family,
  `X_FRAME_OPTIONS = "DENY"`, `ALLOWED_HOSTS` from env.
- Migration enabling `pg_trgm` via `CreateExtension`. Needed now, not at stage 5, so the test
  database has it from the first `migrate`.
- `core/`: `TimeStampedModel`, `config.py` (typed constants), `storage.py` (FileSystem in dev, R2
  in prod, selected by settings — never by `if DEBUG`), `templatetags/money.py` (the single PKR
  formatter; nothing in the project formats currency inline).
- `store/`: `StoreSettings` singleton. `CheckConstraint` pinning the primary key, `save()` pinning
  `pk`, `load()` with cached retrieval and cache invalidation on save, creating the row with
  defaults on first call. Admin registered with add and delete permissions returning `False`.
  Context processor exposing it to all templates.
- `templates/base.html` plus separate `storefront/base.html` and `portal/base.html`. HTMX 2 and
  Alpine 3 **vendored** into `static/vendor/`, not CDN-loaded. Tailwind standalone build to
  `static/css/app.css`. Styled `404.html` and `500.html`.
- `/healthz/` returning JSON with app status and DB connectivity. No auth, no PII, no version.
- `.github/workflows/ci.yml`: Postgres 18 service, Python 3.11, then install → `ruff check` →
  `ruff format --check` → `mypy` → `makemigrations --check --dry-run` → `pytest --cov` → 
  `check --deploy`.

**Acceptance gates**

1. `setup_dev.ps1` completes on a fresh clone with no manual steps, and succeeds when run twice.
2. `/healthz/` returns 200 with DB connectivity true.
3. Store Settings shows exactly one row, PKR and `Asia/Karachi`; Add and Delete are absent.
4. Editing a store setting is reflected in the next template render (cache invalidated).
5. Under `DEBUG=False`, an unknown URL renders the styled 404, not a Django error page.
6. HTMX and Alpine load from `static/vendor/` — verify no CDN request.
7. Full quality gate green. Coverage floor 80% on `core` and `store`.

**Traps**

- SQLite is not an acceptable fallback under any circumstance. If Postgres is unreachable, this is
  a hard stop (see *Intervention* in `CLAUDE.md`).
- `makemigrations --check` in CI is the step that catches model drift later. Do not make it
  non-blocking.

---

## Stage 2 — Catalog domain model

**Goal:** the data model from `requirements.md` §2, migrated and tested. Models only — no portal
UI, no storefront views.

**Deliverables**

`catalog/models.py`: `Brand`, `Category` (self-FK, two levels enforced), `AttributeDefinition`,
`AttributeValue`, `Product`, `ProductVariant`, `ProductAttributeValue`, `VariantAttributeValue`,
`ProductImage`. Field lists exactly as §2 specifies.

Invariants, each enforced in the database where expressible and in `save()`/`clean()` otherwise:

- Every product has at least one variant. Products saved without one get an auto-created default
  (`is_default=True`), so no downstream code ever branches on "does this have variants".
- A category's parent must itself have no parent.
- A variant's set of `VariantAttributeValue` rows is unique within its product.
- Exactly one `is_primary` image per product, and at most one `is_default` variant.
- `AttributeValue` unique on `(definition, slug)`.

Derived properties on `ProductVariant`: `discount_percent`, `available_quantity` (returns
`stock_quantity` until stage 4 wires reservations in), `is_in_stock`, `is_low_stock`.
On `Product`: `display_price` (minimum active variant price) and `has_price_range`.

Image derivative generation on upload: `thumb` 200px, `card` 600px, `full` 1400px, WebP with a
JPEG fallback, generated synchronously.

Slug generation with collision handling. Slugs are stable — a name change does not silently
change the slug (see stage 12 for redirects).

Indexes per §42. All money `DecimalField(max_digits=12, decimal_places=2)`.

**Acceptance gates**

1. Every invariant above has a test proving it is enforced, including the failure case.
2. Saving a product with no variants produces exactly one default variant.
3. A three-level category save raises `ValidationError`.
4. Two variants of one product with identical attribute sets raise an integrity error.
5. `display_price` returns the minimum across active variants and ignores inactive ones.
6. Image upload produces three derivatives with correct dimensions; test images are generated at
   runtime with Pillow, **never committed as binary fixtures**.
7. `grep -rn "FloatField" .` returns nothing outside migrations of third-party apps.
8. Quality gate green. Coverage floor 85% on `catalog`.

**Traps**

- The default-variant invariant is load-bearing for stages 7–10. If it is enforced only in the
  admin form rather than on the model, every later stage inherits a null-price branch.
- `ProductImage.alt_text` falls back to the product name rather than being nullable — §37 makes
  alt text mandatory.

---

## Stage 3 — Merchant portal: catalog management

**Goal:** the merchant can run their catalog end to end through the browser.

**Deliverables**

`portal/` views, all behind login and an owner-or-staff permission mixin enforced per view — never
by hiding a nav link. Django templates plus HTMX; no SPA.

- Product list: paginated, searchable, filterable by status, category, brand.
- Product create and edit: core fields, variant inline formset (SKU, price, compare-at, stock,
  low-stock threshold, attribute values, active), image upload with drag-reorder (SortableJS),
  primary-image selection, image delete and replace.
- Category, subcategory, and brand CRUD with ordering and publish toggles.
- Attribute definition and value management, including the `is_filterable` and `is_variant_option`
  flags.
- Publish and unpublish, feature and unfeature, archive.
- Portal shell: sidebar navigation, breadcrumbs, consistent form and table partials,
  messages framework wired to a toast component.

**Acceptance gates**

1. A merchant can create a product with three variants across two attributes and publish it,
   without touching Django admin.
2. Deleting a variant that is the last remaining variant is refused with a clear message.
3. Reordering images persists and survives a reload.
4. A staff user is blocked (403, not a hidden link) from store settings and user management.
5. `assertNumQueries` on the product list stays flat as the fixture count grows from 5 to 50.
6. Quality gate green. Coverage floor 80% on `portal`.

**Traps**

- The variant formset is where N+1 queries enter the codebase. Use `prefetch_related` on variants
  and their attribute values from the start.
- Do not let the portal reuse storefront partials. They diverge; §11 wants the storefront to feel
  nothing like an admin tool.

---

## Stage 4 — Inventory and stock reservation

**Goal:** the reservation policy from §10, correct under concurrency.

**Deliverables**

- `inventory/models.py`: `StockReservation` (variant, order FK nullable until stage 8, quantity,
  `expires_at` indexed), `InventoryAdjustment` (variant, delta, reason, actor, note).
- `inventory/services.py`: `reserve`, `release`, `commit_reservation`, `restore`, `adjust`. Every
  function that reads availability and then writes takes `select_for_update()` on the variant row
  inside an explicit transaction.
- `ProductVariant.available_quantity` now subtracts active reservations.
- `release_expired_reservations` management command: idempotent, concurrency-safe, logs a count.
  Cron entry documented in the README.
- Portal inventory page: product, variant label, SKU, on-hand, reserved, available, low-stock and
  out-of-stock flags, inline adjustment, filters.

**Acceptance gates**

1. Reserve → confirm decrements on-hand and clears the reservation.
2. Reserve → expire releases the reservation and leaves on-hand untouched.
3. Reserve → cancel releases without touching on-hand.
4. Restore after a post-confirmation cancellation increments on-hand.
5. **Concurrency test:** two simultaneous reservations for the last unit — exactly one succeeds,
   the other fails cleanly with a specific error. Use threads or `transaction.atomic` with a real
   database connection; a mocked test does not count.
6. The sweeper is safe to run twice concurrently.
7. Every adjustment writes an `InventoryAdjustment` row.
8. Quality gate green. Coverage floor 90% on `inventory` — this is the highest-consequence module.

**Traps**

- `available_quantity` computed in Python across a queryset is an N+1 generator. Provide an
  annotated queryset method and use it in every list view.
- `expires_at` must be timezone-aware and compared against `timezone.now()`, not `datetime.now()`.

---

## Stage 5 — Search

**Goal:** every case in §15.1 passes.

**Deliverables**

- `Product.search_text` denormalised column: name, brand, all variant SKUs, category, subcategory,
  tags, filterable attribute values. Rebuilt on save via signal and by a `rebuild_search_index`
  management command.
- Migration adding `GIN (search_text gin_trgm_ops)` and `GIN (to_tsvector('simple', search_text))`.
- Migration setting `pg_trgm.word_similarity_threshold` explicitly.
- `search/backends.py`: `SearchBackend` protocol, `PostgresSearchBackend` implementing it, selected
  by settings. One implementation only.
- Ranking blending `ts_rank` with `word_similarity`. `ILIKE 'q%'` prefix fast path for suggestions.
- HTMX type-ahead endpoint, debounced ~200ms, returning a partial.

**Acceptance gates**

1. **Write the §15.1 table as tests first, watch them fail, then implement.** All six cases pass:
   `afnan 9pm`, `9pm`, `AFNAN`, `afnn`, `9PM afnan`, partial SKU.
2. Renaming a product updates `search_text` without a manual command.
3. `rebuild_search_index` is idempotent and reports a count.
4. Search across a 1,000-product generated fixture returns in a time the test asserts an upper
   bound on, and `EXPLAIN` confirms the GIN index is used rather than a sequential scan.
5. No view imports `PostgresSearchBackend` directly — everything goes through the protocol.
6. Quality gate green. Coverage floor 90% on `search`.

**Traps**

- **`similarity()` will fail the `9pm` case.** A three-character query contributes too few trigrams
  against a long product name. Use `word_similarity()` / the `%>` operator, which scores against
  the best-matching word extent inside the target. If `9pm` is failing, this is why.
- Do not rely on the default `word_similarity_threshold`. Set it in a migration so CI and
  production agree.

---

## Stage 6 — Storefront: browse, filter, sort

**Goal:** §11–§18, mobile-first.

**Deliverables**

Home (hero, featured, new arrivals, category tiles, footer per §13). Category and listing pages.
Product detail page with gallery, variant selector driving price and availability, quantity
selector, lightbox. Filtering per §16 with facet counts, composing across facets, state in the
query string. Sorting per §17. Pagination everywhere. Skeleton loaders, empty states, error states.
Responsive across all breakpoints in §12.

**Acceptance gates**

1. Filters compose: category + brand + price range + an attribute facet returns the correct set,
   with correct facet counts.
2. Filter state survives a page reload and the browser back button.
3. Selecting a variant on the PDP updates price, availability, and gallery hero without a reload.
4. An out-of-stock variant cannot be added to the cart, and the PDP says so specifically.
5. `assertNumQueries` bounded on the listing page and the PDP, and flat as fixture count grows.
6. Every list and detail view has a defined empty state and a skeleton loader.
7. Quality gate green.

**Traps**

- **Variant fan-out.** Filtering products by variant price or availability with `JOIN` + `DISTINCT`
  corrupts pagination counts. Use `EXISTS` subqueries. This is the single most likely defect in
  this stage.
- Facet counts must reflect the *other* active filters, not the unfiltered catalog, or the counts
  lie.

---

## Stage 7 — Cart

**Goal:** §19. Server-side, session-keyed.

**Deliverables:** `Cart` and `CartItem` (FK to **variant**, never product). Add, increment,
decrement, remove, clear — all HTMX partial updates to badge and drawer. Availability re-checked on
every mutation with a specific message when it changes. Subtotal, delivery placeholder, total.

**Acceptance gates**

1. Adding beyond `available_quantity` is refused with the actual available number in the message.
2. A cart item whose variant goes out of stock between add and view is flagged, not silently
   dropped.
3. A variant deactivated after being added is handled without a 500.
4. No page reload on any cart mutation.
5. Quality gate green. Coverage floor 85% on `cart`.

---

## Stage 8 — Checkout and order creation

**Goal:** §20, §22, §24, §27 — the transactional core.

**Deliverables**

- `customers/models.py`: `Customer`, matched on normalised phone.
- `orders/models.py`: `Order` and `OrderItem` exactly per §24, including every snapshot field and
  the nullable payment columns.
- `shipping/`: `DeliveryCalculator` protocol with the three strategies from §27, plus
  `DeliveryZone`. Charge snapshotted onto the order.
- `payments/`: the `PaymentProvider` protocol and the payment-state enum. **Nothing else.**
- Order number `ORD-{seq}-{rand}` per §22, from a database sequence, unambiguous alphabet.
- Single-page guest checkout. Phone validation normalising to E.164. Review before submit.
- Order creation in one transaction: validate → re-check availability under `select_for_update` →
  create order and item snapshots → create reservations → generate number → commit.

**Acceptance gates**

1. **Snapshot test:** create an order, then change the product's price and name, then delete the
   product. The order still displays the original name, SKU, and unit price.
2. Every displayed order value comes from the snapshot. `grep` the order templates for
   `.variant.price` and `.variant.product.name` — both must return nothing.
3. A failure mid-creation rolls back completely: no orphan order, no orphan reservation.
4. Availability changing between cart view and submit produces a per-line error naming the product.
5. Order numbers are unique under a concurrent-creation test.
6. Each of the three delivery strategies calculates correctly, including the free-delivery
   threshold combined with city rates.
7. Quality gate green. Coverage floor 90% on `orders`.

**Traps**

- The snapshot rule is the one most likely to be violated by a template author reaching through the
  FK because the numbers happen to match today. Gate it with the grep in acceptance 2.
- `OrderItem.variant` is `on_delete=SET_NULL`. If it is `CASCADE`, deleting a product destroys
  order history.

---

## Stage 9 — WhatsApp handoff

**Goal:** §21, §26.

**Deliverables:** `notifications/` with a `NotificationChannel` protocol and a
`WhatsAppLinkChannel`. `whatsapp/message_builder.py` producing the §21 message format. Payload
capped at `WHATSAPP_MESSAGE_MAX_CHARS` (conservative default in `StoreSettings`), truncating to
`…and X more items` plus the tracking URL. Confirmation page always showing the order number, a
copy-order-details button, and a re-open-WhatsApp link. Merchant-initiated status-update messages
from the order detail page, templated per status.

**Acceptance gates**

1. A 30-item order produces a message within the budget, with the truncation notice and a working
   tracking URL.
2. The order exists and is visible in the portal whether or not the customer ever sends the
   message.
3. No module outside `notifications/` constructs a WhatsApp string.
4. The confirmation page renders fully with JavaScript disabled — the redirect is an enhancement,
   not the mechanism.
5. Quality gate green.

**Note for the human:** the real `wa.me` truncation ceiling must be measured on Android Chrome,
iOS Safari, and WhatsApp Web, and recorded in `docs/whatsapp-limits.md`. The agent cannot do this.
Log it in `state.md` under *Human tasks* — it is not a blocker.

---

## Stage 10 — Order management and editing

**Goal:** §23 including the order-editing requirement.

**Deliverables:** portal order list (filter by status, date, search by order number and phone) and
detail. Status state machine with an explicit allowed-transition map in typed config; an invalid
transition is a 4xx, not a silent no-op. `OrderStatusEvent` written on every transition. Order
editing while `Pending Confirmation` or `Confirmed`: change quantity, remove line, add line,
override line unit price — each adjusting reservations, recalculating totals, and writing an audit
row with before and after. Editing blocked from `Dispatched` onward. Tracking number and courier
fields. Stock restored on post-confirmation cancellation and on return.

**Acceptance gates**

1. Every allowed transition succeeds; every disallowed one is rejected with a 4xx.
2. Editing a line quantity upward reserves the delta; downward releases it.
3. A line-price override changes the total and writes an audit row showing both values.
4. Editing a dispatched order is refused.
5. Cancel-after-confirm restores exactly the confirmed quantity.
6. The timeline renders every transition in order with actor and timestamp.
7. Quality gate green.

---

## Stage 11 — Public order tracking

**Goal:** §25.

**Deliverables:** public lookup by order number + mobile. Displays status, date, items, total,
delivery status, tracking number, timeline. Rate limited by IP with a longer lockout after repeated
failures. Failed attempts logged.

**Acceptance gates**

1. "Order not found" and "phone does not match" return byte-identical responses.
2. Rate limiting triggers at the configured threshold and the lockout applies.
3. The response contains no email, no full address, no merchant notes, no internal IDs — assert on
   the rendered HTML, not just the context.
4. Quality gate green.

---

## Stage 12 — SEO and performance pass

**Goal:** §34, §35, §36, §37.

**Deliverables:** per-object meta title and description with generated defaults; Open Graph and
Twitter Card tags; `Product` JSON-LD with offers driven off the default variant; `BreadcrumbList`
JSON-LD; `sitemap.xml`; `robots.txt`; canonical URLs; old-slug 301 redirects. WebP `srcset` with
explicit dimensions. HTTP caching on static and media. Accessibility: keyboard navigation, AA
contrast, labelled fields, visible focus, 44px touch targets, `aria-describedby` on errors,
skip-to-content.

**Acceptance gates**

1. JSON-LD validates against a schema validator for a product with and without a price range.
2. `sitemap.xml` includes every published product and category, and excludes drafts.
3. Renaming a product 301-redirects the old slug.
4. `assertNumQueries` bounded on home, listing, PDP, cart, and order list.
5. No image renders without width and height attributes.
6. A keyboard-only pass reaches every interactive element on the PDP and checkout.
7. Quality gate green.

---

## Stage 13 — Hardening and go-live readiness

**Goal:** the release is deployable and recoverable.

**Deliverables:** Caddyfile. Deployment runbook in `docs/deploy.md`. Nightly `pg_dump` plus media
sync script, 30-day retention, and **a restore procedure that has actually been executed once**.
Production settings audit. Rate limiting on login, checkout, tracking, and search. File upload
validation by magic bytes and size. Least-privilege database role for production. Error monitoring
hook. `.env.example` complete.

**Acceptance gates**

1. `manage.py check --deploy` clean with production settings and a realistic env.
2. A dump is taken and restored into a scratch database, and the restored data verifies.
3. Every rate limit has a test.
4. A file with a `.jpg` extension but a non-image payload is rejected.
5. No secret, credential, or customer PII appears in any log line or error page.
6. Quality gate green across the whole project.

**P0 complete.** Update `state.md` and stop. Do not begin P1 without the human confirming go-live
priorities.

---

# P1 — operate at scale

Sequence: **14** dashboard and analytics (§39) → **15** audit trail with a portal UI (§33) →
**16** CSV bulk import (§31) → **17** staff role and granular permissions (§32) → **18** WhatsApp
notification templates in store settings → **19** accessibility audit and performance budget
verification against §36.

**CSV import format — decided, do not re-open.** One row per variant. A `product_handle` column
groups rows into products; the first row for a handle supplies the product-level fields, subsequent
rows supply variant-level fields only. Attributes as `attr:Size`, `attr:Colour` columns. Images as
a pipe-separated URL list on the first row of each handle. Validate, preview, confirm, import, then
emit a downloadable failed-row CSV.

---

# P2 — not now

Coupons, discounts, flash sales, bundles, wishlists, reviews, ratings, customer accounts, saved
addresses, reordering, abandoned cart, courier APIs, payment provider implementations, Meilisearch,
multiple warehouses, marketing, AI features. Anything in `requirements.md` §49.

Do not build any of this. Do not add abstractions in anticipation of it beyond the protocols
already specified in §26, §27, and §28.

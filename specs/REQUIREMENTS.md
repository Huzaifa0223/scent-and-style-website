# E-Commerce Store — Product Requirements v2

**Status:** Authoritative. Supersedes `E-Commerce_Store_Application_Requirements.docx` (v1).
**Owner:** M. Huzaifa
**Last amended:** 11 August 2026

---

## 0. Change log vs v1

Decisions taken after review of v1. Where v2 conflicts with v1, **v2 wins**.

| # | Change | Rationale |
|---|--------|-----------|
| C1 | **Product variants are a first-class model.** Price, SKU, and stock live on `ProductVariant`, not `Product`. | v1 §7 put price/stock on the product while §16 asked for Size/Colour filtering. Those are incompatible. Retrofitting variants later means rewriting cart, inventory, and order items. |
| C2 | **No REST API layer.** v1 §43 is struck. The application is server-rendered Django end to end. | No consumer exists for the API. Speculative surface area with real maintenance cost. |
| C3 | **No multi-tenancy, now or later.** v1 §3's "modular enough for future multi-tenancy" is struck. | Confirmed single merchant permanently. No `store_id` FK, no tenant scaffolding, no defensive abstraction. |
| C4 | **Stock reservation model defined.** Stock is reserved at order creation with a TTL, decremented at confirmation. | v1 §10 never said *when* stock moves. Both naive answers fail (permanent lock vs oversell). |
| C5 | **Order editing is required.** Merchants can amend items, quantities, and line prices before confirmation. | v1 assumed checkout output is final. WhatsApp negotiation makes this false in practice. |
| C6 | **Order line items are immutable snapshots.** Product name, variant label, SKU, and unit price are copied onto `OrderItem` at creation. | v1 §24 implied a live FK to product price. Changing a price would silently rewrite order history. |
| C7 | **Stack fixed** (§A1). Django 5.2 + Postgres 16 + HTMX/Alpine/Tailwind, server-rendered. | v1 §42 deferred the stack while §34 (SEO) and §36 (mobile performance) constrained it hard. A client-rendered SPA cannot satisfy both. |
| C8 | **WhatsApp deep-link payload is capped and truncation-safe.** | `wa.me/?text=` is a URL query parameter. Long orders silently truncate. |
| C9 | **Order numbers carry a random component.** | Sequential numbers plus a phone number are enumerable on a public tracking endpoint. |
| C10 | **Testing, CI, and backup requirements added** (§53–§55). | Absent from all 52 sections of v1. |
| C11 | **Scope phased into P0 / P1 / P2** (§56). | v1's "MVP" was ~10–14 weeks of work presented as one release. |
| C12 | **All money is `Decimal`.** Currency PKR, timezone `Asia/Karachi`, both pinned in config. | Unstated in v1. Float money is a defect, not a preference. |

---

## 1. Product overview

A single-merchant e-commerce application: one deployment, one merchant, one store, one catalog.

Two interfaces, one Django project:

- **Merchant portal** (`/admin-portal/`, authenticated) — store settings, catalog, categories, inventory, customers, orders, delivery configuration, analytics, audit trail.
- **Consumer storefront** (`/`, public) — browse, search, filter, sort, product detail, cart, guest checkout, WhatsApp handoff, order tracking.

The first release does not process online payments. Customers place an order on the website and continue it over WhatsApp. Payment is a separate module with no code path assuming WhatsApp is the payment mechanism.

**Primary success question:** can a merchant put their catalog online quickly, and can a customer find and order a product from a fast, attractive storefront with minimal friction?

---

## A1. Technology stack (fixed)

| Layer | Choice | Version |
|-------|--------|---------|
| Language | Python | 3.11 |
| Framework | Django | 5.2 LTS |
| Database | PostgreSQL | 16 |
| Templating | Django templates | — |
| Interactivity | HTMX | 2.0.x |
| Local state | Alpine.js | 3.14.x |
| Styling | Tailwind CSS (standalone CLI — no Node dependency) | 3.4.x |
| Images | Pillow | pinned |
| Object storage | `django-storages` + Cloudflare R2 (S3 API); local `FileSystemStorage` in dev | pinned |
| Search | PostgreSQL `pg_trgm` + `tsvector`, behind a `SearchBackend` protocol | — |
| Testing | pytest, pytest-django, factory-boy, coverage | pinned |
| Lint / types | ruff, mypy (strict) | pinned |
| Front door | Caddy | 2.x |
| Background work | Django management commands invoked by cron | — |

**Explicitly out of scope for MVP:** Redis, Celery, DRF, Node/npm in the build, Docker in production, Elasticsearch/Meilisearch, any SPA framework.

**Justification for the exotic-looking choices:**

- *Server-rendered over SPA.* §34 requires per-product meta tags, Open Graph, JSON-LD, and a sitemap; §36 requires fast first paint on typical Pakistani mobile connections. Server-rendered HTML delivers both with near-zero JavaScript on the critical path. HTMX covers every interactive requirement the spec actually has (live search suggestions, filter application, cart quantity updates) without a build pipeline, hydration cost, or a second deploy target.
- *Tailwind standalone CLI.* Keeps Node out of the toolchain entirely. One binary, checked into `tools/`, invoked from `setup_dev.ps1`/`.sh`.
- *Cron over Celery.* The only periodic work is the reservation sweeper and the nightly backup. A broker plus a worker process is unjustified infrastructure for two cron entries. Revisit if WhatsApp Business API automation lands (§26).
- *No Redis.* Caching uses Django's database cache backend. Sessions use the database. Under single-merchant load this is correct until proven otherwise by a measured bottleneck.

---

## 2. Domain model

### 2.1 Catalog

**`Product`** — the marketing unit. One PDP, one URL, one gallery.

Fields: `name`, `slug` (unique, indexed), `brand` (FK, nullable), `category` (FK), `subcategory` (FK, nullable), `short_description`, `description`, `tags` (M2M), `status` (draft / published / archived), `is_featured`, `meta_title`, `meta_description`, `search_text` (denormalised, indexed — see §15), `created_at`, `updated_at`.

Product carries **no price and no stock**. Both live on variants.

**`ProductVariant`** — the purchasable unit. What goes in a cart, what has stock.

Fields: `product` (FK, `related_name="variants"`), `sku` (unique, indexed), `price` (`Decimal(12,2)`), `compare_at_price` (`Decimal(12,2)`, nullable), `stock_quantity` (int), `low_stock_threshold` (int), `weight_grams` (nullable), `length_mm` / `width_mm` / `height_mm` (nullable), `is_default` (bool), `position` (int), `is_active` (bool).

**Invariant: every product has at least one variant.** Single-variant products get an auto-created default variant on save. This is deliberate — it means cart, order, inventory, and stock-check code never branches on "does this product have variants". No conditional is cheaper than the one you never write.

**Derived properties on the variant:** `discount_percent` (from `compare_at_price`), `available_quantity` (`stock_quantity` minus active reservations — see §10), `is_in_stock`, `is_low_stock`.

**Display price on a product** is `min(price)` across active variants, rendered as "From Rs. X" when the product has more than one distinct price.

### 2.2 Attributes and variant options

One vocabulary serves both faceted filtering and variant definition.

- **`AttributeDefinition`** — `name` ("Size", "Colour", "Gender", "Material"), `slug`, `is_filterable`, `is_variant_option`, `position`.
- **`AttributeValue`** — `definition` (FK), `value` ("50ml", "Red"), `slug`, `position`. Unique on `(definition, slug)`.
- **`ProductAttributeValue`** — `product` FK + `value` FK. Non-variant facets. A product is Unisex; that does not create a variant.
- **`VariantAttributeValue`** — `variant` FK + `value` FK. The combination that defines the variant. A 50ml Red variant has two rows.

**Why normalised rather than denormalised `option1_name`/`option1_value` columns:** §16 requires filtering by attribute across the whole catalog. With denormalised columns, one product might put Size in `option1` and another in `option2`, so a "Size = 50ml" facet query cannot be expressed as a single index-backed predicate. The normalised model makes every facet the same query shape.

**Constraint:** a variant's set of `VariantAttributeValue` rows must be unique within its product. Two variants of one product cannot both be "50ml / Red".

### 2.3 Categories

Exactly two levels: category and subcategory, modelled as a self-FK `parent` with a validation constraint enforcing `parent.parent is None`. No MPTT, no arbitrary nesting. Fields: `name`, `slug`, `parent`, `description`, `image`, `position`, `is_published`, `meta_title`, `meta_description`.

### 2.4 Brands

`Brand` — `name`, `slug`, `logo`, `is_published`. Filterable (§16) and searchable (§15).

### 2.5 Images

**`ProductImage`** — `product` FK, `image`, `alt_text`, `position`, `is_primary`.

On upload, generate and store three derivatives synchronously: `thumb` (200px), `card` (600px), `full` (1400px), all WebP with a JPEG fallback. Serve via `<picture>` with `srcset` and `loading="lazy"`.

Synchronous generation is a deliberate MVP choice: a merchant uploading a handful of images tolerates a two-second save; a broker and worker process to avoid it does not pay for itself. Logged as debt in `TODO.md` — revisit if bulk import (§31) makes it painful.

Variants may optionally reference one of the product's images (`ProductVariant.image` FK, nullable) so selecting "Red" swaps the gallery hero.

---

## 10. Inventory and stock reservation

### 10.1 The policy

**Available = `stock_quantity` − sum of active `StockReservation` quantities.**

| Event | Effect |
|-------|--------|
| Order created (status `Pending Confirmation`) | Create `StockReservation` per line, `expires_at = now + RESERVATION_TTL_HOURS` (default 24, configurable) |
| Merchant confirms order | Decrement `stock_quantity`, delete reservations |
| Merchant cancels a pending order | Delete reservations, no stock change |
| Reservation TTL elapses without confirmation | Sweeper deletes reservations, order moves to `Expired`, merchant notified in dashboard |
| Order cancelled/returned **after** confirmation | Increment `stock_quantity` back |
| Manual adjustment | Set `stock_quantity` directly, write `InventoryAdjustment` audit row |

**Why reservation rather than the two obvious alternatives.** Decrementing at order creation means every abandoned WhatsApp order locks inventory permanently — and abandonment will be high, because the order is created *before* any human contact. Decrementing at confirmation means two customers can both order the last unit and one gets an apology. Reservation with a TTL is the only option that neither leaks stock nor oversells.

### 10.2 Concurrency

Every stock check and reservation write happens inside a transaction with `SELECT ... FOR UPDATE` on the variant row. Checkout re-validates availability at submit time, not just at add-to-cart, and returns a specific per-line error if availability changed (§44).

### 10.3 Models

- **`StockReservation`** — `variant` FK, `order` FK, `quantity`, `expires_at` (indexed), `created_at`.
- **`InventoryAdjustment`** — `variant` FK, `delta`, `reason`, `actor` FK, `note`, `created_at`.

### 10.4 Sweeper

Management command `release_expired_reservations`, cron every 10 minutes, idempotent, logs a count. Must be safe to run concurrently with itself.

### 10.5 Merchant inventory view

Table across all variants: product, variant label, SKU, `stock_quantity`, reserved, available, low-stock flag, out-of-stock flag. Inline stock adjustment. Filters: low stock, out of stock, by category, by brand.

**Out of scope:** multiple warehouses, purchase orders, stock transfers, cost of goods.

---

## 15. Search

Search is the highest-risk feature in the spec and the one most likely to be judged by the merchant.

### 15.1 Behaviour

Must satisfy, at minimum, these cases against a product named "Afnan 9PM Eau de Parfum":

| Query | Must match |
|-------|-----------|
| `afnan 9pm` | ✅ |
| `9pm` | ✅ |
| `AFNAN` | ✅ |
| `afnn` (typo) | ✅ |
| `9PM afnan` (reordered) | ✅ |
| `EDP-9PM-100` (partial SKU) | ✅ |

Searchable fields: product name, brand name, SKU, category name, subcategory name, tags, filterable attribute values.

Provides: type-ahead suggestions (debounced ~200ms, HTMX), result count, empty-state handling with suggested categories.

### 15.2 Implementation

A denormalised `Product.search_text` column, rebuilt on save via a signal and by a `rebuild_search_index` management command. It concatenates name, brand, all variant SKUs, category, subcategory, tags, and attribute values.

Two Postgres indexes on that column:
- `GIN (search_text gin_trgm_ops)` for fuzzy and partial matching
- `GIN (to_tsvector('simple', search_text))` for ranked full-text

Ranking blends `ts_rank` with trigram `word_similarity`.

**Critical detail for the `9pm` case:** plain `similarity()` scores a 3-character query against a long product name very poorly, because the query contributes few trigrams relative to the target. Use **`word_similarity()`** (the `%>` operator), which scores the query against the best-matching *word extent* within the target rather than the whole string. Set `pg_trgm.word_similarity_threshold` explicitly in a migration; do not rely on the default. This single decision is the difference between `9pm` working and not working — verify it with a test before building anything on top.

An `ILIKE 'query%'` prefix scan runs as a fast path for suggestions.

### 15.3 Abstraction

All search goes through a `SearchBackend` protocol with a single `PostgresSearchBackend` implementation, selected by config. Meilisearch drops in later without touching view code. Do not build a second backend now.

---

## 16–17. Filtering and sorting

Filters: category, subcategory, brand, price range, availability, plus every `AttributeDefinition` marked `is_filterable`. Filters compose (AND across facets, OR within a facet). Facet counts shown next to each option. State lives in the query string so results are shareable and back-button-safe. Applied via HTMX partial swap — no full page reload, no client-side router.

Price and availability filters operate on **variants**, and a product matches if any of its active variants matches. Watch the join fan-out: use `EXISTS` subqueries rather than `JOIN` + `DISTINCT`, which will silently wreck pagination counts.

Mobile: filters in a bottom-sheet drawer with an apply button and an active-filter count badge.

Sorting: relevance (default on search), newest, price ascending, price descending, popularity (units sold), featured. Default sort configurable in store settings.

---

## 19. Cart

Server-side, session-keyed. `Cart` (session key, `created_at`, `updated_at`) and `CartItem` (cart FK, **variant FK**, quantity).

Server-side rather than `localStorage` for three reasons: stock can be validated authoritatively on every mutation, the cart survives a device switch within a session, and abandoned-cart recovery (§49) becomes possible without a rewrite.

Operations: add, increment, decrement, remove, clear. All HTMX partial updates to the cart badge and drawer — no page reload. Availability re-checked on every mutation with a specific message when it changes.

Displays subtotal, delivery charge (once a city is known), and total.

---

## 20–22. Checkout, WhatsApp handoff, order numbers

### 20. Checkout

Guest only. No account creation, no login, no password.

Collects: customer name, mobile number, WhatsApp number (defaulting to the mobile number with a "same as mobile" checkbox), email (optional), delivery address, city (select — drives delivery charge), postal code (optional), delivery instructions, order notes.

Phone validation: Pakistani mobile format, normalised to E.164 (`+92...`) on save, displayed in local format.

Order review before submit shows every line, subtotal, delivery, and total. One page, no multi-step wizard.

### 21. WhatsApp handoff

On submit, in one transaction: validate → re-check availability → create `Order` and `OrderItem` snapshots → create `StockReservation` rows → generate order number → commit. Only then redirect to WhatsApp. If the transaction fails, nothing is created and the customer sees a specific error.

The order exists in the merchant system **before** WhatsApp opens. The WhatsApp message is a courtesy notification, not the order channel. If the customer closes WhatsApp without sending, the merchant still sees the order.

**Message payload cap.** `wa.me/?text=` is a URL query parameter and long orders will truncate silently — the exact ceiling varies by browser and by the WhatsApp client, so treat it as unknown and measure. Build the message to a configured character budget (`WHATSAPP_MESSAGE_MAX_CHARS`, default conservative). When the itemised list would exceed it, render the first N lines then `…and X more items` followed by the tracking URL. **Verify the real limit empirically on Android Chrome, iOS Safari, and WhatsApp Web before finalising the default**, and record the measured values in `docs/whatsapp-limits.md`.

Message construction lives in `notifications/whatsapp/message_builder.py` behind a `NotificationChannel` protocol (§26). No view builds a WhatsApp string inline.

A visible fallback is always rendered on the confirmation page: the order number, a "copy order details" button, and a re-open-WhatsApp link — for when the redirect fails (§44).

### 22. Order numbers

Format: `ORD-{seq}-{rand}` — e.g. `ORD-10025-K7X`, where `seq` is a database sequence starting at 10000 and `rand` is 3 characters from an unambiguous alphabet (no `0`/`O`, no `1`/`I`/`l`).

The random suffix exists because §25 gates public order tracking on order number plus phone. A purely sequential number lets anyone walk the order space. Three characters is not cryptographic security — it is enough friction that the rate limiter (§25) becomes the real control rather than the last line of defence.

Readable aloud over a phone call. Unique. Indexed.

---

## 23–24. Order management

### Statuses

`Pending Confirmation` → `Confirmed` → `Processing` → `Ready to Dispatch` → `Dispatched` → `Out for Delivery` → `Delivered`

Terminal / exceptional: `Cancelled`, `Failed Delivery`, `Returned`, `Expired` (reservation lapsed — **new in v2**).

Transitions are validated against an explicit allowed-transition map in typed config. An invalid transition is a 4xx, not a silent no-op. Every transition writes an `OrderStatusEvent` (`from_status`, `to_status`, `actor`, `note`, `created_at`) which is both the merchant audit trail and the customer-facing timeline (§25).

### Order editing (new in v2)

While an order is `Pending Confirmation` or `Confirmed`, the merchant may: change a line quantity, remove a line, add a line, and override a line unit price (for a negotiated discount). Each edit adjusts reservations, recalculates totals, and writes an audit row capturing before and after values.

This is not a nice-to-have. WhatsApp commerce is a conversation — "make it three", "add the other one too", "give me a discount and I'll take both" — and without order editing the merchant will delete and re-create orders, destroying the analytics in §39.

Editing is blocked once the order is `Dispatched` or beyond.

### `Order` fields

Order number; customer FK; **snapshotted** customer name, phone, WhatsApp number, email; **snapshotted** delivery address, city, postal code, instructions; subtotal, delivery charge, discount, total (all `Decimal`); status; payment method, payment status, payment provider, transaction ID, payment reference, paid amount, payment date, refund amount, refund status (all nullable — §28); customer notes; merchant notes; tracking number; courier name; `created_at`; `updated_at`.

Address and customer details are snapshotted, not read live through the FK. The customer moving house must not rewrite where last month's order was delivered.

### `OrderItem` fields

`order` FK; `variant` FK (`on_delete=SET_NULL`, nullable); and immutable snapshots: `product_name`, `variant_label`, `sku`, `unit_price`, `quantity`, `line_total`.

The variant FK is a convenience for reporting. **Every displayed value comes from the snapshot.** Deleting a product must never corrupt order history, and repricing a product must never rewrite what a customer was charged.

---

## 25. Customer order tracking

Public page. Input: order number + mobile number. Both must match.

Displays: status, order date, line items, total, delivery status, tracking number and courier if present, and the status timeline from `OrderStatusEvent`.

Never exposes: email, full address, merchant notes, internal IDs, or any other order.

**Rate limiting is the actual security control here**, not the order-number format. Limit by IP: a small number of attempts per minute, with a longer lockout after repeated failures. Failed attempts are logged. Return an identical response for "order not found" and "phone does not match" — a distinguishable error confirms which order numbers exist.

---

## 26–28. Notifications, delivery, payments

### 26. Notifications

`NotificationChannel` protocol with a single `WhatsAppLinkChannel` implementation for MVP: the merchant clicks a button on the order detail page and a pre-composed `wa.me` link opens addressed to the customer. Templates per status (Confirmed, Processing, Dispatched, Out for Delivery, Delivered, Cancelled), editable in store settings.

Nothing is sent automatically. Every message is merchant-initiated. WhatsApp Business API, SMS, email, and push are later implementations of the same protocol.

### 27. Delivery

Three strategies behind a `DeliveryCalculator` protocol, selected in store settings:

1. **Flat rate** — one charge.
2. **Free-above threshold** — flat rate, waived above a subtotal.
3. **City-based** — a `DeliveryZone` table of city → charge, with a fallback charge for unlisted cities.

Strategies compose: city-based rates can carry a free-delivery threshold. Charge is calculated at checkout once the city is known and **snapshotted onto the order**.

Courier API integration is out of scope.

### 28. Payments

No online payment in MVP. `payment_method` defaults to `whatsapp_pending`.

Payment states, defined now and unused: `pending`, `initiated`, `successful`, `failed`, `cancelled`, `refunded`, `partially_refunded`.

The `payments` app exists in MVP as a `PaymentProvider` protocol, the state enum, and the order fields listed in §24 — nothing more. **No code outside `payments/` may assume WhatsApp is the payment mechanism.** Adding JazzCash, Easypaisa, COD, cards, or bank transfer must not require touching the order model.

---

## 29–33. Customers, bulk import, auth, audit

**§29 Customers.** Created implicitly at checkout, matched on normalised phone. Fields plus derived `total_orders`, `total_spent`, `last_order_at`. Profile shows order history. No customer login in MVP.

**§30** — see §10.5.

**§31 Bulk import.** CSV upload → validate → preview with per-row errors → confirm → import with a failed-row report downloadable as CSV. Must handle variants: either one row per variant with a shared product identifier column, or a product row plus variant rows. **Decide this format before writing the parser** — it is the whole design. P1 scope.

**§32 Auth.** Django auth. Two roles: `Owner` (full) and `Staff` (orders, inventory, customers — not store settings, not user management, not deletion). Django groups and permissions, no custom permission framework. Enforced by mixins on every admin view — never by hiding a nav link.

**§33 Audit trail.** `AuditLog` — `actor` FK, `action`, `object_type`, `object_id`, `object_repr`, `changes` (JSONB before/after), `ip_address`, `created_at`. Written for: product/variant/category/brand create-update-delete, inventory adjustment, order create, order status change, order edit, customer update, store settings change, user create-update-delete. Append-only; no update or delete path exists in application code.

---

## 34–38. Storefront quality requirements

**§34 SEO.** Per-product and per-category `meta_title` / `meta_description` with sensible generated defaults. Open Graph and Twitter Card tags. `Product` JSON-LD including `offers` with price, currency, and availability — driven off the default variant. `BreadcrumbList` JSON-LD. `sitemap.xml` via `django.contrib.sitemaps` covering products, categories, and static pages. `robots.txt`. Canonical URLs. Slugs are stable — changing a product name must not break an existing link, so slug changes are opt-in and old slugs 301-redirect.

**§35 Social sharing.** WhatsApp, Facebook, and copy-link on every PDP. Shared links must render title, image, and description correctly — verify against Facebook's sharing debugger and by sending a real WhatsApp message.

**§36 Performance.** Budgets, measured on a throttled mobile profile: LCP under 2.5s, CLS under 0.1, total JS under 100KB gzipped, no N+1 queries on any list view (asserted in tests with `assertNumQueries`). Every list view paginated. Images WebP with `srcset` and explicit dimensions to prevent layout shift. Aggressive HTTP caching on static assets and images.

**§37 Accessibility.** Keyboard navigable throughout. WCAG AA contrast. Alt text mandatory on product images (validation-enforced, falls back to product name). Labelled form fields. Focus states visible. Touch targets ≥ 44px. Error messages associated with their inputs via `aria-describedby`. Skip-to-content link.

**§38 Mobile.** Designed mobile-first, not scaled down. Compact header with prominent search. Bottom navigation. Two-column product grid. Sticky cart access. Large tap targets on quantity controls. Prominent WhatsApp order button. Minimal typing at checkout — city as a select, WhatsApp number defaulting to mobile.

---

## 39–41. Analytics, configuration, security

**§39 Analytics.** Total orders, total sales, orders by status, sales over time, top products by units and by revenue, average order value, low-stock list. Date filtering with presets. Computed with database aggregation, not Python loops. Product view counts are an async counter increment on the PDP (deliberately not a full events table — that is P2 if it is ever needed).

**§40 Configuration.** A singleton `StoreSettings` model: identity, contact, WhatsApp number, currency (PKR default), timezone (`Asia/Karachi` default), delivery strategy and rates, order settings including reservation TTL, notification templates, SEO defaults, social links. **No merchant-specific value is hard-coded anywhere.** Non-merchant config (secret key, database URL, storage credentials) lives in environment variables via `django-environ`.

**§41 Security.** Django's built-in CSRF, XSS escaping, and ORM parameterisation, all left on. Argon2 password hashing. Rate limiting on login, checkout, tracking, and search. File upload validation by content type and magic bytes, not extension — with a size cap and a filename sanitiser. `SECURE_*` settings enabled in production. `DEBUG=False` enforced. Admin views require authentication and authorisation by mixin, never by obscurity. Customer PII never appears in logs or error pages. Generic error pages in production.

---

## 42. Database

Indexes required at minimum: `product.slug`, `product.search_text` (both GIN variants), `variant.sku`, `variant.product`, `product.category`, `product.status`, `order.order_number`, `order.status`, `order.created_at`, `customer.phone`, `reservation.expires_at`, `auditlog.created_at`.

Every money column is `DecimalField(max_digits=12, decimal_places=2)`. No `FloatField` on any monetary or quantity field anywhere in the project.

---

## 44–46. Errors, empty states, loading

**§44 Errors.** Specific and actionable on the storefront: which product went out of stock and what the available quantity now is — not "an error occurred". Named cases: product unavailable, availability changed during checkout, no search results, checkout validation failure, order creation failure, WhatsApp redirect failure. Diagnostic detail for admin users. Custom 404 and 500 pages that keep the customer in the store.

**§45 Empty states.** Products, search results, cart, orders, customers, inventory alerts, filtered-to-nothing. Each names the next action.

**§46 Loading.** Skeleton loaders for product cards, PDP, search results, order lists, and dashboard widgets. HTMX indicators on every request. Never a blank screen. Never a layout shift when content arrives.

---

## 53. Testing (new in v2)

- pytest + pytest-django, factory-boy for fixtures. **No binary fixtures in git** — generate test images with Pillow at runtime.
- Coverage floor 80% on `catalog`, `inventory`, `orders`, `search`. UI-only code exempt.
- Mandatory test cases, not negotiable:
  - Stock reservation: create, confirm, expire, cancel, restore-on-return.
  - Concurrent checkout on the last unit — one succeeds, one fails cleanly.
  - Order item snapshot survives product deletion and product repricing.
  - Every search case in the §15.1 table, including `9pm`.
  - Filter composition with facet counts.
  - Every allowed and disallowed status transition.
  - Order editing adjusts reservations and totals correctly.
  - WhatsApp message truncation at the configured budget.
  - Delivery charge for each of the three strategies.
  - Permission enforcement: staff blocked from owner-only views.
  - `assertNumQueries` on product list, PDP, cart, and order list.

## 54. CI (new in v2)

GitHub Actions on every push and PR: ruff, mypy strict, pytest with coverage gate, `makemigrations --check --dry-run` (fails on model drift), and `manage.py check --deploy`. Full matrix green is a merge precondition.

## 55. Backup (new in v2)

Nightly `pg_dump` plus a media sync to off-box storage, 30-day retention. **A documented restore procedure, tested at least once before go-live.** Single-tenant means one Postgres holds the merchant's entire business — an untested backup is not a backup.

---

## 56. Scope phasing (new in v2)

**P0 — the merchant can sell.**
Scaffold, CI, settings. Auth. Store settings. Categories and brands. Products, variants, attributes, images. Inventory with reservations. Storefront: home, listing, PDP, search, filter, sort. Cart. Checkout. WhatsApp handoff. Order management with editing and status timeline. Public tracking. Delivery calculation. Responsive across breakpoints. SEO fundamentals.

**P1 — the merchant can operate at scale.**
Dashboard and analytics. Audit trail UI. CSV bulk import. Staff role. WhatsApp notification templates. Advanced empty and loading states. Performance pass against the §36 budgets. Accessibility audit.

**P2 — later.**
Coupons and discounts. Wishlists. Reviews. Customer accounts. Abandoned cart. Courier integration. Payment provider implementations. Meilisearch. Anything under §49.

**P0 is the release.** P1 and P2 do not gate go-live.

---

## 57. Development principles

- Build P0 first. Resist every P1 feature that presents itself as "quick".
- No multi-tenancy. No tenant abstraction. No `store_id`.
- No online payment code paths in MVP — only the protocol and the enum.
- Nothing outside `notifications/` and `payments/` knows WhatsApp exists.
- The consumer storefront is the priority surface. When admin polish and storefront polish compete, storefront wins.
- Search must be fast and correct. It is the feature the merchant will judge.
- Mobile-first, genuinely — not a scaled-down desktop layout.
- Reusable template partials and components. If a card is rendered twice, it is one partial.
- Loading, error, and empty states are part of the feature, not a follow-up.
- Code standards per the root `CLAUDE.md`. Non-negotiable.
- Debt goes in `TODO.md`. Never `# TODO` in shipped code.

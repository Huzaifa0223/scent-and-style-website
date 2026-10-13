# Noor integration

`noor/` connects the shop to **Noor**, the store's fragrance-consultant app (in-store tablets and
the public web app at `https://noor.scentandstyle.pk`). It reads the catalog, owns one table
(`KioskBackup`) and changes no behaviour of any other app.

## Endpoints

| URL | Auth | Purpose |
|---|---|---|
| `GET /api/noor/catalog.json` | none | `slug`, `price`, `inStock`, `url` per published product |
| `GET /api/noor/products.json` | none | full public product feed (name, brand, category, description, image, notes…) |
| `GET /api/kiosk/sync/ping/` | Bearer | `{"ok": true}` |
| `GET /api/kiosk/sync/catalog/` | Bearer | `slug`, `price`, `stockQty` per published product |
| `POST /api/kiosk/sync/backup/` | Bearer | store a tablet backup (JSON, ≤ 5 MiB, `"format": "scent-style-backup"`), keep newest 10 → `201 {"storedAt"}` |
| `GET /api/kiosk/sync/backup/latest/` | Bearer | newest stored body verbatim, or `404` |

Private endpoints: `Authorization: Bearer <SCENT_SYNC_TOKEN>`; missing/wrong → `401
{"error":"unauthorised"}`; ~30 requests/min/IP → `429`; HTTPS only outside `DEBUG`; CSRF-exempt.
Other errors: `400 invalid_json | invalid_format`, `413 payload_too_large`, `405`, `404 not_found`.

Public feeds send `Access-Control-Allow-Origin: https://noor.scentandstyle.pk`, `Vary: Origin`,
`Cache-Control: public, max-age=300`, and answer `OPTIONS` with the same plus `Allow: GET`.
Stock **counts** are never public — only the `inStock` boolean.

The private `/api/kiosk/sync/` endpoints send **no CORS headers** and do not answer preflights: the
only client is the native Android tablet app, so a browser page on another origin cannot use them
(an `OPTIONS` there is treated like any other request: 401 without the token, 405 with it).

`Product.slug` is exactly the `<slug>` in `/product/<slug>/` (the URL is built with
`reverse("storefront:product_detail", slug=product.slug)`); Noor can match on it. A product renamed
with a slug change appears under its **current** slug; the old one 301-redirects on the site.

## Configuration

| Variable | Required | Notes |
|---|---|---|
| `SCENT_SYNC_TOKEN` | for the private API | ≥ 32 chars. Generate with `python -c "import secrets; print(secrets.token_urlsafe(40))"`. Keep out of git. Unset/short ⇒ every private request is `401` (fails closed) and `manage.py check --deploy` warns `noor.W001`. |
| `NOOR_ORIGIN` | no | defaults to `https://noor.scentandstyle.pk` |

Absolute URLs use `StoreSettings.site_url` when set, else the request's own scheme/host.

## Field mapping (`noor/catalog.py::product_rows()`)

`Product` carries no price or stock — those live on `ProductVariant` — so each product is reduced
to one **representative variant**: the default active variant if it can be bought, otherwise the
first active variant that can (else the default, sold out). Price, `inStock` and `stockQty` all come
from that one variant, so a row never pairs one size's price with another size's count. A published
product with no active variant has no price and is omitted.

| Noor field | Source |
|---|---|
| `slug` | `Product.slug` |
| `name` | `Product.name` |
| `brand` | `Product.brand.name` (`""` if none) |
| `category` | `Product.category.name` |
| `price` | representative `ProductVariant.price`, whole rupees, half-up |
| `inStock` | representative variant `available_quantity > 0` |
| `stockQty` | representative variant `available_quantity` = `stock_quantity` − live reservations (≥ 0) |
| `description` | `Product.short_description`, else `description` minus legacy "Top notes:" lines |
| `image` | primary `ProductImage.card_jpeg` (else original), absolute URL; `""` if none |
| `url` | `/product/<slug>/` on the site base URL |
| `notes.top/heart/base` | `Product.top_notes/heart_notes/base_notes` (split on `, ; newline`), else labelled lines in `description`; `[]` otherwise |

`stockQty` deliberately subtracts units held by pending web orders so a tablet cannot sell stock
already promised online. To send raw on-hand counts instead, change `_available()` in
`noor/catalog.py` (one place).

## Website changes (templates only)

- `templates/noor/_ask_noor_fab.html`, included by `storefront/base.html` in the `noor_fab` block:
  a gold "Ask Noor" pill, bottom-right, stacked above the WhatsApp button, `target="_blank"
  rel="noopener"`, `z-40` (under the cart drawer). `checkout.html` and `order_confirmation.html`
  override the block to nothing. Account/portal pages extend the root `base.html` and never show it.
- `product_detail.html`: "Find similar with Noor" under Add to cart, secondary-button styling,
  links to `…/#/p/<slug>`.
- Only utility classes already present in the built CSS are used — no Tailwind rebuild needed.

## Deploying to the live VPS

The shop runs from `/root/scent-and-style-website`, gunicorn on `127.0.0.1:8000` behind Caddy
(`scentandstyle.service`). A second, unrelated gunicorn is on `127.0.0.1:8001` — never touch or
reload it. Prefer low-traffic hours. Only schema change: the new `noor_kioskbackup` table.

```bash
cd /root/scent-and-style-website
git status --short                       # must be clean; commit live edits as "snapshot before noor"
PREV=$(git rev-parse HEAD); echo "$PREV" # note this for rollback

# 1. Back up and VERIFY (PostgreSQL; DB name is in DATABASES / DATABASE_URL)
TS=$(date +%Y%m%d-%H%M%S); mkdir -p /root/backups
pg_dump -Fc -f /root/backups/shop-$TS.dump <db>
pg_restore --list /root/backups/shop-$TS.dump | head      # must print a TOC
ls -l /root/backups/shop-$TS.dump

# 2. Get the code (branch noor-integration), then set the token in the SERVER's .env
git fetch && git checkout noor-integration
python -c "import secrets; print(secrets.token_urlsafe(40))"   # paste into .env as SCENT_SYNC_TOKEN=…

# 3. Verify before going live (no new errors; only the noor migration)
python manage.py check --deploy
python manage.py makemigrations --check --dry-run          # "No changes detected"
# The test suite is pytest (not `manage.py test`) and needs dev dependencies plus a database role
# that can create a test DB — run `pytest --create-db` on a dev machine/CI before deploying; the
# live runtime role (deploy/create_app_role.sql) is least-privilege and cannot.

# 4. Go live
python manage.py migrate noor
ss -tlnp | grep 8000                                       # confirm the shop's unit/master pid
systemctl reload scentandstyle.service                     # or: kill -HUP <shop master pid>
tail -n 50 /var/log/…/gunicorn error log

# 5. Smoke test (expect 200 ×4, 200 ×2, 401 ×2)
for u in / /products/ /cart/ /checkout/ /api/noor/catalog.json /api/noor/products.json \
         /api/kiosk/sync/ping/ /api/kiosk/sync/catalog/; do
  curl -s -o /dev/null -w "%{http_code} $u\n" "https://scentandstyle.pk$u"; done
```

`/checkout/` redirects (302) with an empty cart — that is expected; load it with an item in the
cart in a browser. Then confirm with the token (do not paste it into shared logs):
`curl -s -H "Authorization: Bearer $SCENT_SYNC_TOKEN" https://scentandstyle.pk/api/kiosk/sync/ping/`.

### Rollback (any 500 or failed check)

```bash
git checkout "$PREV"
python manage.py migrate noor zero        # drops only noor_kioskbackup
systemctl reload scentandstyle.service
```

Restore the database dump only if existing data was harmed (it should not be: the migration only
adds a table).

## Known limits

- Rate-limit rows (`core.RateLimitAttempt`, scope `kiosk_sync`) accumulate like the existing search
  scope's do; there is no purge job in this project yet.

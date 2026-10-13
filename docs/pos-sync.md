# POS ⇄ website stock sync

The store **POS is the master of physical stock**; online orders ship from the same shelves. The
`possync` app lets the POS push stock snapshots to the website and pull the web orders it still has
to record. **Prices are never changed automatically** — the POS price is stored for review only.

Not deployed by this branch (`pos-sync`). See "Deploying" below.

## The stock formula

```text
available_quantity = onHand
                     − (units in web orders awaiting POS acknowledgement)
                     − (units in active reservations)
```

Implemented as: on each snapshot, per mapped variant (under the variant's row lock),

```text
stock_quantity = max(onHand − unacknowledged_units, 0)
```

and the existing `with_available_quantity()` already subtracts active reservations
(`available = stock_quantity − reserved`). So the number customers see is exactly the formula above.

**Awaiting acknowledgement** means a web order that is

- in status Confirmed, Processing, Ready to Dispatch, Dispatched, Out for Delivery, Delivered or
  Failed Delivery (the shop has already taken the stock out), **and**
- has no POS acknowledgement, **and**
- was confirmed **on or after the cut-off** (`PosSyncState.orders_since`).

Pending Confirmation orders are covered by their reservation; Cancelled / Returned / Expired orders
gave the stock back. Because the sync sets the number absolutely every time, it self-heals:
confirming an order decrements the same figure the next snapshot would compute, and acknowledging
one needs no recompute (the POS on-hand falls by the units that stop being subtracted).

### The cut-off (read this before go-live)

Historical confirmed/delivered orders will never be acknowledged. Without a cut-off, the very first
snapshot would subtract all of them from on-hand and zero out stock. `orders_since` defaults to the
moment POS sync is first used and is shown (and editable) at the top of **Portal → POS mapping**.
Orders confirmed before it are treated as already reflected in the POS count. Orders that are
in flight at go-live must be recorded in the POS by hand; move the cut-off earlier only if you want
them counted until acknowledged.

### Other behaviour

- A snapshot **older than the last applied one is ignored** (`"stale": true`, nothing changes), so a
  late retry cannot roll stock back. Same timestamp is re-applied (idempotent). A `snapshotAt` more
  than 1 hour in the future is refused (it would otherwise block every later sync).
  Snapshots are serialised with a Postgres advisory lock.
- Negative `onHand` is accepted and clamped to 0 (and counted as oversold if orders are waiting).
- A stock **movement** (`InventoryAdjustment`, reason *Manual adjustment*, note `POS sync: <n> on
  hand (snapshot …)`) is written only when the number actually changes. (A dedicated "POS sync"
  reason would need an `inventory` migration; the note carries it instead.)
- Unmapped SKUs are upserted into `PosProduct` (`last_seen_at`, price) and listed in the response —
  never matched by guesswork. SKUs marked "not sold online" are not listed as unmapped.
- Hand edits to `stock_quantity` (Inventory page, product form) on a **mapped** variant are
  overwritten by the next snapshot — the POS is the master.

## API

Base `/api/pos/sync/`. `Authorization: Bearer <SCENT_POS_TOKEN>` (≥ 32 chars, **different** from
`SCENT_SYNC_TOKEN`; the two APIs reject each other's secret). Same pipeline as `/api/kiosk/sync/`:
HTTPS only outside DEBUG, ~30 requests/min/IP in its own `pos_sync` bucket, CSRF-exempt, **no CORS
headers**, `Cache-Control: private, no-store`. Unset/short token ⇒ every request `401`
(`manage.py check --deploy` warns `possync.W001`). Errors are `{"error": "<code>"}`.

| Request | Response |
|---|---|
| `GET ping/` | `200 {"ok": true}` |
| `POST stock/` `{"snapshotAt": "<ISO>", "items": [{"sku": "…", "onHand": 7, "priceRs": 12500}]}` | `200 {"applied": n, "unchanged": n, "unmapped": ["sku"], "oversold": [{"sku": "…", "short": n}]}` (+ `"stale": true` when ignored) |
| `GET web-orders/` | `200 {"orders": [{"id", "number", "paidAt", "lines": [{"posSku","variantSku","name","qty","unitPriceRs"}], "unmappedLines": [...]}]}` — **no names, phones or addresses**. `paidAt` is when the order was confirmed (there is no online payment). Oldest first. |
| `POST web-orders/<id>/ack/` `{"posSaleNumber": "S-2026-00123"}` | `200 {"ok": true, "orderId", "posSaleNumber", "alreadyAcked"}`; same number again `200`; different number `409 already_acked_differently`; unknown id `404`; order not in a status the POS should record `409 order_not_awaiting_ack` |

`POST stock/` validates the whole request before applying anything: `400` with `invalid_json`,
`invalid_snapshot_at`, `snapshot_in_future`, `invalid_items`, or per item (`index` = position)
`invalid_item`, `invalid_sku`, `invalid_on_hand`, `invalid_price`, `duplicate_sku`. Body cap 5 MiB
(`413 payload_too_large`). `onHand` must be an integer (`7` or `7.0`); `priceRs` optional, ≥ 0.

`oversold` appears when units in unacknowledged web orders exceed `onHand`; it is also shown in the
portal and stored with the last sync result.

## Mapping workflow (Portal → POS mapping, Owner only)

Requires the `possync.manage_pos_mapping` permission, which Staff do not have (403).

1. **Upload** the POS product CSV `sku,brand,name,category,price_rs,active` (UTF-8, case-insensitive
   headers, `Rs. 12,500` tolerated). Valid rows are upserted and bad rows reported by line number;
   re-uploading never changes "not sold online" or last-seen.
2. For each **unmapped** POS product the page shows the **top 3 suggestions** with a score
   (brand match after normalising spellings such as *Al Majeed* ↔ *Al Majed*; name-token overlap;
   ml size — a different size is penalised hard). **Nothing is confirmed automatically.** Click
   *Map* to confirm, or *Not sold online* (watches, sunglasses…).
3. Filter unmapped / mapped / not online; search; **Export mapping (CSV)**.
4. **Price differences** lists mapped variants whose POS price ≠ website price, for a human to fix
   on the product page. Nothing writes `price`.
5. Every change (map, unmap, not-online, CSV import, cut-off change) is audited with who/when
   (*Recent changes*). A variant maps to at most one POS SKU and vice-versa (DB unique constraint).

## Data model (all additive)

| Where | What |
|---|---|
| `catalog.ProductVariant` | `pos_sku` (nullable, unique when set, never `""`), `pos_price` (nullable) — migration `catalog.0013` |
| `possync.PosProduct` | every POS product incl. not-online ones |
| `possync.PosMappingEvent` | append-only audit trail |
| `possync.PosSyncState` | singleton: cut-off, last snapshot time, last result |
| `possync.PosOrderAck` | one row per acknowledged order (a separate table; `orders_order` is untouched) |

## Deploying (runbook — not run from this repo's session)

Same safety rules as `docs/noor-integration.md`: low-traffic hours, verified backup first, only the
shop's gunicorn is reloaded (never the one on 8001), never print a token or `.env`. On the VPS
`manage.py` defaults to dev settings — set `DJANGO_SETTINGS_MODULE=config.settings.prod`.

```bash
cd /root/scent-and-style-website && git status --short          # clean
PREV=$(git rev-parse HEAD); echo "$PREV"
pg_dump -Fc -f /root/backups/shop-$(date +%Y%m%d-%H%M%S).dump <db>   # then pg_restore --list | head
git fetch && git checkout pos-sync        # or main once merged
# add SCENT_POS_TOKEN (>= 32 chars, different from SCENT_SYNC_TOKEN) to the service's env file
export DJANGO_SETTINGS_MODULE=config.settings.prod
python manage.py check --deploy            # possync.W001 must NOT appear
python manage.py makemigrations --check --dry-run
python manage.py showmigrations catalog possync     # catalog 0013 and possync 0001 unapplied
python manage.py migrate catalog && python manage.py migrate possync
# Tailwind: the portal pages add a few utility classes — rebuild CSS + collectstatic if the build
# is done on the server (./tools/tailwindcss -c tailwind.config.js -i static/css/input.css \
#   -o static/css/app.css --minify), otherwise they render unstyled (functionally fine).
systemctl reload scentandstyle.service     # never restart; never touch 127.0.0.1:8001
```

Smoke test: `/`, `/products/`, `/cart/` → 200; `/api/pos/sync/ping/` → 401 without the token and 200
with it; `/admin-portal/pos/` → redirects to login anonymously. Then: upload the CSV, review the
cut-off, map products, and only then point the POS at `/api/pos/sync/`.

### Rollback (order matters)

Undo the **database first, while the new code is still checked out** (the migrations live in it):

```bash
export DJANGO_SETTINGS_MODULE=config.settings.prod
python manage.py migrate possync zero                      # drops the possync tables
python manage.py migrate catalog 0012_product_is_trending  # drops pos_sku / pos_price
git checkout "$PREV"
systemctl reload scentandstyle.service
```

Restore the dump only if existing data was harmed (the migrations only add tables/columns).

## Known limits / things to watch

- A web order the POS never records stays subtracted until acknowledged (or until it falls before
  the cut-off). If staff also correct stock by a stock-take for the same unit, it would be counted
  twice; raising the cut-off is the escape hatch.
- The mapping page computes suggestions in Python over every unmapped variant, per page of 50 POS
  products. Fine for a catalog of hundreds/low thousands.
- `RateLimitAttempt` rows (scope `pos_sync`) accumulate one per request, like the other scopes.

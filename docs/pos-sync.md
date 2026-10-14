# POS ⇄ website stock sync

The store **POS is the master of physical stock**; online orders ship from the same shelves. The
`possync` app lets the POS push stock snapshots to the website and pull the web orders it still has
to record. **Prices are never changed automatically** — the POS price is stored for review only.

Merged to `main`, **not deployed**. See "Deploying" below.

## Mode: read-only (default) or subtracting web orders

`POS_SYNC_SUBTRACT_WEB_ORDERS` (env, boolean, **default `false`**) selects what a snapshot does. The
current mode is shown at the top of **Portal → POS mapping**.

| Mode | When to use | `stock_quantity` set to | "oversold" |
|---|---|---|---|
| **Read-only** (`false`, default) | Web orders are **not** recorded in the POS — staff ring them up at the till, so the POS on-hand already drops | `max(onHand, 0)` | never computed |
| **Subtracting** (`true`) | Web orders are recorded in the POS and acknowledged through the API | `max(onHand − unacknowledged web-order units, 0)` | when waiting orders exceed `onHand` |

In **both** modes active reservations are still subtracted by the existing availability logic
(`available = stock_quantity − reserved`), prices are recorded but never applied, and
`GET web-orders/`, `POST web-orders/<id>/ack/` and "Mark as recorded" keep working — in read-only
mode they are harmless (they change no stock). The portal's *Web orders awaiting the POS* page says
"Read-only mode — web orders are not subtracted". Switching the mode takes effect at the next
snapshot; set it in the service's env file and send the service a HUP (see Deploying).

## The stock formula

Subtracting mode (read-only is the same with the web-order term fixed at zero):

```text
available_quantity = onHand
                     − (units in web orders awaiting POS acknowledgement)
                     − (units in active reservations)
```

Implemented as: on each snapshot, per mapped variant (under the variant's row lock),

```text
stock_quantity = max(onHand − unacknowledged_units, 0)        # read-only: max(onHand, 0)
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

### The cut-off (subtracting mode only — read this before turning it on)

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
  overwritten by the next snapshot — the POS is the master (the forms warn about it).

## API

Base `/api/pos/sync/`. `Authorization: Bearer <SCENT_POS_TOKEN>` (≥ 32 chars, **different** from
`SCENT_SYNC_TOKEN`; the two APIs reject each other's secret). Same pipeline as `/api/kiosk/sync/`:
HTTPS only outside DEBUG, ~30 requests/min/IP in its own `pos_sync` bucket, CSRF-exempt, **no CORS
headers**, `Cache-Control: private, no-store`. Unset/short token ⇒ every request `401`
(`manage.py check --deploy` warns `possync.W001`). Errors are `{"error": "<code>"}`.

| Request | Response |
|---|---|
| `GET ping/` | `200 {"ok": true}` |
| `POST stock/` `{"snapshotAt": "<ISO>", "items": [{"sku": "…", "onHand": 7, "priceRs": 12500}]}` | `200 {"applied": n, "unchanged": n, "unmapped": ["sku"], "oversold": [{"sku": "…", "short": n}], "skipped": [{"index": n, "sku": "…"\|null, "reason": "…"}]}` (+ `"stale": true` when ignored) |
| `GET web-orders/` | `200 {"orders": [{"id", "number", "paidAt", "lines": [{"posSku","variantSku","name","qty","unitPriceRs"}], "unmappedLines": [...]}]}` — **no names, phones or addresses**. `paidAt` is when the order was confirmed (there is no online payment). Oldest first. |
| `POST web-orders/<id>/ack/` `{"posSaleNumber": "S-2026-00123"}` | `200 {"ok": true, "orderId", "posSaleNumber", "alreadyAcked"}`; same number again `200`; different number `409 already_acked_differently`; unknown id `404`; order not in a status the POS should record `409 order_not_awaiting_ack` |

**Bad items are skipped, not fatal.** An item with an empty/missing SKU (`empty_sku`), an over-long
SKU (`sku_too_long`), a repeated SKU (`duplicate_sku` — the first occurrence is applied, later ones
skipped), an unusable count (`invalid_on_hand`), an unusable price (`invalid_price`) or that is not
an object (`invalid_item`) is left out, listed in `skipped` with its `index`, and every other item is
applied. Only a **malformed body** is a `400` and applies nothing: `invalid_json`,
`invalid_snapshot_at`, `snapshot_in_future`, `invalid_items`. Body cap 5 MiB (`413
payload_too_large`). `onHand` must be an integer (`7` or `7.0`); `priceRs` optional, ≥ 0. The last
sync's `skipped` list is kept and shown in the portal.

`oversold` appears when units in unacknowledged web orders exceed `onHand`; it is also shown in the
portal and stored with the last sync result.

## Mapping workflow (Portal → POS mapping, Owner only)

Requires the `possync.manage_pos_mapping` permission, which Staff do not have (403).

1. **Upload** the POS product CSV `sku,brand,name,category,price_rs,active` (UTF-8, case-insensitive
   headers, `Rs. 12,500` tolerated). Valid rows are upserted and bad rows reported by line number;
   re-uploading never changes "not sold online" or last-seen.
   The page opens with a **"Do it in this order"** panel: 1 upload, 2 *Hide watches, sunglasses and
   accessories* (one list, all ticked, you confirm), 3 *Confirm the clear matches* (the bulk review:
   one candidate at 0.90+, a **Size** column, rows with an unusual POS size marked *Check size*,
   nothing pre-ticked), 4 decide the rest one by one, 5 price differences. Tick boxes and bulk
   buttons exist only on the **Unmapped** list.
2. For each **unmapped** POS product the page shows the **top 3 suggestions** with a score
   (brand match after normalising spellings such as *Al Majeed* ↔ *Al Majed*; name-token overlap;
   ml size — a different size is penalised hard). **Nothing is confirmed automatically.** Click
   *Map* to confirm, or *Not sold online* (watches, sunglasses…).
3. Filter unmapped / mapped / not online; search; **Export mapping (CSV)**.
4. **Price differences** lists mapped variants whose POS price ≠ website price, for a human to fix
   on the product page. Nothing writes `price`.
5. Every change (map, unmap, not-online, CSV import, cut-off change, mark-recorded) is audited with
   who/when (*Recent changes*). A variant maps to at most one POS SKU and vice-versa (DB unique
   constraint).
6. **Web orders awaiting the POS** (`/admin-portal/pos/orders/`, Owner only) lists the orders still
   being subtracted. For one the POS will **never** record (e.g. a stock-take already reflects it),
   **Mark as recorded** takes it out of the awaiting-ack count. A reason (5–400 characters) is
   mandatory and is audited with your name. The order disappears from `GET web-orders/` at once; its
   units stop being subtracted at the **next stock snapshot**. A manual mark is provisional: if the
   POS later acknowledges the same order, its real sale number replaces the mark (history kept).
7. The Inventory page and the product edit form show **"POS updates will overwrite this"** beside the
   stock field of any POS-mapped variant (and saving one from Inventory says so too).

## Data model (all additive)

| Where | What |
|---|---|
| `catalog.ProductVariant` | `pos_sku` (nullable, unique when set, never `""`), `pos_price` (nullable) — migration `catalog.0013` |
| `possync.PosProduct` | every POS product incl. not-online ones |
| `possync.PosMappingEvent` | append-only audit trail |
| `possync.PosSyncState` | singleton: cut-off, last snapshot time, last result |
| `possync.PosOrderAck` | one row per acknowledged order — by the POS (`source=pos`) or by hand (`source=manual`, with `reason` and `marked_by`); a separate table, `orders_order` is untouched |

Migrations: `catalog.0013`, `possync.0001`, `possync.0002`.

## Deploying (runbook — not run from this repo's session)

Same safety rules as `docs/noor-integration.md`: low-traffic hours, verified backup first, only the
shop's gunicorn is reloaded (never the one on 8001), never print a token or `.env`. On the VPS
`manage.py` defaults to dev settings — set `DJANGO_SETTINGS_MODULE=config.settings.prod`.

```bash
cd /root/scent-and-style-website && git status --short          # clean
PREV=$(git rev-parse HEAD); echo "$PREV"
pg_dump -Fc -f /root/backups/shop-$(date +%Y%m%d-%H%M%S).dump <db>   # then pg_restore --list | head
git fetch && git checkout pos-sync        # or main once merged
# add SCENT_POS_TOKEN (>= 32 chars, different from SCENT_SYNC_TOKEN) to the service's env file;
# leave POS_SYNC_SUBTRACT_WEB_ORDERS unset (= false, read-only) for the first go-live
export DJANGO_SETTINGS_MODULE=config.settings.prod
python manage.py check --deploy            # possync.W001 must NOT appear
python manage.py makemigrations --check --dry-run
python manage.py showmigrations catalog possync     # catalog 0013 and possync 0001 unapplied
python manage.py migrate catalog && python manage.py migrate possync   # catalog 0013, possync 0001+0002
# Tailwind: the portal pages add a few utility classes — rebuild CSS + collectstatic if the build
# is done on the server (./tools/tailwindcss -c tailwind.config.js -i static/css/input.css \
#   -o static/css/app.css --minify), otherwise they render unstyled (functionally fine).
# This service has no ExecReload, so `systemctl reload` fails. Gracefully reload gunicorn's master
# with a HUP instead (never `restart`; never touch the gunicorn on 127.0.0.1:8001):
kill -HUP $(systemctl show -p MainPID --value scentandstyle.service)
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
kill -HUP $(systemctl show -p MainPID --value scentandstyle.service)   # no ExecReload: not `systemctl reload`
```

Restore the dump only if existing data was harmed (the migrations only add tables/columns).

## Known limits / things to watch

- In read-only mode the cut-off, acknowledgements and *Mark as recorded* have no effect on stock;
  they only matter if you switch to subtracting mode.

- A web order the POS never records stays subtracted until acknowledged, marked recorded by hand,
  or it falls before the cut-off. If staff also correct stock by a stock-take for the same unit it
  would otherwise be counted twice — that is what *Mark as recorded* is for.
- The mapping page computes suggestions in Python over every unmapped variant, per page of 50 POS
  products. Fine for a catalog of hundreds/low thousands.
- `RateLimitAttempt` rows (scope `pos_sync`) accumulate one per request, like the other scopes.

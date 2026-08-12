# Stage 3 checkpoint report

Paused mid-stage at your request, before starting product create/edit and the variant formset.
Scope covered: `accounts` app, portal shell, product list + N+1 test, Category/Brand/Attribute
CRUD, and the design system. For pasting into a review conversation, not a changelog.

## Done

- `029f20b` — fix(catalog): `ProductVariant.delete()` now promotes the next variant by position
  when the deleted row was the default (migration 0003's trigger only covers INSERT/UPDATE).
  `create_product()`'s docstring rewritten to state it's for single-default-variant callers only.
- `e419e76` — feat(accounts,portal): login/logout, `PortalPermissionRequiredMixin`, seeded "Staff"
  Group (migration + `post_migrate` backstop), `ProductListView`, Category/Brand/Attribute CRUD.
  Vendors SortableJS 1.15.6. Adds accounts/portal coverage floors to CI.
- `9a5a15e` — feat(design): Tailwind theme tokens, self-hosted IBM Plex Sans/Mono, `docs/design.md`
  with verified contrast ratios. Reworks the four pre-existing templates onto the new tokens.
- `89958a5` — docs: Stage 3 checkpoint notes in `specs/state.md`.

## Corrections

1. **Staff group as a real data migration, not a permissionless dummy.** Done — migration
   0001 + `create_permissions()` call (permissions don't exist yet mid-migration on a fresh DB) +
   a `post_migrate` signal backstop in `apps.py` (a `flush` — which `transaction=True` test
   teardown runs — wipes migration-inserted data; only signal-driven data survives it). Took three
   attempts to get the backstop actually firing; see "second opinion" section below.
2. **`create_product()` docstring vs. formset reality.** Fixed by *not* routing the formset
   through the service — docstring now says explicitly it's for single-variant callers, and
   multi-variant flows (the not-yet-built formset, Stage 16's CSV import) create the Product row
   and their own variants together, directly.
3. **Deferred trigger doesn't fire on DELETE.** Fixed — chose to mirror `ProductImage`'s
   promote-on-delete rather than document zero-default as permitted, since a product silently
   losing its default seemed like the worse default behavior. Tested.
4. **Vendor SortableJS.** Done, pinned 1.15.6, matching the HTMX/Alpine pattern (setup scripts +
   CI). Not yet wired into any template — no drag-reorder UI exists yet, since images weren't
   built this pass.
5. **`paginate_by` for the merchant, not the test.** Set to 25 with the reasoning written in the
   code comment; confirmed it still sits strictly between the gate's 5-and-50 fixture counts.

Didn't fit cleanly: none of the five required deviating from what you asked — the one place I
initially got it wrong on my own (before you corrected it) was assuming gate 4 could be satisfied
with a portal-native store-settings page; you redirected that to `/django-admin/`, which is also
just more consistent with the Stage 1 log's existing decision.

## Gate status

| Gate | Status |
|---|---|
| 1. 3-variant/2-attribute product, publish | Not provable — needs the formset (not built) |
| 2. Last-variant-delete refused with a message | Not provable at the portal level yet — the DB invariant is tested (Stage 2), the formset-level UX message isn't built |
| 3. Image reorder persists | Not provable — image management not built |
| 4. Staff blocked (403) from store settings/user management | **Provable now** — 6 tests, `portal/tests/test_permissions.py`, against `/django-admin/` |
| 5. `assertNumQueries` flat 5→50 | **Provable now** — see below |
| 6. Quality gate green, 80% coverage on `portal` | **Provable now** — see below |

Quality gate, actual numbers: `ruff check` — all checks passed. `ruff format --check` — 81 files
already formatted. `mypy .` — no issues found in 74 source files. `makemigrations --check
--dry-run` — no changes detected. `pytest` — 137 passed. Coverage: `portal` 98% (floor 80%),
`accounts` 100%, `catalog` 95% (floor 85%). `manage.py check --deploy` clean under prod settings.

## N+1 result (gate 5)

8 queries at 5 fixtures, 8 queries at 50 fixtures — flat. Measured with
`CaptureQueriesContext`, not a hardcoded assertion, after a warm-up request (first-ever access to
the DB-backed cache/session costs extra one-time queries that would otherwise look like an N+1
between the two measurements). `paginate_by=25` means page 1 shows all 5 fixtures in the first run
and a full 25 in the second, so this genuinely exercises N+1 risk rather than trivially passing.

## Decisions I made alone

- **Gate 4's "store settings and user management" targets `/django-admin/`, not a new portal
  view** (you later confirmed this). Reasoning: `roadmap.md` line 473 schedules "staff role and
  granular permissions" as Stage 17, not Stage 3; no roadmap stage before then builds a portal-
  native settings/user page; Stage 1's log already established `/django-admin/` as that surface.
- **"Staff" group scoped to catalog view/add/change only**, not the fuller orders/inventory/
  customers scope from requirements §32 — those apps have no portal views yet. You confirmed this
  reading explicitly in your corrections.
- **Owner = Django superuser**, no "Owner" Group row — `is_superuser` already bypasses permission
  checks, and requirements §32 calls Owner "full," so a second mechanism seemed redundant.
- **`accounts/models.py` exists, empty**, purely because Django skips `post_migrate` for any app
  with no models module — a real trap I only found by testing, not by reading docs first.
- Search box on the product list matches name OR SKU via `Exists()`, not a join — CLAUDE.md's
  variant-fan-out trap applies to search exactly like it does to filtering.

## Design system

Tokens in `tailwind.config.js`, full rationale and every contrast ratio in `docs/design.md`.
Summary: `ink`/`paper`/`surface` (near-black on near-white, not the cream-background default),
`accent` a deep wine `#7A2130` (not the terracotta-on-cream or neon-on-black defaults the skill
warns about), semantic `success`/`warning`/`danger` pairs, `border-subtle` (decorative) vs.
`border-interactive` (form/button outlines, held to the 3:1 UI-component bar). Typeface: **IBM
Plex Sans** for UI/prose, **IBM Plex Mono** for every number (price, SKU, quantity, position) —
self-hosted, OFL-licensed, chosen because the family's real monospace sibling makes a genuine
"data gets its own register" signature rather than an arbitrary aesthetic pick. Every pairing
actually used for text or a UI boundary was computed (sRGB relative luminance), not eyeballed —
17 text pairings clear 4.5:1, border-interactive and the focus ring clear 3:1. `min-h-11` (44px,
confirmed against the compiled CSS) is the recorded button/touch-target minimum every later
control inherits. No auto-dismissing messages — an accessibility regression I introduced and then
removed on your correction; messages now persist with an explicit dismiss control and
`role="status" aria-live="polite"`.

## Design points I'd want a second opinion on

- **The Staff-group `post_migrate` resync reverts manual permission edits** (recorded as an open
  question in `state.md`). It's the right behavior for Stage 3 (nobody has a reason to hand-edit
  the group yet) but it's a real footgun if anyone touches `/django-admin/auth/group/` before
  Stage 17 replaces this mechanism. Worth deciding now whether that's acceptable through Stage 17,
  or whether the sync should become additive-only sooner.
- **`accounts/permissions.py` is imported by a migration.** Migrations conventionally avoid
  depending on application code that can change shape. I judged this safe because the shared
  function only calls `.filter()`/`.exclude()` against stable Django framework fields, not this
  project's own models — but it's a first for this codebase's migrations, and I'd rather you saw
  it explicitly than found it later.
- **The three-attempt path to the working `post_migrate` fix** (migration timing → flush wipes
  non-signal data → `models_module=None` silently skips the signal) says something about how easy
  this class of bug is to half-fix and declare done. I've written the full chain into `state.md`
  for Stage 4/17, but if there's a cleaner mechanism than "empty `models.py` as a sentinel," I'd
  take it.
- **Badge/button styling lives in two small template partials** (`_badge.html`,
  `_button_primary.html`) rather than a more general component system. Reasonable for six call
  sites; if the portal grows much past what's here, that pattern may need revisiting before it's
  copy-pasted somewhere it shouldn't be.

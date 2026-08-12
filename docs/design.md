# Design system

Established in Stage 3 for the merchant portal; Stage 6's storefront inherits the same tokens
(§colour/type below) and is free to diverge in layout and voice, per requirements §1's split
between the two interfaces — but not in the underlying palette or typefaces, which stay one
system project-wide.

All tokens live in `tailwind.config.js` under `theme.extend`. This file is the rationale; that
file is the source of truth. If they disagree, the config is right and this file is stale — fix
it.

---

## Why these choices, not the defaults

Three looks currently dominate AI-generated interfaces: warm cream background with a high-contrast
serif and a terracotta accent; near-black background with a single neon accent; broadsheet-style
hairlines with zero border-radius. All three are legitimate for *some* brief — none of them are
this one, chosen for its own sake rather than picked for this brief.

This brief: a single merchant's back-office, used by one or two people for hours at a stretch,
doing repetitive data-entry-shaped work (scan a product table, edit a price, check a status). The
job of these screens is legibility and speed, not persuasion. So:

- **Not cream+terracotta.** Background is near-white, not a strong cream. No serif anywhere — the
  portal is UI, not editorial.
- **Not near-black+neon.** The one dark surface (the sidebar) is a normal, restrained admin-UI
  convention, not a whole-page treatment, and the accent is a deep wine, not an acid brights.
- **Not pure broadsheet.** Hairlines and density are genuinely appropriate for a data tool and
  used throughout, but a small consistent border-radius (4–10px) keeps it reading as considered
  software rather than a newspaper pastiche, and there's no multi-column article typesetting
  anywhere (nothing here is prose).

**The one deliberate identity choice:** IBM Plex Mono for every number — price, SKU, quantity,
position, timestamp. Prose and UI chrome stay in Plex Sans; anything a merchant needs to compare
or scan precisely renders in the monospace face instead. That's a real point of view (most admin
tools don't bother), it's cheap (one extra self-hosted font file), and it directly serves the
brief: a merchant scanning a price column for the outlier benefits from tabular figures far more
than from any hero treatment would help them.

**Restraint is the deliverable, not a constraint on top of it.** No page-load animation, no
scroll-triggered reveals, no decorative motion. The only motion in the whole system is a message
banner's opacity transition when a user dismisses it by hand — see "Motion" below.

---

## Colour

Named, semantic tokens — never a raw hex or an un-tokened `gray-400` in a template. Every pairing
below that's actually used for text or a UI-component boundary has a verified WCAG contrast ratio;
see the table.

| Token | Hex | Role |
|---|---|---|
| `ink` | `#1A1512` | Primary text |
| `paper` | `#FBFAF7` | Page background |
| `surface` | `#FFFFFF` | Card / table / input background |
| `surface-sunken` | `#171310` | Sidebar background |
| `surface-sunken-hover` | `#2A241E` | Sidebar link hover background |
| `border-subtle` | `#E6E1D6` | Decorative dividers (table rows, cards) — no contrast requirement, purely visual separation |
| `border-interactive` | `#8F8674` | Input / button / select outlines — WCAG 1.4.11 non-text contrast applies here |
| `text-muted` | `#5C5648` | Secondary text (table cell values, helper text) |
| `text-faint` | `#726B5C` | Tertiary text — still passes normal-text AA, kept for anything that might scale up to real content later |
| `text-inverse` | `#F5F2EA` | Text on the dark sidebar |
| `text-inverse-muted` | `#B7AF9E` | Secondary text on the dark sidebar |
| `accent` | `#7A2130` | Links, primary buttons, focus rings, the one brand colour |
| `accent-hover` | `#611A26` | Hover/active state for accent surfaces |
| `accent-soft` | `#F5E7E5` | Accent-tinted badge backgrounds |
| `success` / `success-soft` | `#1E6B4F` / `#E4F2EC` | Published, positive states |
| `warning` / `warning-soft` | `#8A5A00` / `#FBF0DC` | Draft, needs-attention states |
| `danger` / `danger-soft` | `#B3261E` / `#FBE9E7` | Errors, destructive actions |

### Verified contrast ratios

Computed from WCAG 2.x relative luminance, not eyeballed — every pairing the system actually uses
for text or an interactive-component boundary. AA thresholds: 4.5:1 for normal text, 3:1 for large
text and UI components (borders, focus indicators).

| Pairing | Ratio | Requirement | Result |
|---|---|---|---|
| `ink` on `paper` | 17.35:1 | 4.5:1 | Pass |
| `ink` on `surface` | 18.10:1 | 4.5:1 | Pass |
| `text-muted` on `paper` | 6.99:1 | 4.5:1 | Pass |
| `text-muted` on `surface` | 7.29:1 | 4.5:1 | Pass |
| `text-faint` on `paper` | 5.06:1 | 4.5:1 | Pass |
| `text-faint` on `surface` | 5.29:1 | 4.5:1 | Pass |
| `accent` on `paper` (links) | 9.64:1 | 4.5:1 | Pass |
| `accent` on `surface` (links) | 10.06:1 | 4.5:1 | Pass |
| `accent-hover` on `surface` | 12.47:1 | 4.5:1 | Pass |
| white on `accent` (primary buttons) | 10.06:1 | 4.5:1 | Pass |
| `danger` on `surface` | 6.54:1 | 4.5:1 | Pass |
| white on `danger` | 6.54:1 | 4.5:1 | Pass |
| `success` on `surface` | 6.42:1 | 4.5:1 | Pass |
| white on `success` | 6.42:1 | 4.5:1 | Pass |
| `warning` on `surface` | 5.93:1 | 4.5:1 | Pass |
| `text-inverse` on `surface-sunken` (sidebar) | 16.51:1 | 4.5:1 | Pass |
| `text-inverse-muted` on `surface-sunken` | 8.48:1 | 4.5:1 | Pass |
| `border-interactive` on `surface` (input/button outline) | 3.60:1 | 3:1 | Pass |
| `border-interactive` on `paper` | 3.45:1 | 3:1 | Pass |
| `accent` focus ring on `paper` / `surface` | 9.64:1 / 10.06:1 | 3:1 | Pass |
| `accent-hover` badge text on `accent-soft` | 10.36:1 | 4.5:1 | Pass |
| `success` badge text on `success-soft` | 5.57:1 | 4.5:1 | Pass |
| `warning` badge text on `warning-soft` | 5.25:1 | 4.5:1 | Pass |
| `danger` badge text on `danger-soft` | 5.58:1 | 4.5:1 | Pass |

`border-subtle` (`#E6E1D6` on white, 1.30:1) intentionally fails 3:1 — it's a decorative row/card
divider, not a UI component boundary, so WCAG 1.4.11 doesn't apply to it. It must never be used as
an input or button outline; `border-interactive` is the token for that, and does clear 3:1.

Computed with the standard sRGB relative-luminance formula (`L = 0.2126R + 0.7152G + 0.0722B` on
linearised channels, contrast = `(L1+0.05)/(L2+0.05)`), not a browser DevTools eyeball check — the
script is disposable and not part of the repo, but every number above was verified before the
token was adopted, not after.

---

## Typography

**Plex Sans** (UI, headings, prose) paired with **Plex Mono** (every number). Both are IBM Plex,
SIL Open Font License, self-hosted in `static/fonts/` with `font-display: swap` — no Google Fonts
CDN, same reasoning as vendoring HTMX/Alpine/SortableJS (CLAUDE.md; requirements §36's mobile
performance budget also wants zero third-party font-request round trips on the storefront later).
License text is alongside the font files in `static/fonts/LICENSE.txt`.

Weights shipped: Plex Sans Regular (400) and SemiBold (600) — body text and emphasis/headings, no
need for a third weight yet. Plex Mono Regular (400) only; data doesn't need a bold variant here.

This is a deliberate pairing, not the Inter-everywhere default: Plex has real character (a
grotesque with more warmth than most system-UI faces) and ships a genuine monospace sibling in the
same family, which is what makes the numeric-data signature (see above) coherent rather than
mismatched.

### Type scale

`tailwind.config.js` overrides `fontSize` with a slightly denser scale than Tailwind's default,
tuned for an admin tool that's read at close range for long sessions, not a marketing page:

| Token | Size | Line height |
|---|---|---|
| `xs` | 0.75rem (12px) | 1.1rem |
| `sm` | 0.8125rem (13px) | 1.25rem |
| `base` | 0.9375rem (15px) | 1.5rem |
| `lg` | 1.0625rem (17px) | 1.6rem |
| `xl` | 1.25rem (20px) | 1.75rem |
| `2xl` | 1.5rem (24px) | 2rem |

---

## Spacing

No custom spacing scale — Tailwind's default 4px-based scale (`1` = 0.25rem through the full
default range) is already a coherent system on its own, and reinventing it would just be
duplication with no benefit. That's a deliberate choice, not an oversight: the design system's job
here is the *values that need a brief-specific answer* (colour, type, radius, shadow), not
re-deriving spacing Tailwind already gets right.

**Button / touch-target minimum: `min-h-11` = 2.75rem = 44px** (verified against the compiled CSS,
not assumed — `.min-h-11{min-height:2.75rem}`). Every interactive control (buttons, inputs,
selects, nav links, pagination links) uses `min-h-11` for this reason; it's the one number every
later button should inherit from here rather than re-deriving.

---

## Radius & shadow

`borderRadius`: `sm` 4px, `DEFAULT` 6px, `lg` 10px — small and consistent, avoiding both a zero-
radius broadsheet look and an oversized bubbly-SaaS one.

`boxShadow.card`: a single soft, low-opacity shadow (`0 1px 2px 0 rgb(26 21 18 / 0.06), 0 1px 1px 0
rgb(26 21 18 / 0.04)`) for table containers and cards — one shadow value, used everywhere something
needs to lift off the page, rather than a new one invented per component.

---

## Focus ring

Every interactive element: `focus:outline-none focus-visible:ring-2 focus-visible:ring-accent
focus-visible:ring-offset-2 focus-visible:ring-offset-{paper|surface-sunken}` (the sidebar's dark
background needs `ring-offset-surface-sunken` and `ring-text-inverse` instead of the accent ring,
since the accent ring's own contrast against the dark sidebar wasn't part of the verified table
above — text-inverse is, at 16.51:1). `focus-visible` rather than `focus` so a mouse click doesn't
show a ring a keyboard user needs.

---

## Motion

Reduced to one place: a flash message's opacity transition when a user clicks its dismiss button
(Alpine `x-transition`). No auto-dismiss timer — an earlier draft used one and it was removed: a
slow reader or screen-reader user could lose an error message before finishing it. Messages are
persistent until dismissed, and the message container carries `role="status"
aria-live="polite"` so screen readers announce new messages without needing focus to move. No
page-load sequences, no scroll-triggered reveals, no hover micro-interactions beyond a plain colour
change — decorative motion has no job to do in a tool used for hours at a stretch.

---

## What's out of scope here

Storefront-specific layout, voice, and any storefront-only components (product cards, cart,
checkout) are Stage 6's job — this document only locks the shared token layer, not how the
storefront composes it. The storefront is explicitly meant to *not* look like the portal
(roadmap Stage 3 trap, requirements §1's two-interface split); sharing tokens is not the same as
sharing layout.

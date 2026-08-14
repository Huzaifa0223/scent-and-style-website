# Design system

Established in Stage 3 for the merchant portal; Stage 6's storefront initially inherited the same
tokens and diverged only in layout and voice. **That changed in the storefront redesign**: the
storefront now has its own palette, type scale, radius, and motion system — see "Storefront
(redesign)" below. This is a deliberate, human-directed departure from this file's original "one
system project-wide" rule, not drift: the portal is an internal back-office tool used for hours at
a stretch (legibility and speed), the storefront is a customer-facing brand surface (Scent &
Style, luxury/editorial), and the two now have different jobs the shared system wasn't serving
well for the storefront half. **The portal keeps everything below exactly as originally
specified — untouched, unaffected by the redesign.**

All tokens live in `tailwind.config.js` under `theme.extend`. This file is the rationale; that
file is the source of truth. If they disagree, the config is right and this file is stale — fix
it. Storefront tokens are namespaced with an `sf-` prefix specifically so the two systems can share
one config file without collision — see "Storefront (redesign)" for why that prefix exists and
which names it was protecting.

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

## Storefront (redesign)

A separate system from everything above, sharing only this file and `tailwind.config.js`'s file —
not a single color, type, or radius value. Source: a design brief handed to a dedicated design
tool, reviewed and directed by the human before implementation, output as a token/spec sheet plus
mockups of all six core storefront pages. Applies to `storefront/`, `cart/`, `orders/` (checkout,
confirmation, tracking) templates only. **Never applies to `portal/` or `accounts/` templates —
if you're adding an `sf-` class to a portal template, stop, that's the wrong system.**

### Why dark, editorial, and animated — a deliberate contrast with the portal above

The portal's own rationale (top of this file) explicitly argues against a near-black background, a
serif face, and decorative motion — for the portal's brief. That reasoning doesn't transfer to the
storefront: a merchant scanning a data table for hours needs legibility and speed; a customer
discovering a fragrance brand for the first time is not doing the same job, and "quietly
best-selling," slow-reveal, unhurried-feeling pages are doing real brand work a plain admin-UI
palette can't. Two different jobs, two different systems, on purpose.

### Colour

| Token | Hex | Role | Contrast |
|---|---|---|---|
| `sf-ink-deep` | `#0E0B0A` | App shell background | — |
| `sf-ink` | `#14100E` | Page background | — |
| `sf-surface` | `#2C2621` | Cards, inputs, filter tray | 1.27:1 vs `sf-ink` — see note below |
| `sf-surface-raised` | `#3A322B` | Hover / elevated rows | 1.51:1 vs `sf-ink` |
| `sf-line` | `#786755` | Borders, dividers, input/component boundaries | 3.49:1 vs `sf-ink` — AA (non-text) |
| `sf-line-strong` | `#8F7C67` | Secondary button borders | 4.73:1 vs `sf-ink` |
| `sf-fg` | `#F4EFE9` | Primary text | 15.1:1 on `sf-ink` — AAA |
| `sf-fg-muted` | `#BDB2A8` | Body / secondary text | 8.3:1 on `sf-ink` — AAA |
| `sf-fg-dim` | `#8E837A` | Meta, captions, 14px+ only | 4.6:1 on `sf-ink` — AA |
| `sf-brass` | `#D8A448` | Accent, primary CTA fill, focus ring | 9.0:1 on `sf-ink` — AAA |
| `sf-brass-press` | `#BE8C32` | CTA hover / pressed | 6.7:1 on `sf-ink` — AA |
| `sf-cream` | `#E8D9C3` | Prices, italic display accents | 12.1:1 on `sf-ink` — AAA |
| `sf-paper` | `#F4EFE9` | Light editorial band background | pairs with `#1A1512` at 14.6:1 |
| `sf-paper-fg-muted` | `#6B5C4A` | Eyebrow labels on `sf-paper` | 5.64:1 — see note below |
| `sf-ok` | `#7FBF9A` | Success, in stock | 8.0:1 on `sf-ink` — AAA |
| `sf-warn` | `#E3B45C` | Low stock, delivery notes | 10.3:1 on `sf-ink` — AAA |
| `sf-danger` | `#E88178` | Form errors, removal | 7.1:1 on `sf-ink` — AAA |
| `sf-whatsapp` | `#25D366` | WhatsApp handoff button only | 10.4:1 with its own `#0B1F13` text |

`sf-fg-dim` is never used below 14px, and only for meta/caption text — that's what keeps its AA
(not AAA) ratio acceptable; anything more prominent than a caption uses `sf-fg-muted` or `sf-fg`.

**Corrected post-launch, against a real contrast audit of the shipped Home page** — `sf-surface`
and `sf-line` originally shipped at the design brief's own values (`#1E1917` / `#332B27`), which
measured **1.09:1** and **1.37:1** against `sf-ink`, computed with the same sRGB relative-luminance
formula used everywhere else in this file, not eyeballed. WCAG 1.4.11 requires 3:1 for a UI
component's visual boundary; at those ratios, cards, tiles, and the search input were genuinely
imperceptible outside the text sitting inside them. `sf-line` is corrected to a real 3:1+ (3.49:1)
and now carries the boundary requirement on its own; `sf-surface` gets a smaller lift to 1.27:1
rather than chasing 3:1 on the fill too — a fill doesn't independently need 3:1 when a compliant
border already marks the component boundary, and every consumer of `sf-surface` in this codebase
pairs it with an `sf-line` border (confirmed by reading every template that uses it, not assumed).
`sf-paper-fg-muted` is corrected from the brief's `#7A6A56` (4.57:1 — the most fragile pairing on
the site, 11px caps text 0.07 above AA's 4.5:1 floor) to `#6B5C4A` (5.64:1) for real headroom.

### Typography

Two typefaces, both SIL Open Font License, both self-hosted in `static/fonts/` — same "no CDN, no
runtime font request" rule as Plex above, same license-file-alongside-the-binary convention
(`static/fonts/LICENSE-CormorantGaramond.txt`, `static/fonts/LICENSE-IBMPlex.txt` — split into two
files now that there are two font families with two different copyright holders under OFL).

- **Cormorant Garamond** (`font-display`) — display/heading face. One variable-font file
  (`CormorantGaramond-Roman.woff2`) legitimately backs two `@font-face` weight declarations (300
  and 400) — verified directly against Google's own CSS2 delivery for this family before relying
  on it, not assumed. A second file (`CormorantGaramond-Italic.woff2`) covers the one italic
  weight actually used (300, for the homepage hero's accent line).
- **IBM Plex Sans** (`font-sans`) — body/UI face, same family already vendored for the portal.
  Storefront body text and the portal's UI text share a typeface on purpose; only the display face
  and the palette are new.

| Token | Size | Line height | Weight | Use |
|---|---|---|---|---|
| `sf-d-2xl` | 4.25rem (68px) | 1.02 | 300 | Hero headline, desktop |
| `sf-d-xl` | 2.75rem (44px) | 1.04 | 300 | Hero headline, mobile |
| `sf-d-lg` | 2.25rem (36px) | 1.08 | 300 | Page title |
| `sf-d-md` | 1.6875rem (27px) | 1.25 | 400 | Section heading |
| `sf-d-sm` | 1.1875rem (19px) | 1.2 | 400 | Card title |
| `sf-lede` | 1.0625rem (17px) | 1.7 | 400 | Intro / lede paragraph |
| `sf-base` | 1rem (16px) | 1.65 | 400 | Body text |
| `sf-sm` | 0.875rem (14px) | 1.6 | 400 | Secondary text |
| `sf-caption` | 0.75rem (12px) | 1.5 | 400 | Captions |
| `sf-eyebrow` | 0.6875rem (11px) | 1 | 500, 0.22em caps | Overline / kicker labels |

### Radius, shadow, motion tokens

`sf` (2px, default), `sf-md` (4px), `sf-lg` (8px) — deliberately sharp, editorial, not the
portal's softer 6px default. `sf-lift`/`sf-float`/`sf-drawer`/`sf-overlay` box-shadows for cards,
hover elevation, the cart drawer, and the lightbox respectively — on this dark palette, elevation
reads mainly from `sf-surface` → `sf-surface-raised`, not shadow; shadow is reserved for things
that actually float above the page (drawer, lightbox, toast). `duration-420` plus the existing
Tailwind `duration-200`/`duration-700` and a `sf-editorial` timing function
(`cubic-bezier(0.16, 1, 0.30, 1)`) cover every animation below. `min-h-sf-tap` (44px) / `min-h-sf-ctrl`
(52px) and `max-w-sf-shell` (1240px) / `max-w-sf-form` (560px) round out the layout tokens.

### Motion — the deliberate opposite of the portal's "restraint is the deliverable"

Six specified animations, every one CSS-transition or Alpine-`x-transition` implementable (no new
JS dependency):

1. **Hero / section entrance** — `duration-700 sf-editorial`, 80ms stagger per child. Hero fires on
   load; every section below fires on scroll into view (`IntersectionObserver`, threshold 0.15,
   unobserve after first fire — never re-fires). `opacity 0→1` + `translateY(18px)→0`. Under
   `prefers-reduced-motion: reduce`: opacity only, 200ms, no translate.
2. **Product card hover** — 260ms image cross-fade + 200ms `translateY(-2px)` lift, ease-out,
   `@media (hover: hover)` only. Keyboard `:focus-within` gets the same visual plus the focus ring.
   Touch devices never get a hover state — their "Add to cart" affordance is always visible instead
   of hidden behind hover.
3. **Gallery lightbox** — open 380ms, close 260ms, `sf-editorial`; Alpine `x-show`/`x-transition`
   with a trapped focus that returns to the trigger on close, body scroll locked while open (all
   already-established patterns from the existing PDP lightbox — reuse, don't reinvent).
4. **Cart drawer** — in 420ms, out 300ms, `sf-editorial`. Panel `translateX(100%)→0`; backdrop
   fades in slightly ahead of the panel. Same Alpine `x-transition` shape the drawer already uses
   today, new timing/easing only.
5. **Add-to-cart feedback** — badge scales `1→1.28→1` over 220ms (no overshoot past 1.28); a
   `sf-paper`-colored toast slides down 10px, holds ~2s, fades out — one CSS keyframe animation so
   it self-dismisses with no JS timer to manage. `aria-live="polite"` on the toast text. The drawer
   never auto-opens on add.
6. **Buttons, links, focus** — `duration-200` ease-out hover (brass fill darkens, ghost-button
   border/text moves to brass, link underline grows `scaleX 0→1` from the left). Focus is *never* a
   color change: `:focus-visible` draws a 2px `sf-brass` outline at 3px offset — same
   never-`:focus`-always-`:focus-visible` rule as the portal's own focus ring above, so a mouse
   click never shows a keyboard-only ring.

**Skeleton loading**, reused/extended from the existing storefront skeleton loaders (Stage 6): the
skeleton mirrors the real element's exact box (same aspect ratio, same text-line widths) so nothing
shifts on swap. Sweep is `background-position` `duration-[1600ms]` linear infinite — never a pulse.
Swap is a 240ms ease-out cross-fade, skeleton opacity out / content opacity in, no translate. Under
`prefers-reduced-motion: reduce` the sweep becomes a static `sf-surface-raised` fill.

### Accessibility — unchanged requirements, restated for this palette

Every rule from the portal's own accessibility work applies here too — this is a different palette,
not a different accessibility bar:

- Every tap target ≥44×44 (`min-h-sf-tap`) — icon buttons are 44px squares even when the glyph
  itself is 16px; quantity steppers are 44×52 (`min-h-sf-ctrl`).
- Focus is the 2px `sf-brass` outline at 3px offset via `:focus-visible`, always distinguishable
  from hover (hover never changes color the same way focus does).
- The skip-to-content link stays first in the DOM, becomes a visible `sf-paper`-on-`sf-ink` chip on
  focus.
- The cart drawer and lightbox trap focus, close on Escape, and return focus to their trigger.
- `sf-fg-dim` never appears below 14px (see the colour table above).
- `prefers-reduced-motion: reduce` drops every translate/scale project-wide on the storefront,
  keeping only 150–200ms opacity fades; the skeleton sweep becomes a static fill.

---

## What's out of scope here

Storefront-specific layout and voice beyond the token/motion system above (exact page composition,
copy, imagery) are implemented incrementally, template by template, against the tokens and specs
above — this document locks the *system*, not a pixel-for-pixel spec of every page. The storefront
is explicitly meant to *not* look like the portal (roadmap Stage 3 trap, requirements §1's
two-interface split, and now two genuinely separate token systems); sharing a config file is not
the same as sharing a look.

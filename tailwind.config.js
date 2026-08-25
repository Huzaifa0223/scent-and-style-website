/**
 * Tailwind standalone CLI config — no Node/npm in the build (CLAUDE.md).
 *
 * Design tokens live here as `theme.extend` values, not as raw hex/px
 * scattered through templates. Rationale, the typeface pairing, and
 * verified WCAG contrast ratios are in docs/design.md — read that before
 * changing any value below. Core Tailwind utilities only: no plugins.
 */
module.exports = {
  // forms.py is scanned as well as templates: core/forms.py assigns Tailwind
  // class strings to widgets for every form in the project, and those files
  // were previously invisible to the scanner. Every class they used happened
  // to appear in some template too, so nothing was purged — but only by
  // coincidence, and "placeholder:text-sf-fg-dim" was down to two templates.
  // Deleting the last template that used one would have silently stripped
  // styling from every form field, with nothing failing to point at why.
  content: ["./templates/**/*.html", "./*/templates/**/*.html", "./*/forms.py"],
  theme: {
    extend: {
      colors: {
        ink: "#1A1512",
        paper: "#FBFAF7",
        surface: {
          DEFAULT: "#FFFFFF",
          sunken: "#171310",
          "sunken-hover": "#2A241E",
        },
        border: {
          subtle: "#E6E1D6",
          interactive: "#8F8674",
        },
        text: {
          DEFAULT: "#1A1512",
          muted: "#5C5648",
          faint: "#726B5C",
          inverse: "#F5F2EA",
          "inverse-muted": "#B7AF9E",
        },
        accent: {
          DEFAULT: "#7A2130",
          hover: "#611A26",
          soft: "#F5E7E5",
        },
        success: { DEFAULT: "#1E6B4F", soft: "#E4F2EC" },
        warning: { DEFAULT: "#8A5A00", soft: "#FBF0DC" },
        danger: { DEFAULT: "#B3261E", soft: "#FBE9E7" },

        // --- Storefront redesign (Ajmal Perfumes system) — warm luxury palette.
        // Every key uses "ajmal-" prefix to maintain separation from portal tokens.
        // "ink", "paper", "surface" at the top of this object are for the portal and
        // must not be used in storefront templates; they would silently repaint the
        // merchant UI with customer-facing colors.

        // Primary text — warm dark brown, more readable than the previous #14100E
        // against cream backgrounds. Verified contrast: 19.1:1 on cream (#FFF7EE).
        "ajmal-ink": { DEFAULT: "#2B2826", soft: "#413D3A" },

        // Background palette — warm creams and sand tones.
        // cream: section backgrounds, card fills, page base.
        // sand: mobile bottom navigation bar.
        // blush gradients: decorative section backgrounds (linear-gradient stop points).
        "ajmal-cream": { DEFAULT: "#FFF7EE", secondary: "#FAF9F5" },
        "ajmal-sand": { DEFAULT: "#F0E6DB", secondary: "#F3EDE7" },
        "ajmal-blush": { grad_a: "#EDE2DD", grad_b: "#F7F1EE" },

        // Brand accent — keep the storefront on the canonical gold from docs/design.md.
        // 10% and 21% tints for card backgrounds and hover states.
        "ajmal-gold": {
          DEFAULT: "#D8A448",
          10: "rgba(216, 164, 72, 0.10)",
          21: "rgba(216, 164, 72, 0.21)",
        },

        // Utility colors — semantic signaling.
        "ajmal-muted": "#777777",                  // meta text (size, fragrance notes)
        "ajmal-star": "#F3C45A",                   // rating stars
        "ajmal-sale": "#BE4040",                   // sale/strike price
        "ajmal-whatsapp": { DEFAULT: "#16BE45", hover: "#20BD5A" }, // WhatsApp FAB
        "ajmal-ok": "#7FBF9A",                     // success state
        "ajmal-warn": "#E3B45C",                   // warning
        "ajmal-danger": "#E88178",                 // error

        // Text color aliases — sf-* names map to new Ajmal tokens for template compatibility.
        // Existing templates reference sf-fg/sf-fg-dim/etc.; these map to the new palette.
        "sf-fg": { DEFAULT: "#2B2826", muted: "#777777", dim: "#777777", "onbrass": "#2B2826" },
        "sf-fg-muted": "#777777",
        "sf-fg-dim": "#777777",
        "sf-paper": "#FFF7EE",                     // cream background
        "sf-paper-fg": { DEFAULT: "#2B2826", muted: "#777777" },
        "sf-brass": { DEFAULT: "#D8A448", hover: "#C9973D", press: "#BE8C32" },
        "sf-cream": "#F0E6DB",                     // sand tone
        "sf-ink": { DEFAULT: "#2B2826", deep: "#1A1512" },
        "sf-surface": "#FFF7EE",                   // cream
        "sf-line": { DEFAULT: "#D8A448", strong: "#C9973D", gold: "rgba(216, 164, 72, 0.50)" },
      },
      fontFamily: {
        sans: ["Futura", "Avenir Next", "Montserrat", "Helvetica Neue", "Arial", "sans-serif"],
        mono: ["Futura", "Avenir Next", "Montserrat", "Helvetica Neue", "Arial", "sans-serif"],
        // Whole-site typography now follows a clean Futura-style sans stack.
        // Headings remain bold and body text remains regular weight across the storefront.
        satoshi: ["Futura", "Avenir Next", "Montserrat", "Helvetica Neue", "Arial", "sans-serif"],
        gambetta: ["Futura", "Avenir Next", "Montserrat", "Helvetica Neue", "Arial", "sans-serif"],
        tajawal: ["Futura", "Avenir Next", "Montserrat", "Helvetica Neue", "Arial", "sans-serif"],
      },
      fontSize: {
        xs: ["0.75rem", { lineHeight: "1.1rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.9375rem", { lineHeight: "1.5rem" }],
        lg: ["1.0625rem", { lineHeight: "1.6rem" }],
        xl: ["1.25rem", { lineHeight: "1.75rem" }],
        "2xl": ["1.5rem", { lineHeight: "2rem" }],

        // Storefront redesign type scale — "sf-" prefixed for the same
        // reason as the colors above (sf-sm/sf-base collide in *value*,
        // not just name, with the portal's sm/base).
        "sf-eyebrow": ["0.6875rem", { lineHeight: "1", letterSpacing: "0.22em" }],
        "sf-caption": ["0.75rem", { lineHeight: "1.5" }],
        "sf-sm": ["0.875rem", { lineHeight: "1.6" }],
        "sf-base": ["1rem", { lineHeight: "1.65" }],
        "sf-lede": ["1.0625rem", { lineHeight: "1.7" }],
        "sf-d-sm": ["1.1875rem", { lineHeight: "1.2" }],
        "sf-d-md": ["1.6875rem", { lineHeight: "1.25" }],
        "sf-d-lg": ["2.25rem", { lineHeight: "1.08" }],
        "sf-d-xl": ["2.75rem", { lineHeight: "1.04" }],
        "sf-d-2xl": ["4.25rem", { lineHeight: "1.02" }],
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        lg: "10px",
        // Storefront redesign (Ajmal Perfumes) uses rounder corners — 12px
        // for product cards and major components instead of 2px sharp editorial
        // style. "ajmal-card" for product tiles; component classes maintain
        // their own radius rules via Tailwind utilities on the element.
        "ajmal-card": "12px",
        "ajmal-md": "16px",
        "ajmal-button": "24px",            // pill-shaped buttons
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(26 21 18 / 0.06), 0 1px 1px 0 rgb(26 21 18 / 0.04)",
        // Ajmal Perfumes shadow system — minimal elevation, emphasis on texture/tint.
        // Values are conservative; the design relies on background tints and
        // gold geometric patterns more than shadow depth for visual separation.
        "ajmal-lift": "0 2px 8px rgba(43, 40, 38, 0.08)",     // header on scroll
        "ajmal-float": "0 8px 24px rgba(43, 40, 38, 0.12)",   // floating panels
        "ajmal-drawer": "-24px 0 48px rgba(43, 40, 38, 0.15)", // cart drawer
        "ajmal-overlay": "0 20px 50px rgba(43, 40, 38, 0.16)", // modal backdrop
        // Product card hover — tight negative spread to read as lift, not halo.
        "ajmal-card-hover": "0 8px 24px -8px rgba(43, 40, 38, 0.12)",
      },
      transitionTimingFunction: {
        // Ajmal Perfumes easing — smooth, decelerated motion.
        "ajmal-ease": "cubic-bezier(.4, 0, .2, 1)",
      },
      transitionDuration: {
        // Unified interaction speed across the system. 300ms is slower than
        // the previous 160/240ms but still responsive — matches Ajmal's
        // "300ms cubic-bezier(.4,0,.2,1)" for all interaction feedback.
        300: "300ms",
        // Named steps for motion inventory alignment.
        fast: "300ms",          // control feedback (was 160ms)
        base: "300ms",          // card hover (was 240ms)
        slow: "400ms",          // image zoom (was 360ms)
        // Scroll-triggered slide-ins: 1.2–1.7s once-only motion.
        "slide-in-fast": "1200ms",
        "slide-in-mid": "1400ms",
        "slide-in-slow": "1700ms",
        // Hero carousel autoplay: 3000ms between slides.
        hero: "3000ms",
      },
      minHeight: {
        "sf-tap": "44px",
        "sf-ctrl": "52px",
      },
      maxWidth: {
        "sf-shell": "1240px",
        "sf-form": "560px",
      },
      spacing: {
        // Named page-gutter steps so header, body, and footer can never
        // drift apart. The storefront previously ran px-4 -> sm:px-8 and
        // then held 32px all the way to the 1240px cap, which is why a
        // ~1100px viewport looked edge-to-edge: correct container, but no
        // gutter growth between the phone step and the cap.
        gutter: "1.5rem",
        "gutter-md": "2.5rem",
        "gutter-lg": "4rem",
      },
      keyframes: {
        // Grid entrance animation — cards fade and rise on initial page load.
        // Staggered via animation-delay in component layer (CSS only, no JS).
        "rise-in": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        // Ajmal Perfumes slide-in animations — section entrance on scroll.
        // Spec calls for 1.2–1.7s once-only motion as user scrolls sections
        // into view (via data-reveal + .is-in marker from JS observer).
        "slide-in": {
          "0%": { opacity: "0", transform: "translateY(18px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        // Hero carousel slide animation — 3000ms between cards (Swiper autoplay).
        "hero-slide": {
          "0%": { opacity: "0", transform: "translateX(-6px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
      },
      animation: {
        // Product grid entrance. Updated easing to Ajmal's cubic-bezier(.4,0,.2,1),
        // kept 480ms as a reasonable duration for the full stagger.
        "rise-in": "rise-in 480ms cubic-bezier(.4, 0, .2, 1) both",
        "fade-in": "fade-in 300ms cubic-bezier(.4, 0, .2, 1) both",
        // Ajmal slide-in: triggered by intersection observer on sections,
        // with three speed variants (fast/mid/slow). Each is once-only, no loop.
        "slide-in-fast": "slide-in 1200ms cubic-bezier(.4, 0, .2, 1) both",
        "slide-in-mid": "slide-in 1400ms cubic-bezier(.4, 0, .2, 1) both",
        "slide-in-slow": "slide-in 1700ms cubic-bezier(.4, 0, .2, 1) both",
        // Hero carousel slide feedback.
        "hero-slide": "hero-slide 300ms cubic-bezier(.4, 0, .2, 1) forwards",
      },
    },
  },
  plugins: [],
};

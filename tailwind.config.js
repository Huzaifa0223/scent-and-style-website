/**
 * Tailwind standalone CLI config — no Node/npm in the build (CLAUDE.md).
 *
 * Design tokens live here as `theme.extend` values, not as raw hex/px
 * scattered through templates. Rationale, the typeface pairing, and
 * verified WCAG contrast ratios are in docs/design.md — read that before
 * changing any value below. Core Tailwind utilities only: no plugins.
 */
module.exports = {
  content: ["./templates/**/*.html", "./*/templates/**/*.html"],
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

        // --- Storefront redesign (luxury/editorial, dark) — every key below
        // is "sf-" prefixed on purpose. `ink`, `paper`, `surface`, and
        // `danger` above already mean something different for the portal;
        // reusing those names here would silently repaint portal screens
        // that share this one config file. Portal templates must never use
        // an "sf-" class; storefront templates must never use an unprefixed
        // one. See docs/design.md's "Two systems" section.
        "sf-ink": { DEFAULT: "#14100E", deep: "#0E0B0A" },
        "sf-surface": { DEFAULT: "#1E1917", raised: "#2A2321" },
        "sf-line": { DEFAULT: "#332B27", strong: "#4A403A" },
        "sf-paper": "#F4EFE9",
        // The spec (docs/design.md) verifies sf-paper pairs with #1A1512
        // text at 14.6:1 but names no token for that text color — added
        // here rather than an inline hex in a template (project rule:
        // never a raw hex in a template).
        "sf-paper-fg": { DEFAULT: "#1A1512", muted: "#7A6A56" },
        "sf-brass": { DEFAULT: "#D8A448", hover: "#E8BE6C", press: "#BE8C32" },
        "sf-cream": "#E8D9C3",
        "sf-fg": { DEFAULT: "#F4EFE9", muted: "#BDB2A8", dim: "#8E837A", onbrass: "#14100E" },
        "sf-ok": "#7FBF9A",
        "sf-warn": "#E3B45C",
        "sf-danger": "#E88178",
        "sf-whatsapp": "#25D366",
      },
      fontFamily: {
        sans: ["Plex Sans", "system-ui", "sans-serif"],
        mono: ["Plex Mono", "ui-monospace", "SFMono-Regular", "monospace"],
        // Storefront only — the portal stays Plex-only (docs/design.md).
        display: ["Cormorant Garamond", "Georgia", "serif"],
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
        // Storefront redesign is deliberately sharp-cornered (editorial,
        // not the portal's softer admin-UI radius) — "sf-" prefixed since
        // "DEFAULT" can't be overridden per-consumer in one shared config.
        sf: "2px",
        "sf-md": "4px",
        "sf-lg": "8px",
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(26 21 18 / 0.06), 0 1px 1px 0 rgb(26 21 18 / 0.04)",
        "sf-lift": "0 2px 8px rgba(0,0,0,0.40)",
        "sf-float": "0 10px 30px rgba(0,0,0,0.50)",
        "sf-drawer": "-30px 0 60px rgba(0,0,0,0.50)",
        "sf-overlay": "0 24px 60px rgba(0,0,0,0.60)",
      },
      transitionTimingFunction: {
        "sf-editorial": "cubic-bezier(0.16, 1, 0.30, 1)",
      },
      transitionDuration: {
        // 200 and 700 already exist in Tailwind's default scale at these
        // same values — listed for readability, not overriding anything.
        200: "200ms",
        420: "420ms",
        700: "700ms",
      },
      minHeight: {
        "sf-tap": "44px",
        "sf-ctrl": "52px",
      },
      maxWidth: {
        "sf-shell": "1240px",
        "sf-form": "560px",
      },
    },
  },
  plugins: [],
};

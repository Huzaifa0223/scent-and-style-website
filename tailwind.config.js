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
      },
      fontFamily: {
        sans: ["Plex Sans", "system-ui", "sans-serif"],
        mono: ["Plex Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        xs: ["0.75rem", { lineHeight: "1.1rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.9375rem", { lineHeight: "1.5rem" }],
        lg: ["1.0625rem", { lineHeight: "1.6rem" }],
        xl: ["1.25rem", { lineHeight: "1.75rem" }],
        "2xl": ["1.5rem", { lineHeight: "2rem" }],
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        lg: "10px",
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(26 21 18 / 0.06), 0 1px 1px 0 rgb(26 21 18 / 0.04)",
      },
    },
  },
  plugins: [],
};

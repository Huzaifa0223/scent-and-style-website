/** Tailwind standalone CLI config — no Node/npm in the build (CLAUDE.md). */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./*/templates/**/*.html",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};

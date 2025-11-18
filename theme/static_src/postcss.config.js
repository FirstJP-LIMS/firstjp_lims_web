module.exports = {
  content: [
    "./templates/**/*.html",        // Django templates
    "./**/templates/**/*.html",     // app-level templates
    "./static/js/**/*.js",          // JS files
  ],
  theme: {
    extend: {},
  },
  plugins: {
    "@tailwindcss/postcss": {},
    "postcss-simple-vars": {},
    "postcss-nested": {}
  },
}

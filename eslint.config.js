const js = require('@eslint/js');
const globals = require('globals');

// Flat config (ESLint 9+/10). Replaces the legacy .eslintrc.js, which ESLint 10
// no longer supports. ESLint owns code quality (js.configs.recommended); Prettier
// owns formatting (see .prettierrc: singleQuote, semi, tabWidth). The old eslintrc
// also set indent/quotes/semi, but those duplicate Prettier and ESLint's `indent`
// rule conflicts with Prettier on edge cases, so they're intentionally dropped.
module.exports = [
  {
    ignores: [
      'static/js/dist/**',
      'staticfiles/**',
      '**/node_modules/**',
      '**/*.min.js',
    ],
  },
  js.configs.recommended,
  {
    files: ['static/js/**/*.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
  },
];

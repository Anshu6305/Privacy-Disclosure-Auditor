/**
 * ESLint configuration.
 *
 * The `lint` script predates this file and had nothing to read, so it failed
 * with a setup message rather than linting anything. Added here with M9
 * because the script claims a check the project was not performing.
 *
 * `react/prop-types` is off: these components take props described by the
 * Pydantic schemas in backend/app/api/schemas/audit.py, which is the one
 * authoritative description of the contract. A second, hand-maintained copy
 * in PropTypes would drift from it and the drift would be silent.
 */

module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  extends: ['eslint:recommended', 'plugin:react/recommended', 'plugin:react/jsx-runtime'],
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module', ecmaFeatures: { jsx: true } },
  settings: { react: { version: '18.3' } },
  rules: {
    'react/prop-types': 'off',
    'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
  },
  overrides: [
    {
      files: ['**/*.test.jsx', 'src/test/**'],
      env: { node: true },
      globals: { describe: 'readonly', it: 'readonly', expect: 'readonly', vi: 'readonly' },
    },
  ],
};

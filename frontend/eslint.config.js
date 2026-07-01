import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";

export default tseslint.config(
  {
    ignores: ["dist", "coverage", "playwright-report", "test-results"],
  },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
  {
    files: ["**/*.test.{ts,tsx}", "src/vitest.setup.ts"],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node, ...globals.vitest },
    },
  },
  {
    // Playwright E2E specs run in Node (config + `Buffer`), not the browser,
    // and are transpiled by Playwright rather than the app's `tsc` build.
    files: ["e2e/**/*.{ts,tsx}", "playwright.config.ts"],
    languageOptions: {
      globals: { ...globals.node },
    },
  },
  {
    // shadcn/ui primitives intentionally co-export component + variant helpers
    // (e.g. buttonVariants). They are library files, not fast-refresh targets.
    files: ["src/components/ui/**/*.{ts,tsx}"],
    rules: {
      "react-refresh/only-export-components": "off",
    },
  },
  prettier,
);

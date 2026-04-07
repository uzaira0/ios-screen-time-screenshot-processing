import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "*.config.js", "*.config.ts", "server"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
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
      // Downgrade new react-hooks v7 rules to warnings (pre-existing patterns)
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/immutability": "warn",
      "react-hooks/refs": "warn",
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/no-explicit-any": "warn",
      "no-console": ["warn", { allow: ["warn", "error"] }],

      // Catch real bugs
      "no-constant-binary-expression": "error",
      "no-constructor-return": "error",
      "no-self-compare": "error",
      "no-template-curly-in-string": "warn",
      "no-unmodified-loop-condition": "error",
      "no-unreachable-loop": "error",
      "require-atomic-updates": "warn",
      "array-callback-return": "error",
      "no-await-in-loop": "warn",
      "no-promise-executor-return": "error",
      "eqeqeq": ["error", "always", { null: "ignore" }],
    },
  }
);

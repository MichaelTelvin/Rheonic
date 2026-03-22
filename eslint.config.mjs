import js from "@eslint/js";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";
import globals from "globals";
import importPlugin from "eslint-plugin-import";

const frontendFiles = ["frontend/src/**/*.{ts,tsx}"];
const sdkNodeFiles = ["sdk-node/src/**/*.ts"];

const sharedTypeScriptRules = {
  ...tsPlugin.configs.recommended.rules,
  "no-console": "warn",
  "consistent-return": "error",
  "no-undef": "off",
  "import/order": [
    "error",
    {
      alphabetize: { order: "asc", caseInsensitive: true },
      "newlines-between": "always",
      groups: [["builtin", "external"], ["internal", "parent", "sibling", "index"], ["type"]],
    },
  ],
  "no-unused-vars": "off",
  "@typescript-eslint/no-explicit-any": "off",
  "@typescript-eslint/no-unused-vars": [
    "error",
    {
      argsIgnorePattern: "^_",
      varsIgnorePattern: "^_",
      caughtErrorsIgnorePattern: "^_",
    },
  ],
};

const typeScriptLanguageOptions = {
  parser: tsParser,
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    ecmaFeatures: {
      jsx: true,
    },
  },
};

export default [
  {
    ignores: ["**/dist/**", "**/node_modules/**", "**/coverage/**", "frontend/public/**"],
  },
  js.configs.recommended,
  {
    files: frontendFiles,
    languageOptions: {
      ...typeScriptLanguageOptions,
      globals: {
        ...globals.browser,
        ...globals.es2021,
      },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      import: importPlugin,
    },
    rules: sharedTypeScriptRules,
  },
  {
    files: ["frontend/src/lib/logger.ts"],
    rules: {
      "no-console": "off",
    },
  },
  {
    files: sdkNodeFiles,
    languageOptions: {
      ...typeScriptLanguageOptions,
      globals: {
        ...globals.node,
        ...globals.es2022,
      },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      import: importPlugin,
    },
    rules: sharedTypeScriptRules,
  },
];

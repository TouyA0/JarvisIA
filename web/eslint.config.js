import js from "@eslint/js";
import globals from "globals";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import jsxA11y from "eslint-plugin-jsx-a11y";

export default [
  // public/ort/** est vendoré par onnxruntime-web (copié tel quel, non
  // écrit ici) : pas de code source à linter.
  { ignores: ["dist/**", "node_modules/**", "public/ort/**"] },
  js.configs.recommended,
  jsxA11y.flatConfigs.recommended,
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: { ...globals.browser, ...globals.node },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      react,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      // jsx-uses-vars seul (pas tout eslint-plugin-react) : sans lui,
      // no-unused-vars ne voit pas qu'un composant importé est "utilisé"
      // via <Foo /> (JSXIdentifier, pas Identifier) et le signale comme mort
      // à tort sur tout composant qui n'est référencé que dans du JSX.
      "react/jsx-uses-vars": "error",
      // Seulement les règles historiques (rules-of-hooks, exhaustive-deps) :
      // reactHooks.configs.recommended embarque désormais aussi les règles
      // du React Compiler (refs/immutability/preserve-manual-memoization…),
      // bien plus strictes et hors sujet pour une base non préparée pour le
      // compilateur — elles feraient exploser le nombre d'erreurs sans lien
      // avec de vrais bugs de hooks.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    },
  },
  {
    files: ["**/*.test.{js,jsx}", "src/test/**"],
    languageOptions: {
      globals: { ...globals.vitest },
    },
  },
  {
    // Exécute dans le contexte AudioWorkletGlobalScope, pas le DOM.
    files: ["public/wakeword-worklet.js"],
    languageOptions: {
      globals: {
        AudioWorkletProcessor: "readonly",
        registerProcessor: "readonly",
        sampleRate: "readonly",
        currentFrame: "readonly",
        currentTime: "readonly",
      },
    },
  },
];

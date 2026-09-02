import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En dev, Vite sert le front sur :5173 et relaie /api + /ws vers le brain
// (:8420, voir brain/config.py) pour éviter un rebuild à chaque changement.
// En prod, brain/server.py sert directement web/dist en statique — pas de
// proxy nécessaire, tout est servi depuis la même origine.
export default defineConfig({
  plugins: [react()],
  // Force onnxruntime-web à résoudre vers sa variante "wasm externe"
  // (ort.wasm.min.mjs) plutôt que son bundle par défaut, qui inline une
  // référence statique vers un .wasm de 26 Mo (WebGPU/JSEP) que Vite
  // embarque bêtement. wasmPaths (voir wakeWordDetector.js) pointe alors
  // vers web/public/ort/, où seul le binaire WASM simple (13 Mo) est copié.
  resolve: {
    conditions: ["onnxruntime-web-use-extern-wasm"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8420",
      "/ws": {
        target: "ws://127.0.0.1:8420",
        ws: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
    globals: true,
  },
});

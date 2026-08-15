import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En dev, Vite sert le front sur :5173 et relaie /api + /ws vers le brain
// (:8420, voir brain/config.py) pour éviter un rebuild à chaque changement.
// En prod, brain/server.py sert directement web/dist en statique — pas de
// proxy nécessaire, tout est servi depuis la même origine.
export default defineConfig({
  plugins: [react()],
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
});

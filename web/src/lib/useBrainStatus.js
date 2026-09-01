import { useEffect, useState } from "react";
import { authFetch } from "./consoleAuth.js";

// Assez lent pour ne rien coûter, assez rapide pour qu'un brain relancé
// se voie avant qu'on aille cliquer sur un bouton qui échouerait.
const POLL_MS = 5000;

/**
 * État de la liaison avec le brain, disponible partout (barre latérale,
 * en-têtes, boutons désactivés). Avant, seule la Console le savait — via
 * son WebSocket de chat — donc les autres écrans laissaient cliquer des
 * boutons qui ne pouvaient qu'échouer en silence.
 *
 * `/api/health` plutôt qu'un WebSocket dédié : la route est publique
 * (pas de token requis) et le brain la sert déjà pour ses sondes de
 * démarrage.
 */
export function useBrainStatus() {
  const [status, setStatus] = useState("connecting"); // connecting | online | offline

  useEffect(() => {
    let cancelled = false;

    async function ping() {
      try {
        const res = await authFetch("/api/health");
        if (!cancelled) setStatus(res.ok ? "online" : "offline");
      } catch {
        if (!cancelled) setStatus("offline");
      }
    }

    ping();
    const id = setInterval(ping, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return status;
}

import { useCallback, useEffect, useState } from "react";
import { authFetch } from "./consoleAuth.js";

// Poll rapide et volontairement dédié (pas mutualisé avec useIntegrations) :
// une confirmation en attente bloque un thread côté brain jusqu'à 90s
// (voir brain/integrations/confirm.py), la bannière doit apparaître vite
// pour ne pas gâcher inutilement ce délai.
const POLL_MS = 1000;

export function useConfirmations() {
  const [pending, setPending] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const res = await authFetch("/api/confirmations");
      if (res.ok) setPending(await res.json());
    } catch {
      // brain injoignable — on garde la dernière liste connue
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const resolve = useCallback(
    async (id, approved) => {
      // Retrait optimiste : la bannière ne doit pas rester affichée jusqu'au
      // prochain poll après un clic, ça se sentirait mou.
      setPending((p) => p.filter((c) => c.id !== id));
      await authFetch(`/api/confirmations/${id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved }),
      });
      await refresh();
    },
    [refresh],
  );

  return { pending, resolve };
}

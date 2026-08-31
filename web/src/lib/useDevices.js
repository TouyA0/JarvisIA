import { useCallback, useEffect, useState } from "react";
import { authFetch } from "./consoleAuth.js";

const POLL_MS = 3000;

/**
 * Liste des appareils appairés, rafraîchie par polling — pas de canal
 * WebSocket dédié pour l'instant, /api/devices suffit à cette fréquence
 * pour un écran de gestion (pas une vue temps réel critique).
 */
export function useDevices() {
  const [devices, setDevices] = useState([]);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await authFetch("/api/devices");
      if (res.ok) setDevices(await res.json());
    } catch {
      // brain injoignable — on garde la dernière liste connue à l'écran
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const forget = useCallback(
    async (deviceId) => {
      await authFetch(`/api/devices/${deviceId}`, { method: "DELETE" });
      await refresh();
    },
    [refresh],
  );

  return { devices, loaded, refresh, forget };
}

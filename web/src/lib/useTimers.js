import { useCallback, useEffect, useState } from "react";
import { authFetch } from "./consoleAuth.js";

/**
 * Minuteurs & rappels (C1) — brain/timers.py est la source de vérité,
 * commune à toutes les Consoles. Sondé plutôt que poussé : un minuteur ne
 * change pas assez souvent pour justifier un canal WebSocket dédié, et
 * /ws/cards s'en charge déjà pour l'échéance elle-même (voir Hud.jsx).
 */
const POLL_MS = 1000;

export function useTimers() {
  const [timers, setTimers] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const res = await authFetch("/api/timers");
      if (res.ok) setTimers(await res.json());
    } catch {
      // brain injoignable — la liste reste celle du dernier sondage réussi
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const create = useCallback(
    async (duration, label) => {
      const res = await authFetch("/api/timers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration, label }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "durée incomprise");
      await refresh();
      return data;
    },
    [refresh],
  );

  const cancel = useCallback(
    async (id) => {
      await authFetch(`/api/timers/${id}`, { method: "DELETE" });
      await refresh();
    },
    [refresh],
  );

  return { timers, create, cancel };
}

/** « 1:05:30 » au-delà d'une heure, « 05:30 » sinon — même format que le
 * chip du HUD Qt desktop (agents/desktop/services/timers.py). */
export function formatCountdown(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

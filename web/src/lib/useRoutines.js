import { useCallback, useEffect, useState } from "react";
import { authFetch } from "./consoleAuth.js";

const POLL_MS = 2000;

export function useRoutines() {
  const [routines, setRoutines] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const res = await authFetch("/api/routines");
      if (res.ok) setRoutines(await res.json());
    } catch {
      // brain injoignable — on garde la dernière liste connue
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const create = useCallback(
    async (name, steps) => {
      const res = await authFetch("/api/routines", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, steps }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "échec de la création");
      }
      await refresh();
    },
    [refresh],
  );

  const remove = useCallback(
    async (id) => {
      await authFetch(`/api/routines/${id}`, { method: "DELETE" });
      await refresh();
    },
    [refresh],
  );

  const run = useCallback(
    async (id) => {
      await authFetch(`/api/routines/${id}/run`, { method: "POST" });
      await refresh();
    },
    [refresh],
  );

  return { routines, create, remove, run };
}

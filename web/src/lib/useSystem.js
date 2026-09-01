import { useCallback, useEffect, useState } from "react";
import { authFetch } from "./consoleAuth.js";

/**
 * Les trois choses que le brain sait de lui-même et que la Console
 * n'exposait pas : ce qu'il a coûté, ce qu'il retient, dans quel mode il
 * est. Tout existait déjà côté serveur (data/usage.json, memory.json,
 * modes.json) mais n'était lisible que sur le HUD Qt du PC fixe.
 *
 * Pas de polling : ces données ne bougent qu'à l'occasion d'une action.
 * On charge à l'ouverture et on rafraîchit après chaque écriture.
 */
async function getJson(url) {
  const res = await authFetch(url);
  if (!res.ok) throw new Error(`${url} : ${res.status}`);
  return res.json();
}

async function sendJson(url, method, body) {
  const res = await authFetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "échec de l'opération");
  return data;
}

export function useUsage() {
  const [usage, setUsage] = useState(null);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try {
      setUsage(await getJson("/api/usage"));
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { usage, error, refresh };
}

export function useMemoryFacts() {
  const [facts, setFacts] = useState([]);
  const [lastUpdated, setLastUpdated] = useState("");
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await getJson("/api/memory");
      setFacts(data.facts || []);
      setLastUpdated(data.last_updated || "");
    } catch {
      // brain injoignable — on garde la dernière liste connue
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const add = useCallback(
    async (fact) => {
      const data = await sendJson("/api/memory", "POST", { fact });
      await refresh();
      return data;
    },
    [refresh],
  );

  const update = useCallback(
    async (index, fact) => {
      await sendJson(`/api/memory/${index}`, "PUT", { fact });
      await refresh();
    },
    [refresh],
  );

  const remove = useCallback(
    async (index) => {
      await sendJson(`/api/memory/${index}`, "DELETE");
      await refresh();
    },
    [refresh],
  );

  return { facts, lastUpdated, loaded, add, update, remove, refresh };
}

export function useModes() {
  const [modes, setModes] = useState([]);
  const [current, setCurrent] = useState(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await getJson("/api/modes");
      setModes(data.modes || []);
      setCurrent(data.current || null);
    } catch {
      // idem : le dernier état connu vaut mieux qu'un écran vide
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const activate = useCallback(
    async (modeId) => {
      const data = await sendJson("/api/modes/current", "POST", { mode_id: modeId });
      await refresh();
      return data.mode;
    },
    [refresh],
  );

  return { modes, current, loaded, activate, refresh };
}

export function useConversationLog(limit = 60) {
  const [entries, setEntries] = useState([]);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setEntries(await getJson(`/api/conversations?limit=${limit}`));
    } catch {
      // journal absent au premier lancement — liste vide, pas une erreur
    } finally {
      setLoaded(true);
    }
  }, [limit]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { entries, loaded, refresh };
}

/** Cartes passées (au-delà des 30 gardées en mémoire par useCardFeed) —
 * relit le journal disque du brain (brain/cards.py::history). Les captures
 * d'écran y perdent leur image (jamais écrite sur disque), le Fallback
 * générique des renderers de carte l'affiche sans planter pour autant. */
export function useCardHistory(limit = 100) {
  const [entries, setEntries] = useState([]);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setEntries(await getJson(`/api/cards/history?limit=${limit}`));
    } catch {
      // journal absent au premier lancement — liste vide, pas une erreur
    } finally {
      setLoaded(true);
    }
  }, [limit]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { entries, loaded, refresh };
}

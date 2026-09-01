import { useCallback, useEffect, useState } from "react";
import { onAuthRequired, setConsoleToken } from "./consoleAuth.js";

/** Purement réactif au 401 du brain (authFetch/ws) — pas de vérification
 * proactive au chargement, voir consoleAuth.js. Si CONSOLE_PASSWORD n'est
 * pas défini côté brain (dev local), cet écran n'apparaît jamais. */
export function useConsoleAuth() {
  const [needsAuth, setNeedsAuth] = useState(false);

  useEffect(() => onAuthRequired(() => setNeedsAuth(true)), []);

  /** Valide le mot de passe contre une route authentifiée (/api/devices,
   * pas /api/health qui reste ouvert sans jeton) avant de fermer l'écran —
   * sinon un mauvais mot de passe et un brain injoignable produisaient tous
   * les deux un écran vide sans message. Renvoie "ok", "rejected" (401,
   * mauvais mot de passe) ou "unreachable" (brain injoignable). */
  const login = useCallback(async (password) => {
    const token = password.trim();
    let res;
    try {
      res = await fetch("/api/devices", { headers: { Authorization: `Bearer ${token}` } });
    } catch {
      return "unreachable";
    }
    if (res.status === 401) return "rejected";
    if (!res.ok) return "unreachable";
    setConsoleToken(token);
    setNeedsAuth(false);
    return "ok";
  }, []);

  return { needsAuth, login };
}

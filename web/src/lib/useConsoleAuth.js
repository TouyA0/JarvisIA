import { useCallback, useEffect, useState } from "react";
import { onAuthRequired, setConsoleToken } from "./consoleAuth.js";

/** Purement réactif au 401 du brain (authFetch/ws) — pas de vérification
 * proactive au chargement, voir consoleAuth.js. Si CONSOLE_PASSWORD n'est
 * pas défini côté brain (dev local), cet écran n'apparaît jamais. */
export function useConsoleAuth() {
  const [needsAuth, setNeedsAuth] = useState(false);

  useEffect(() => onAuthRequired(() => setNeedsAuth(true)), []);

  /** Échange le mot de passe contre un jeton de session via POST
   * /api/session (P4) — seul ce jeton est ensuite gardé (voir
   * consoleAuth.js) ; le mot de passe ne transite qu'une fois, dans ce
   * corps JSON, jamais en Bearer ni dans une URL de WebSocket. Renvoie
   * "ok", "rejected" (401, mauvais mot de passe), "locked" (429, trop de
   * tentatives) ou "unreachable" (brain injoignable). */
  const login = useCallback(async (password) => {
    let res;
    try {
      res = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: password.trim() }),
      });
    } catch {
      return "unreachable";
    }
    if (res.status === 401) return "rejected";
    if (res.status === 429) return "locked";
    if (!res.ok) return "unreachable";
    const { token } = await res.json();
    setConsoleToken(token);
    setNeedsAuth(false);
    return "ok";
  }, []);

  return { needsAuth, login };
}

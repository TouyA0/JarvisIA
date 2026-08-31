import { useCallback, useEffect, useState } from "react";
import { onAuthRequired, setConsoleToken } from "./consoleAuth.js";

/** Purement réactif au 401 du brain (authFetch/ws) — pas de vérification
 * proactive au chargement, voir consoleAuth.js. Si CONSOLE_PASSWORD n'est
 * pas défini côté brain (dev local), cet écran n'apparaît jamais. */
export function useConsoleAuth() {
  const [needsAuth, setNeedsAuth] = useState(false);

  useEffect(() => onAuthRequired(() => setNeedsAuth(true)), []);

  const login = useCallback((password) => {
    setConsoleToken(password.trim());
    setNeedsAuth(false);
  }, []);

  return { needsAuth, login };
}

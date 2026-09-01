import { useCallback, useEffect, useState } from "react";
import { authFetch } from "./consoleAuth.js";

const POLL_MS = 3000;

export function useIntegrations() {
  const [accounts, setAccounts] = useState([]);
  const [googleSettings, setGoogleSettings] = useState({ configured: false, source: null, client_id: null });

  const refresh = useCallback(async () => {
    try {
      const [accountsRes, settingsRes] = await Promise.all([
        authFetch("/api/integrations"),
        authFetch("/api/integrations/google/settings"),
      ]);
      if (accountsRes.ok) setAccounts(await accountsRes.json());
      if (settingsRes.ok) setGoogleSettings(await settingsRes.json());
    } catch {
      // brain injoignable — on garde la dernière liste connue
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  // Le callback OAuth (brain/server.py::google_callback) prévient cet
  // onglet via postMessage une fois la connexion terminée — plus réactif
  // que d'attendre le prochain poll, et ça marche même si l'onglet popup
  // se ferme avant.
  useEffect(() => {
    function onMessage(event) {
      if (event.data && typeof event.data === "object" && "jarvisIntegration" in event.data) {
        refresh();
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [refresh]);

  const connectGoogle = useCallback(async () => {
    const res = await authFetch("/api/integrations/google/auth-url");
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Google Calendar non configuré");
    }
    const { url } = await res.json();
    window.open(url, "jarvis-google-auth", "width=480,height=680");
  }, []);

  const remove = useCallback(
    async (id) => {
      await authFetch(`/api/integrations/${id}`, { method: "DELETE" });
      await refresh();
    },
    [refresh],
  );

  const saveGoogleSettings = useCallback(
    async (clientId, clientSecret) => {
      const res = await authFetch("/api/integrations/google/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "échec de l'enregistrement");
      }
      await refresh();
    },
    [refresh],
  );

  const clearGoogleSettings = useCallback(async () => {
    await authFetch("/api/integrations/google/settings", { method: "DELETE" });
    await refresh();
  }, [refresh]);

  return { accounts, connectGoogle, remove, googleSettings, saveGoogleSettings, clearGoogleSettings };
}

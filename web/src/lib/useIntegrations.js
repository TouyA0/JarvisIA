import { useCallback, useEffect, useState } from "react";
import { authFetch } from "./consoleAuth.js";

const POLL_MS = 3000;

export function useIntegrations() {
  const [accounts, setAccounts] = useState([]);
  const [googleSettings, setGoogleSettings] = useState({ configured: false, source: null, client_id: null });
  const [zohoSettings, setZohoSettings] = useState({ configured: false, client_id: null, region: null });
  const [spotifySettings, setSpotifySettings] = useState({ configured: false, client_id: null });

  const refresh = useCallback(async () => {
    try {
      const [accountsRes, googleRes, zohoRes, spotifyRes] = await Promise.all([
        authFetch("/api/integrations"),
        authFetch("/api/integrations/google/settings"),
        authFetch("/api/integrations/zoho/settings"),
        authFetch("/api/integrations/spotify/settings"),
      ]);
      if (accountsRes.ok) setAccounts(await accountsRes.json());
      if (googleRes.ok) setGoogleSettings(await googleRes.json());
      if (zohoRes.ok) setZohoSettings(await zohoRes.json());
      if (spotifyRes.ok) setSpotifySettings(await spotifyRes.json());
    } catch {
      // brain injoignable — on garde la dernière liste connue
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  // Le callback OAuth (brain/server.py::google_callback / zoho_callback)
  // prévient cet onglet via postMessage une fois la connexion terminée —
  // plus réactif que d'attendre le prochain poll, et ça marche même si
  // l'onglet popup se ferme avant.
  useEffect(() => {
    function onMessage(event) {
      if (event.data && typeof event.data === "object" && "jarvisIntegration" in event.data) {
        refresh();
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [refresh]);

  const connectGoogle = useCallback(async (service = "google_calendar") => {
    const res = await authFetch(`/api/integrations/google/auth-url?service=${encodeURIComponent(service)}`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Google non configuré");
    }
    const { url } = await res.json();
    window.open(url, "jarvis-google-auth", "width=480,height=680");
  }, []);

  const connectZoho = useCallback(async (service = "zoho_mail") => {
    const res = await authFetch(`/api/integrations/zoho/auth-url?service=${encodeURIComponent(service)}`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Zoho non configuré");
    }
    const { url } = await res.json();
    window.open(url, "jarvis-zoho-auth", "width=480,height=680");
  }, []);

  const connectSpotify = useCallback(async () => {
    const res = await authFetch("/api/integrations/spotify/auth-url");
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Spotify non configuré");
    }
    const { url } = await res.json();
    window.open(url, "jarvis-spotify-auth", "width=480,height=680");
  }, []);

  // Jellyfin : pas d'OAuth (serveur perso), un seul aller-retour avec la
  // clé API directement — voir brain/server.py::connect_jellyfin.
  const connectJellyfin = useCallback(
    async (baseUrl, apiKey, username) => {
      const res = await authFetch("/api/integrations/jellyfin/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, username: username || undefined }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "échec de la connexion");
      }
      await refresh();
    },
    [refresh],
  );

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

  const saveZohoSettings = useCallback(
    async (clientId, clientSecret, region) => {
      const res = await authFetch("/api/integrations/zoho/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_id: clientId, client_secret: clientSecret, region }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "échec de l'enregistrement");
      }
      await refresh();
    },
    [refresh],
  );

  const clearZohoSettings = useCallback(async () => {
    await authFetch("/api/integrations/zoho/settings", { method: "DELETE" });
    await refresh();
  }, [refresh]);

  const saveSpotifySettings = useCallback(
    async (clientId, clientSecret) => {
      const res = await authFetch("/api/integrations/spotify/settings", {
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

  const clearSpotifySettings = useCallback(async () => {
    await authFetch("/api/integrations/spotify/settings", { method: "DELETE" });
    await refresh();
  }, [refresh]);

  return {
    accounts, remove,
    connectGoogle, googleSettings, saveGoogleSettings, clearGoogleSettings,
    connectZoho, zohoSettings, saveZohoSettings, clearZohoSettings,
    connectSpotify, spotifySettings, saveSpotifySettings, clearSpotifySettings,
    connectJellyfin,
  };
}

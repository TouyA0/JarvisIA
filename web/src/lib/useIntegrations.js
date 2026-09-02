import { useCallback, useEffect, useState } from "react";
import { authFetch } from "./consoleAuth.js";

const POLL_MS = 3000;

export function useIntegrations() {
  const [accounts, setAccounts] = useState([]);
  // Santé des comptes (C7) : jamais dans le poll rapide ci-dessous — sonder
  // Google/Zoho/Spotify/Jellyfin/HA toutes les 3s serait à la fois inutile
  // (le brain la met en cache 5 min de toute façon) et malpoli envers ces
  // fournisseurs. Un seul chargement au montage ; `checkAccountHealth` pour
  // forcer un compte précis (bouton « Vérifier » d'une carte).
  const [health, setHealth] = useState({});
  const [googleSettings, setGoogleSettings] = useState({ configured: false, source: null, client_id: null });
  const [zohoSettings, setZohoSettings] = useState({ configured: false, client_id: null, region: null });
  const [spotifySettings, setSpotifySettings] = useState({ configured: false, client_id: null });
  const [tisseoSettings, setTisseoSettings] = useState({ configured: false });
  const [orsSettings, setOrsSettings] = useState({ configured: false });
  const [braveSettings, setBraveSettings] = useState({ configured: false });
  const [tvSettings, setTvSettings] = useState({ configured: false, host: null });

  const refresh = useCallback(async () => {
    try {
      const [accountsRes, googleRes, zohoRes, spotifyRes, tisseoRes, orsRes, braveRes, tvRes] = await Promise.all([
        authFetch("/api/integrations"),
        authFetch("/api/integrations/google/settings"),
        authFetch("/api/integrations/zoho/settings"),
        authFetch("/api/integrations/spotify/settings"),
        authFetch("/api/integrations/tisseo/settings"),
        authFetch("/api/integrations/ors/settings"),
        authFetch("/api/integrations/brave/settings"),
        authFetch("/api/integrations/tv/settings"),
      ]);
      if (accountsRes.ok) setAccounts(await accountsRes.json());
      if (googleRes.ok) setGoogleSettings(await googleRes.json());
      if (zohoRes.ok) setZohoSettings(await zohoRes.json());
      if (spotifyRes.ok) setSpotifySettings(await spotifyRes.json());
      if (tisseoRes.ok) setTisseoSettings(await tisseoRes.json());
      if (orsRes.ok) setOrsSettings(await orsRes.json());
      if (braveRes.ok) setBraveSettings(await braveRes.json());
      if (tvRes.ok) setTvSettings(await tvRes.json());
    } catch {
      // brain injoignable — on garde la dernière liste connue
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const refreshHealth = useCallback(async () => {
    try {
      const res = await authFetch("/api/integrations/health");
      if (res.ok) setHealth(await res.json());
    } catch {
      // brain injoignable — on garde le dernier état connu
    }
  }, []);

  useEffect(() => {
    refreshHealth();
  }, [refreshHealth]);

  const checkAccountHealth = useCallback(async (id) => {
    const res = await authFetch(`/api/integrations/${id}/health`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    setHealth((prev) => ({ ...prev, [id]: data }));
    return data;
  }, []);

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

  // Home Assistant : pas d'OAuth, token longue durée direct — voir
  // brain/server.py::connect_home_assistant.
  const connectHomeAssistant = useCallback(
    async (baseUrl, token) => {
      const res = await authFetch("/api/integrations/home_assistant/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: baseUrl, token }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "échec de la connexion");
      }
      await refresh();
    },
    [refresh],
  );

  // Tisséo : pas d'OAuth, enregistre un arrêt favori par nom (résolu côté
  // brain) — voir brain/server.py::connect_tisseo.
  const connectTisseo = useCallback(
    async (stop) => {
      const res = await authFetch("/api/integrations/tisseo/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stop }),
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

  const saveTisseoSettings = useCallback(
    async (apiKey) => {
      const res = await authFetch("/api/integrations/tisseo/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "échec de l'enregistrement");
      }
      await refresh();
    },
    [refresh],
  );

  const clearTisseoSettings = useCallback(async () => {
    await authFetch("/api/integrations/tisseo/settings", { method: "DELETE" });
    await refresh();
  }, [refresh]);

  const saveOrsSettings = useCallback(
    async (apiKey) => {
      const res = await authFetch("/api/integrations/ors/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "échec de l'enregistrement");
      }
      await refresh();
    },
    [refresh],
  );

  const clearOrsSettings = useCallback(async () => {
    await authFetch("/api/integrations/ors/settings", { method: "DELETE" });
    await refresh();
  }, [refresh]);

  const saveHomeAddress = useCallback(
    async (address) => {
      const res = await authFetch("/api/integrations/ors/home-address", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "échec de l'enregistrement");
      }
      await refresh();
    },
    [refresh],
  );

  const clearHomeAddress = useCallback(async () => {
    await authFetch("/api/integrations/ors/home-address", { method: "DELETE" });
    await refresh();
  }, [refresh]);

  const saveBraveSettings = useCallback(
    async (apiKey) => {
      const res = await authFetch("/api/integrations/brave/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "échec de l'enregistrement");
      }
      await refresh();
    },
    [refresh],
  );

  const clearBraveSettings = useCallback(async () => {
    await authFetch("/api/integrations/brave/settings", { method: "DELETE" });
    await refresh();
  }, [refresh]);

  // Télé (T2) : pas de "connexion" à proprement parler (ANDROID_TV_HOST
  // reste .env-only, voir android_tv.py) — juste une sonde forcée pour que
  // le bouton « Tester la connexion » réponde autre chose qu'un silence.
  const testTvConnection = useCallback(async () => {
    const res = await authFetch("/api/integrations/tv/health", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "échec du test");
    setHealth((prev) => ({ ...prev, android_tv: data }));
    if (data.healthy === false) throw new Error(data.error || "télé injoignable");
    return data;
  }, []);

  return {
    accounts, remove,
    health, refreshHealth, checkAccountHealth,
    connectGoogle, googleSettings, saveGoogleSettings, clearGoogleSettings,
    connectZoho, zohoSettings, saveZohoSettings, clearZohoSettings,
    connectSpotify, spotifySettings, saveSpotifySettings, clearSpotifySettings,
    connectJellyfin,
    connectHomeAssistant,
    connectTisseo, tisseoSettings, saveTisseoSettings, clearTisseoSettings,
    orsSettings, saveOrsSettings, clearOrsSettings, saveHomeAddress, clearHomeAddress,
    braveSettings, saveBraveSettings, clearBraveSettings,
    tvSettings, testTvConnection,
  };
}

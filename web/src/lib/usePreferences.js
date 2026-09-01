import { useCallback, useEffect, useState } from "react";
import { authFetch } from "./consoleAuth.js";

/**
 * Réglages généraux (C6 / F26) — jusqu'ici uniquement dans `.env`, à
 * éditer et redémarrer le brain pour voir l'effet (brain/preferences.py).
 */
export function usePreferences() {
  const [weather, setWeatherState] = useState(null);
  const [proactive, setProactiveState] = useState(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await authFetch("/api/preferences");
      if (res.ok) {
        const data = await res.json();
        setWeatherState(data.weather);
        setProactiveState(data.proactive);
      }
    } catch {
      // brain injoignable — on garde les derniers réglages connus
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setWeather = useCallback(async (city, lat, lon) => {
    const res = await authFetch("/api/preferences/weather", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ city, lat, lon }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "échec de l'enregistrement");
    setWeatherState(data);
    return data;
  }, []);

  const setProactive = useCallback(async (values) => {
    const res = await authFetch("/api/preferences/proactive", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "échec de l'enregistrement");
    setProactiveState(data);
    return data;
  }, []);

  return { weather, proactive, loaded, setWeather, setProactive, refresh };
}

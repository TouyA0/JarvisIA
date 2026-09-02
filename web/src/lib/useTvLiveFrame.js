import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch } from "./consoleAuth.js";

// Rythme du direct sur la télé (C6/C9) — même compromis qu'ailleurs (voir
// useFocusDevice.js côté PC) : android_tv.screenshot() fait un screencap +
// pull ADB (plus lourd qu'un JPEG pyautogui), 800 ms reste un bon équilibre
// entre fluidité perçue et requêtes qui s'empilent.
const TV_STREAM_INTERVAL_MS = 800;

/**
 * Polling du flux « direct » de la télé (POST /api/tv/stream/frame,
 * brain/server.py, réutilise android_tv.screenshot()) — extrait en hook
 * partagé entre la carte "tv" (cards/renderers.jsx) et la télécommande
 * dédiée (TvRemote.jsx, C9) pour ne pas dupliquer la même boucle deux fois.
 */
export function useTvLiveFrame() {
  const [live, setLive] = useState(false);
  const [frame, setFrame] = useState(null);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);
  const inFlightRef = useRef(false);

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setLive(false);
  }, []);

  const start = useCallback(() => {
    if (timerRef.current) return;
    setError(null);
    setLive(true);

    async function tick() {
      if (inFlightRef.current) return; // une image encore en vol : on saute ce tour plutôt que d'empiler
      inFlightRef.current = true;
      try {
        const res = await authFetch("/api/tv/stream/frame", { method: "POST" });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.detail || "échec de la capture");
        if (body.image_b64) setFrame(body);
      } catch (e) {
        setError(e.message);
        stop();
      } finally {
        inFlightRef.current = false;
      }
    }

    tick();
    timerRef.current = setInterval(tick, TV_STREAM_INTERVAL_MS);
  }, [stop]);

  // Quitter l'écran (carte écartée, télécommande démontée) ne doit jamais
  // laisser un intervalle tourner en tâche de fond à réclamer des images.
  useEffect(() => stop, [stop]);

  return { live, frame, error, start, stop };
}

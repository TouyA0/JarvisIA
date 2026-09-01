import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch } from "./consoleAuth.js";

const POLL_MS = 3000;
// Rythme du direct : compromis entre "ça bouge" et le coût réel d'une
// capture d'écran répétée côté agent (grab + JPEG + aller-retour réseau).
// En dessous, les requêtes s'empilent plus vite qu'elles ne répondent.
const STREAM_INTERVAL_MS = 800;

/**
 * État d'un appareil précis pour l'écran Focus : infos, journal
 * d'activité, l'action « capturer » (dispatch réel vers l'agent — voir
 * brain/server.py POST /api/devices/{id}/dispatch, Phase 3), et le
 * partage d'écran live (POST .../stream/frame, §4 V1 de la roadmap).
 */
export function useFocusDevice(deviceId) {
  const [device, setDevice] = useState(null);
  const [activityLog, setActivityLog] = useState([]);
  const [screenshot, setScreenshot] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const [liveFrame, setLiveFrame] = useState(null);
  const [live, setLive] = useState(false);
  const [liveError, setLiveError] = useState(null);
  const liveTimerRef = useRef(null);
  const liveInFlightRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!deviceId) return;
    try {
      const [devRes, actRes] = await Promise.all([
        authFetch(`/api/devices/${deviceId}`),
        authFetch(`/api/devices/${deviceId}/activity`),
      ]);
      if (devRes.ok) setDevice(await devRes.json());
      if (actRes.ok) setActivityLog(await actRes.json());
    } catch {
      // brain injoignable — on garde le dernier état connu
    }
  }, [deviceId]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const dispatch = useCallback(
    async (tool, args = {}) => {
      setBusy(true);
      setError(null);
      try {
        const res = await authFetch(`/api/devices/${deviceId}/dispatch`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tool, args }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "échec");
        if (!data.ok) throw new Error(data.error || "l'appareil a signalé une erreur");
        await refresh();
        return data.result;
      } catch (e) {
        setError(e.message);
        return null;
      } finally {
        setBusy(false);
      }
    },
    [deviceId, refresh],
  );

  const capture = useCallback(async () => {
    const result = await dispatch("take_screenshot");
    if (result?.image_b64) setScreenshot(result.image_b64);
    // Rendu à l'appelant : la vue Focus a besoin de savoir si la capture a
    // abouti pour confirmer (ou non) à l'écran — `dispatch` renvoie null
    // en cas d'échec, et `error` porte déjà le détail.
    return result?.image_b64 || null;
  }, [dispatch]);

  const lock = useCallback(
    () => dispatch("run_powershell", { command: "rundll32.exe user32.dll,LockWorkStation" }),
    [dispatch],
  );

  // Boucle de polling volontairement indépendante de `dispatch` : elle ne
  // doit ni activer `busy` (qui désactiverait les autres boutons de Focus
  // à chaque image) ni passer par activity.record côté brain (des dizaines
  // d'images par minute noieraient le vrai journal d'activité).
  const stopLive = useCallback(() => {
    if (liveTimerRef.current) {
      clearInterval(liveTimerRef.current);
      liveTimerRef.current = null;
    }
    setLive(false);
  }, []);

  const startLive = useCallback(() => {
    if (liveTimerRef.current || !deviceId) return;
    setLiveError(null);
    setLive(true);

    async function tick() {
      if (liveInFlightRef.current) return; // une image encore en vol : on saute ce tour plutôt que d'empiler
      liveInFlightRef.current = true;
      try {
        const res = await authFetch(`/api/devices/${deviceId}/stream/frame`, { method: "POST" });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || "échec de la capture");
        if (data.image_b64) setLiveFrame(data.image_b64);
      } catch (e) {
        setLiveError(e.message);
        stopLive();
      } finally {
        liveInFlightRef.current = false;
      }
    }

    tick();
    liveTimerRef.current = setInterval(tick, STREAM_INTERVAL_MS);
  }, [deviceId, stopLive]);

  // Filet de sécurité : quitter Focus (démontage) ou changer d'appareil ne
  // doit jamais laisser un intervalle tourner en tâche de fond à réclamer
  // des images à un agent que plus personne ne regarde.
  useEffect(() => stopLive, [deviceId, stopLive]);

  return {
    device, activityLog, screenshot, busy, error, capture, lock, dispatch,
    liveFrame, live, liveError, startLive, stopLive,
  };
}

import { useCallback, useEffect, useState } from "react";
import { authFetch } from "./consoleAuth.js";

const POLL_MS = 3000;

/**
 * État d'un appareil précis pour l'écran Focus : infos, journal
 * d'activité, et l'action « capturer » (dispatch réel vers l'agent —
 * voir brain/server.py POST /api/devices/{id}/dispatch, Phase 3).
 */
export function useFocusDevice(deviceId) {
  const [device, setDevice] = useState(null);
  const [activityLog, setActivityLog] = useState([]);
  const [screenshot, setScreenshot] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

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
  }, [dispatch]);

  const lock = useCallback(() => dispatch("run_powershell", { command: "rundll32.exe user32.dll,LockWorkStation" }), [dispatch]);

  return { device, activityLog, screenshot, busy, error, capture, lock };
}

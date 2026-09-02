import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch, reportAuthFailure, wsAuthQuery } from "./consoleAuth.js";

/**
 * Qui « a la main » pour parler à voix haute, en direct — évite que deux
 * appareils lisent leur réponse audio en même temps quand on ouvre le
 * téléphone pendant que le PC répond encore (ou l'inverse). Dernier
 * appareil à avoir entendu « Jarvis » (ou tapé une commande) gagne, voir
 * brain/presence.py : seul l'appareil actif joue l'audio de synthèse, les
 * autres continuent d'afficher le texte normalement.
 *
 * Identité stable de CE navigateur, générée une fois et gardée en
 * localStorage — pas de compte, juste de quoi se distinguer des autres
 * onglets/appareils dans l'arbitrage.
 */
const DEVICE_ID_KEY = "jarvis.webDeviceId";
const AUTH_CLOSE_CODE = 4401;
const RECONNECT_MS = 2000;

export function getWebDeviceId() {
  let id = "";
  try {
    id = localStorage.getItem(DEVICE_ID_KEY) || "";
  } catch {
    // stockage indisponible (navigation privée stricte) — id éphémère,
    // tant pis pour l'arbitrage entre deux rechargements de cette session
  }
  if (!id) {
    id = `web-${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
    try {
      localStorage.setItem(DEVICE_ID_KEY, id);
    } catch {
      // idem
    }
  }
  return id;
}

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/cards${wsAuthQuery()}`;
}

export function usePresence() {
  const [presence, setPresence] = useState({ device: null, label: null, since: 0 });
  const presenceRef = useRef(presence);
  presenceRef.current = presence;

  useEffect(() => {
    let cancelled = false;
    let ws = null;

    (async () => {
      try {
        const res = await authFetch("/api/presence");
        if (res.ok && !cancelled) setPresence(await res.json());
      } catch {
        // brain injoignable — pas d'arbitrage possible pour l'instant,
        // chaque appareil restera libre de parler comme avant
      }
    })();

    function connect() {
      if (cancelled) return;
      ws = new WebSocket(wsUrl());
      ws.onclose = (event) => {
        if (event.code === AUTH_CLOSE_CODE) reportAuthFailure();
        if (!cancelled) setTimeout(connect, RECONNECT_MS);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.kind === "presence") setPresence(msg);
      };
    }

    connect();
    return () => {
      cancelled = true;
      ws?.close();
    };
  }, []);

  /** À consulter juste avant de jouer l'audio de synthèse — pas avant
   * d'afficher le texte, qui doit toujours apparaître. */
  const isActive = useCallback((deviceId) => {
    const dev = presenceRef.current.device;
    return dev == null || dev === deviceId;
  }, []);

  const activate = useCallback(async (deviceId, label) => {
    try {
      const res = await authFetch("/api/presence/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device: deviceId, label }),
      });
      if (res.ok) setPresence(await res.json());
    } catch {
      // brain injoignable — ce tour ne participera pas à l'arbitrage
    }
  }, []);

  return { presence, isActive, activate };
}

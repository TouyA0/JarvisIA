import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch, reportAuthFailure, wsAuthQuery } from "./consoleAuth.js";

/**
 * Flux de diffusion du brain (`/ws/cards`) : les cartes que Jarvis
 * affiche, et les tours de conversation, **quelle que soit leur origine**.
 *
 * C'est ce qui distingue le pupitre d'une fenêtre de chat : une question
 * posée à voix haute au PC fixe fait apparaître l'agenda ici, sur l'écran
 * resté allumé à côté, sans que cette Console ait rien demandé.
 *
 * `/api/cards` au démarrage pour ne pas ouvrir sur un pupitre vide juste
 * après avoir parlé ; le WebSocket prend le relais pour la suite.
 */
const AUTH_CLOSE_CODE = 4401;
const RECONNECT_MS = 2000;

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/cards${wsAuthQuery()}`;
}

export function useCardFeed() {
  const [cards, setCards] = useState([]);
  const [lastExchange, setLastExchange] = useState(null);
  const [connected, setConnected] = useState(false);
  const dismissedRef = useRef(new Set());

  const addCard = useCallback((card) => {
    if (dismissedRef.current.has(card.id)) return;
    setCards((list) => [card, ...list.filter((c) => c.id !== card.id)].slice(0, 30));
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await authFetch("/api/cards?limit=30");
        if (!res.ok || cancelled) return;
        const recent = await res.json();
        // Le brain les renvoie de la plus ancienne à la plus récente ; le
        // pupitre affiche la dernière en premier.
        setCards(recent.reverse());
      } catch {
        // brain injoignable — le pupitre démarre vide, le WebSocket
        // rattrapera dès qu'il répond.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let ws = null;

    function connect() {
      if (cancelled) return;
      ws = new WebSocket(wsUrl());
      ws.onopen = () => setConnected(true);
      ws.onclose = (event) => {
        setConnected(false);
        if (event.code === AUTH_CLOSE_CODE) reportAuthFailure();
        if (!cancelled) setTimeout(connect, RECONNECT_MS);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.kind === "card") addCard(msg.card);
        else if (msg.kind === "exchange") setLastExchange(msg);
      };
    }

    connect();
    return () => {
      cancelled = true;
      ws?.close();
    };
  }, [addCard]);

  /** Écarter une carte : purement local (l'écran de Monsieur, pas celui
   * des autres Consoles) — d'où le registre des identifiants écartés, qui
   * évite qu'un rechargement depuis /api/cards ne la fasse revenir. */
  const dismiss = useCallback((id) => {
    dismissedRef.current.add(id);
    setCards((list) => list.filter((c) => c.id !== id));
  }, []);

  const clearAll = useCallback(async () => {
    setCards([]);
    await authFetch("/api/cards", { method: "DELETE" });
  }, []);

  return { cards, lastExchange, connected, dismiss, clearAll };
}

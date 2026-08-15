import { useCallback, useEffect, useRef, useState } from "react";

// En dev, Vite proxifie /ws vers le brain (voir vite.config.js). En prod,
// brain/server.py sert web/dist depuis la même origine — même chemin marche
// dans les deux cas.
function wsUrl() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/chat`;
}

/**
 * Chat texte simple vers brain/server.py (/ws/chat). Pas de pilotage PC ici
 * — juste la conversation Ollama/Claude en streaming phrase par phrase
 * (voir docs/ROADMAP_MULTIDEVICE.md, Phase 2).
 */
export function useChat() {
  const wsRef = useRef(null);
  const [status, setStatus] = useState("connecting"); // connecting | online | offline
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;

    function connect() {
      if (cancelled) return;
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;
      setStatus("connecting");

      ws.onopen = () => setStatus("online");
      ws.onclose = () => {
        setStatus("offline");
        if (!cancelled) setTimeout(connect, 2000);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "chat.phrase") {
          setAnswer((prev) => (prev ? `${prev} ${msg.text}` : msg.text));
        } else if (msg.type === "chat.done") {
          setBusy(false);
        }
      };
    }

    connect();
    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
  }, []);

  const ask = useCallback((text) => {
    const trimmed = text.trim();
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !trimmed) return;
    setQuestion(trimmed);
    setAnswer("");
    setBusy(true);
    ws.send(JSON.stringify({ question: trimmed }));
  }, []);

  return { status, question, answer, busy, ask };
}

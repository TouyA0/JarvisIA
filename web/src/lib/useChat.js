import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch, reportAuthFailure, wsAuthQuery } from "./consoleAuth.js";

// En dev, Vite proxifie /ws vers le brain (voir vite.config.js). En prod,
// brain/server.py sert web/dist depuis la même origine — même chemin marche
// dans les deux cas.
function wsUrl() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/chat${wsAuthQuery()}`;
}

// Code de fermeture applicatif renvoyé par brain/server.py::ws_chat quand le
// token est absent/invalide — voir require_console_auth.
const AUTH_CLOSE_CODE = 4401;

// Assez pour retrouver le fil d'hier sans transformer l'ouverture de la
// Console en chargement de plusieurs centaines de messages.
const HISTORY_LIMIT = 40;

let messageSeq = 0;
const nextId = () => `m${++messageSeq}`;

/**
 * Conversation avec le brain (/ws/chat) : historique persistant + tour en
 * cours en streaming phrase par phrase, ou pilotage PC dispatché sur le
 * réseau quand la question ressemble à une commande (Phase 10).
 *
 * Change de forme par rapport à la version précédente, qui n'exposait
 * qu'un couple `question` / `answer` : la Console n'affichait donc qu'un
 * seul tour à la fois, et tout disparaissait au rafraîchissement de la
 * page alors que le brain journalisait déjà tout (data/logs/*.jsonl).
 * On expose maintenant une vraie liste de messages, amorcée avec
 * /api/conversations.
 */
export function useChat() {
  const wsRef = useRef(null);
  const [status, setStatus] = useState("connecting"); // connecting | online | offline
  const [messages, setMessages] = useState([]);
  const [activity, setActivity] = useState("");
  const [busy, setBusy] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  // Identifiant du message de Jarvis en cours de rédaction : les phrases
  // arrivent une par une, il faut les concaténer dans la même bulle.
  const pendingRef = useRef(null);

  // Écran actif (Console ou Hud) : relaie chaque phrase à la synthèse
  // vocale dès son arrivée, plutôt que d'attendre le bloc entier — voir
  // useVoice.js::speakPhrase. Assigné directement dans le corps du
  // composant par l'écran actif, comme setCommandHandler côté voix.
  const phraseHandlerRef = useRef(null);
  const doneHandlerRef = useRef(null);
  const setPhraseHandler = useCallback((fn) => {
    phraseHandlerRef.current = fn;
  }, []);
  const setDoneHandler = useCallback((fn) => {
    doneHandlerRef.current = fn;
  }, []);
  useEffect(() => {
    // Chaque message restauré porte `historical: true` : le Pupitre
    // (Hud.jsx) filtre sur ce flag pour ne montrer que ce qui se passe
    // maintenant, pas le fil d'hier — sans ça, il afficherait la dernière
    // réponse du journal comme si Jarvis venait de la prononcer.
    let cancelled = false;
    (async () => {
      try {
        const res = await authFetch(`/api/conversations?limit=${HISTORY_LIMIT}`);
        if (!res.ok || cancelled) return;
        const entries = await res.json();
        const restored = [];
        for (const e of entries) {
          const at = e.at ? Date.parse(e.at) : null;
          restored.push({ id: nextId(), role: "user", text: e.question, at, historical: true });
          restored.push({
            id: nextId(),
            role: "jarvis",
            text: e.answer,
            at,
            source: e.source,
            historical: true,
          });
        }
        // Concaténation plutôt que remplacement : un tour peut déjà avoir
        // eu lieu pendant le chargement (la voix est armée très tôt).
        setMessages((live) => [...restored, ...live]);
      } catch {
        // journal illisible ou brain injoignable — la conversation démarre
        // simplement vide, ce n'est pas une erreur à montrer.
      } finally {
        if (!cancelled) setHistoryLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    function connect() {
      if (cancelled) return;
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;
      setStatus("connecting");

      ws.onopen = () => setStatus("online");
      ws.onclose = (event) => {
        setStatus("offline");
        if (event.code === AUTH_CLOSE_CODE) reportAuthFailure();
        // Un tour en cours ne recevra jamais sa fin : on débloque la
        // saisie, sinon la Console reste figée sur « Réflexion… ».
        setBusy(false);
        setActivity("");
        if (pendingRef.current) {
          pendingRef.current = null;
          doneHandlerRef.current?.();
        }
        // Le prochain essai relira le token à jour (mis à jour entre-temps
        // si Monsieur vient de se reconnecter via AuthGate) — pas besoin de
        // traiter ce cas à part, la boucle de reconnexion suffit.
        if (!cancelled) setTimeout(connect, 2000);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "chat.phrase") {
          setActivity("");
          setMessages((list) =>
            list.map((m) =>
              m.id === pendingRef.current
                ? { ...m, text: m.text ? `${m.text} ${msg.text}` : msg.text, pending: true }
                : m,
            ),
          );
          phraseHandlerRef.current?.(msg.text);
        } else if (msg.type === "chat.status") {
          setActivity(msg.text || "");
        } else if (msg.type === "chat.done") {
          setMessages((list) =>
            list.map((m) =>
              m.id === pendingRef.current ? { ...m, pending: false, source: msg.source } : m,
            ),
          );
          pendingRef.current = null;
          setActivity("");
          setBusy(false);
          doneHandlerRef.current?.();
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
    // pendingRef non nul = un tour précédent n'a pas encore reçu son
    // chat.done. Sans ce garde-fou, le barge-in vocal (useVoice.js) peut
    // désormais envoyer une nouvelle commande pendant que la réponse
    // précédente streame encore — les chat.phrase restants du vieux tour
    // se retrouveraient concaténés dans la bulle du nouveau.
    if (!ws || ws.readyState !== WebSocket.OPEN || !trimmed || pendingRef.current) return false;

    const answerId = nextId();
    pendingRef.current = answerId;
    const at = Date.now();
    setMessages((list) => [
      ...list,
      { id: nextId(), role: "user", text: trimmed, at },
      { id: answerId, role: "jarvis", text: "", at, pending: true },
    ]);
    setActivity("");
    setBusy(true);
    ws.send(JSON.stringify({ question: trimmed }));
    return true;
  }, []);

  /** Dépôt d'un fichier image pour analyse (C9) — HTTP, pas le WebSocket :
   * pas de streaming côté brain/vision.py, une seule réponse. Même garde
   * de tour-en-cours que ask(), même forme de messages (bulle utilisateur
   * + bulle Jarvis en attente) pour rester cohérent dans le fil. */
  const uploadImage = useCallback(async (file, question) => {
    if (pendingRef.current) return false;
    const trimmed = (question || "").trim();
    const answerId = nextId();
    pendingRef.current = answerId;
    const at = Date.now();
    const imageUrl = URL.createObjectURL(file);
    setMessages((list) => [
      ...list,
      { id: nextId(), role: "user", text: trimmed || `Image jointe : ${file.name}`, at, imageUrl },
      { id: answerId, role: "jarvis", text: "", at, pending: true },
    ]);
    setActivity("Analyse de l'image…");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      if (trimmed) form.append("question", trimmed);
      const res = await authFetch("/api/vision/analyze", { method: "POST", body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "analyse impossible");
      setMessages((list) =>
        list.map((m) => (m.id === answerId ? { ...m, text: data.text, pending: false, source: "claude-vision" } : m)),
      );
    } catch (e) {
      setMessages((list) =>
        list.map((m) => (m.id === answerId ? { ...m, text: e.message || "Analyse impossible.", pending: false } : m)),
      );
    } finally {
      pendingRef.current = null;
      setActivity("");
      setBusy(false);
    }
    return true;
  }, []);

  /** Vide le fil affiché. Le journal côté brain n'est pas touché — c'est
   * la mémoire de Jarvis, pas un historique de navigateur à effacer. */
  const clear = useCallback(() => {
    setMessages([]);
    pendingRef.current = null;
    setActivity("");
  }, []);

  return {
    status,
    messages,
    activity,
    busy,
    historyLoaded,
    ask,
    uploadImage,
    clear,
    setPhraseHandler,
    setDoneHandler,
  };
}

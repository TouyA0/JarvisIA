import { useEffect, useRef, useState } from "react";
import CardView from "./cards/CardView.jsx";
import Icon from "./ui/Icon.jsx";
import ModeSwitcher from "./ui/ModeSwitcher.jsx";
import { authFetch } from "../lib/consoleAuth.js";
import { useCardFeed } from "../lib/useCardFeed.js";
import { useChat } from "../lib/useChat.js";
import { useDevices } from "../lib/useDevices.js";
import { useVoice } from "../lib/useVoice.js";

/**
 * Le pupitre — écran d'accueil de la Console.
 *
 * Ce n'est volontairement pas une fenêtre de chat. Jarvis est d'abord une
 * présence : au repos, l'écran affiche l'heure, le mode en cours, l'état
 * de la maison. Quand on lui parle, il répond à voix haute *et* fait
 * apparaître ce qu'il a trouvé sous forme de cartes (agenda, mails,
 * capture d'écran…) — voir docs/ROADMAP_DISPLAY_INTEGRATIONS.md §2.
 *
 * Le fil de conversation complet existe toujours, mais comme un journal
 * consultable (vue Conversation), pas comme l'écran principal.
 *
 * Deux sources alimentent le pupitre :
 *   - le WebSocket de chat (`useChat`) pour ce que cette Console demande
 *     elle-même, avec la réponse en streaming ;
 *   - la diffusion (`useCardFeed`) pour tout le reste — y compris une
 *     question posée à voix haute au PC fixe, dont la réponse s'affiche
 *     ici sans que cette fenêtre ait rien envoyé.
 */

// Formulations choisies pour tomber dans les mots-clés de l'aiguilleur
// (agents/desktop/brain/router.py) : « musique », « mails », « agenda »…
// Une question mal formulée part en conversation pure et ne produit
// aucune carte, ce qui donnerait l'impression que le pupitre ne marche pas.
const SUGGESTIONS = [
  "Qu'est-ce que j'ai aujourd'hui ?",
  "Mes derniers mails",
  "Quelle musique joue en ce moment ?",
  "Capture l'écran du PC fixe",
];

const STAGE_LABELS = {
  standby: "En veille",
  listening: "À l'écoute",
  heard: "Je vous écoute",
  transcribing: "Transcription",
  thinking: "Analyse en cours",
  speaking: "Réponse",
};

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 10000);
    return () => clearInterval(id);
  }, []);
  return now;
}

/** Bandeau permanent : l'information qui a sa place à l'écran même quand
 * personne ne parle — c'est ce qui fait la différence entre un assistant
 * et une fenêtre de messagerie. */
function Ambient({ devicesOnline, connected }) {
  const now = useClock();
  return (
    <div className="hud-ambient">
      <span className="hud-clock">
        {now.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
      </span>
      <span className="hud-date">
        {now.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}
      </span>
      <span className="spacer" />
      <ModeSwitcher variant="chip" />
      <span className="hud-chip">
        {devicesOnline} appareil{devicesOnline > 1 ? "s" : ""} en ligne
      </span>
      <span className={`hud-chip ${connected ? "hud-chip--ok" : "hud-chip--off"}`}>
        {connected ? "liaison établie" : "liaison rompue"}
      </span>
    </div>
  );
}

/** Le réacteur et ce qui se dit autour. Occupe tout l'écran tant qu'aucune
 * carte n'est là, se replie en bandeau dès que le pupitre se remplit. */
function Stage({ state, question, answer, activity, compact }) {
  const busy = state === "thinking";
  return (
    <div className={`hud-stage${compact ? " hud-stage--compact" : ""}`}>
      <div className={`hud-reactor hud-reactor--${state}`} aria-hidden="true">
        <span className="hud-reactor-halo" />
        <span className="hud-reactor-ring hud-reactor-ring--outer" />
        <span className="hud-reactor-ring hud-reactor-ring--inner" />
        <span className="hud-reactor-core" />
      </div>

      <div className="hud-speech">
        <span className="hud-state" role="status">
          {STAGE_LABELS[state]}
          {activity && busy && <span className="hud-activity"> · {activity}</span>}
        </span>
        {question && <p className="hud-question">« {question} »</p>}
        {/* Au repos, l'écran ne reste pas muet : Jarvis se tient là. */}
        {state === "standby" && !question && !answer && (
          <p className="hud-answer hud-answer--idle">À votre disposition, Monsieur.</p>
        )}
        {busy && !answer ? (
          <p className="hud-answer hud-answer--pending">
            <span className="thinking">
              <span />
              <span />
              <span />
            </span>
          </p>
        ) : (
          answer && <p className="hud-answer">{answer}</p>
        )}
      </div>
    </div>
  );
}

function Composer({ online, busy, onSend, voice }) {
  const [value, setValue] = useState("");

  function submit(e) {
    e.preventDefault();
    const text = value.trim();
    if (!text || busy || !online) return;
    if (onSend(text)) setValue("");
  }

  const micState = voice.armed
    ? voice.status === "listening_command" || voice.status === "transcribing"
      ? "mic--active"
      : "mic--armed"
    : "";

  return (
    <form className="hud-composer" onSubmit={submit}>
      <button
        type="button"
        className={`mic mic--lg ${micState}`.trim()}
        onClick={() => (voice.armed ? voice.disarm() : voice.arm())}
        aria-pressed={voice.armed}
        aria-label={voice.armed ? "Couper l'écoute vocale" : "Activer l'écoute vocale"}
      >
        <Icon name="mic" size={22} />
      </button>

      <label className="sr-only" htmlFor="hud-input">
        Demander quelque chose à Jarvis
      </label>
      <input
        id="hud-input"
        className="hud-input"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={
          voice.armed ? "Dites « Jarvis », ou tapez ici…" : online ? "Demandez…" : "Brain injoignable"
        }
        disabled={!online}
      />
      <button
        type="submit"
        className="composer-send"
        disabled={!online || busy || !value.trim()}
        aria-label="Envoyer"
      >
        <Icon name="send" size={17} />
      </button>
    </form>
  );
}

export default function Hud() {
  const { status, messages, activity, busy, ask } = useChat({ withHistory: false });
  const { cards, lastExchange, connected, dismiss, clearAll } = useCardFeed();
  const { devices } = useDevices();

  const lastLocalQuestionRef = useRef("");
  const localTurnAtRef = useRef(0);
  const wasBusyRef = useRef(false);
  const lastWasVoiceRef = useRef(false);
  const [remote, setRemote] = useState(null);

  function handleVoiceCommand(text) {
    lastWasVoiceRef.current = true;
    voice.pause();
    send(text);
  }

  const voice = useVoice({ onCommand: handleVoiceCommand });

  function send(text) {
    lastLocalQuestionRef.current = text.trim();
    localTurnAtRef.current = Date.now();
    return ask(text);
  }

  // Un tour diffusé qui n'est pas le nôtre : Monsieur a parlé au PC fixe
  // (ou depuis une autre Console). On l'affiche à l'identique — c'est tout
  // l'intérêt d'un écran qui reste allumé dans la pièce.
  useEffect(() => {
    if (!lastExchange) return;
    if (lastExchange.question === lastLocalQuestionRef.current) return;
    setRemote(lastExchange);
  }, [lastExchange]);

  // Lecture à voix haute uniquement si la question venait de la voix : une
  // réponse à une question tapée ne doit pas se mettre à parler seule.
  const lastJarvis = [...messages].reverse().find((m) => m.role === "jarvis");
  const lastAnswerRef = useRef("");
  lastAnswerRef.current = lastJarvis?.text || "";
  useEffect(() => {
    if (wasBusyRef.current && !busy && lastWasVoiceRef.current) {
      lastWasVoiceRef.current = false;
      speakAnswer(lastAnswerRef.current, voice);
    }
    wasBusyRef.current = busy;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy]);

  const online = status === "online";
  const devicesOnline = devices.filter((d) => d.status === "online").length;

  // Qui parle en ce moment : notre propre tour tant qu'il est en cours ou
  // plus récent, sinon le dernier tour diffusé par ailleurs.
  const remoteIsNewer = remote && remote.at * 1000 > localTurnAtRef.current;
  const showRemote = !busy && remoteIsNewer;
  const question = showRemote ? remote.question : lastLocalQuestionRef.current;
  const answer = showRemote ? remote.answer : lastAnswerRef.current;

  let state = "standby";
  if (busy) state = "thinking";
  else if (voice.status === "transcribing") state = "transcribing";
  else if (voice.status === "listening_command" || voice.wakeWordHeard) state = "heard";
  else if (voice.status === "speaking") state = "speaking";
  else if (voice.armed) state = "listening";
  else if (answer) state = "speaking";

  const hasCards = cards.length > 0;

  return (
    <div className="hud">
      <Ambient devicesOnline={devicesOnline} connected={connected && online} />

      <div className="hud-body">
        <Stage
          state={state}
          question={question}
          answer={answer}
          activity={activity}
          compact={hasCards}
        />

        {hasCards ? (
          <section className="hud-deck" aria-label="Affichages de Jarvis">
            <div className="hud-deck-head">
              <h2 className="section-label">Affichage</h2>
              <button type="button" className="btn btn--ghost btn--sm" onClick={clearAll}>
                <Icon name="x" size={15} />
                Tout effacer
              </button>
            </div>
            <div className="hud-deck-grid">
              {cards.map((card) => (
                <CardView key={card.id} card={card} onDismiss={dismiss} />
              ))}
            </div>
          </section>
        ) : (
          <div className="hud-suggestions">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                className="suggestion"
                onClick={() => send(s)}
                disabled={!online}
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {voice.error && (
        <div className="alert alert--danger hud-alert" role="alert">
          <Icon name="alert" size={16} />
          {voice.error}
        </div>
      )}

      {voice.armed && (
        <div className="hud-listen" role="status" aria-live="polite">
          <span className={`dot ${voice.wakeWordHeard ? "dot--ok" : "dot--cyan"} dot--pulse`} aria-hidden="true" />
          {voice.wakeWordHeard ? "« Jarvis » détecté" : "En écoute — dites « Jarvis »"}
          <span className="meter" aria-hidden="true">
            <span className="meter-fill" style={{ width: `${Math.min(100, voice.lastScore * 100)}%` }} />
          </span>
          {voice.lastTranscript && <span className="hud-heard">entendu : « {voice.lastTranscript} »</span>}
        </div>
      )}

      <Composer online={online} busy={busy} onSend={send} voice={voice} />
    </div>
  );
}

async function speakAnswer(text, voice) {
  if (!text) {
    voice.resume();
    return;
  }
  try {
    const res = await authFetch("/api/speech/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      voice.resume();
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => {
      URL.revokeObjectURL(url);
      voice.resume();
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      voice.resume();
    };
    await audio.play();
  } catch {
    voice.resume();
  }
}

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ViewHeader } from "./AppShell.jsx";
import CardView from "./cards/CardView.jsx";
import Icon from "./ui/Icon.jsx";
import StatusBadge from "./ui/StatusBadge.jsx";
import { authFetch } from "../lib/consoleAuth.js";
import { useCardFeed } from "../lib/useCardFeed.js";
import { useChat } from "../lib/useChat.js";
import { useVoice } from "../lib/useVoice.js";

const SUGGESTIONS = [
  "Quel temps fait-il ?",
  "Résume-moi mes prochains rendez-vous",
  "Mémorise que je préfère les réponses courtes",
  "Fais une capture d'écran du PC fixe",
];

const VOICE_LABELS = {
  idle: "Micro éteint",
  listening: "En écoute — dites « Jarvis »",
  listening_command: "Jarvis vous écoute",
  transcribing: "Transcription en cours",
  speaking: "Jarvis parle",
};

function formatTime(ts) {
  if (!ts) return "";
  return new Date(ts).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

function dayKey(ts) {
  if (!ts) return "";
  return new Date(ts).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
}

/** Une bulle. Le rôle est écrit (« Vous » / « Jarvis »), pas seulement
 * suggéré par l'alignement et la couleur — c'est ce qui rend le fil
 * lisible pour un lecteur d'écran comme en diagonale. */
function Message({ message, activity }) {
  const isUser = message.role === "user";
  const empty = !message.text;
  return (
    <article className={`msg msg--${isUser ? "user" : "jarvis"}`}>
      <div className="msg-meta">
        <span>{isUser ? "Vous" : "Jarvis"}</span>
        {message.at && <span>· {formatTime(message.at)}</span>}
        {!isUser && message.source && !message.pending && <span>· {message.source}</span>}
      </div>
      <div className="msg-bubble">
        {empty ? (
          activity ? (
            <span className="msg-activity">
              <span className="spinner" aria-hidden="true" />
              {activity}
            </span>
          ) : (
            <span className="thinking" role="status" aria-label="Jarvis réfléchit">
              <span />
              <span />
              <span />
            </span>
          )
        ) : (
          message.text
        )}
        {!empty && message.pending && activity && (
          <div className="msg-activity" style={{ marginTop: "var(--sp-2)" }}>
            <span className="spinner" aria-hidden="true" />
            {activity}
          </div>
        )}
      </div>
    </article>
  );
}

function Thread({ messages, activity }) {
  const scrollerRef = useRef(null);
  const stickToBottomRef = useRef(true);

  // On ne recolle en bas que si Monsieur y était déjà : sinon relire un
  // vieux message pendant que Jarvis répond devient impossible, la vue
  // sautant à chaque phrase reçue.
  function onScroll() {
    const el = scrollerRef.current;
    if (!el) return;
    stickToBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }

  useLayoutEffect(() => {
    const el = scrollerRef.current;
    if (el && stickToBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [messages, activity]);

  let lastDay = "";

  return (
    <div className="thread" ref={scrollerRef} onScroll={onScroll}>
      <div className="thread-inner">
        {messages.map((m) => {
          const day = dayKey(m.at);
          const separator = day && day !== lastDay ? day : null;
          lastDay = day || lastDay;
          return (
            <div key={m.id} style={{ display: "contents" }}>
              {separator && <div className="thread-sep">{separator}</div>}
              <Message message={m} activity={m.pending ? activity : ""} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Ce que le micro entend, en clair. Sans ce bandeau, l'écoute armée est
 * une boîte noire : impossible de savoir si le mot d'éveil est passé, si
 * la commande a été comprise, ou si le micro capte simplement du bruit. */
function VoiceBar({ voice }) {
  if (!voice.armed) return null;
  const heard = voice.wakeWordHeard;
  return (
    <div className="voicebar" role="status" aria-live="polite">
      <span className={`voicebar-state${heard ? " voicebar-state--heard" : ""}`}>
        <span className={`dot ${heard ? "dot--ok" : "dot--cyan"} dot--pulse`} aria-hidden="true" />
        {heard ? "« Jarvis » détecté" : VOICE_LABELS[voice.status]}
      </span>

      {voice.status === "listening" && (
        <>
          <span className="meter" aria-hidden="true">
            <span className="meter-fill" style={{ width: `${Math.min(100, voice.lastScore * 100)}%` }} />
          </span>
          <span className="voicebar-heard">niveau {voice.lastScore.toFixed(2)}</span>
        </>
      )}

      <span className="spacer" />
      {voice.lastTranscript && <span className="voicebar-heard">entendu : « {voice.lastTranscript} »</span>}
    </div>
  );
}

function Composer({ online, busy, onSend, voice }) {
  const [value, setValue] = useState("");
  const inputRef = useRef(null);

  // Hauteur ajustée aussi au montage : sans ça, un `rows={1}` mesuré par
  // le navigateur avant le chargement de la police laisse une ligne
  // trop basse, et le texte saisi est rogné verticalement.
  useLayoutEffect(() => autoSize(inputRef.current), []);

  // Le champ grandit avec le texte : une commande de trois lignes ne doit
  // pas se saisir à l'aveugle dans une ligne unique qui défile.
  function autoSize(el) {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  function submit() {
    const text = value.trim();
    if (!text || busy || !online) return;
    if (onSend(text)) {
      setValue("");
      requestAnimationFrame(() => autoSize(inputRef.current));
    }
  }

  const micState = voice.armed
    ? voice.status === "listening_command" || voice.status === "transcribing"
      ? "mic--active"
      : "mic--armed"
    : "";

  return (
    <>
      <div className="composer">
        <button
          type="button"
          className={`mic ${micState}`.trim()}
          onClick={() => (voice.armed ? voice.disarm() : voice.arm())}
          aria-pressed={voice.armed}
          aria-label={voice.armed ? "Couper l'écoute vocale" : "Activer l'écoute vocale"}
          title={voice.armed ? VOICE_LABELS[voice.status] : "Activer l'écoute vocale"}
        >
          <Icon name="mic" size={20} />
        </button>

        <div className="composer-inner">
          <label className="sr-only" htmlFor="composer-input">
            Message pour Jarvis
          </label>
          <textarea
            id="composer-input"
            ref={inputRef}
            className="composer-input"
            rows={1}
            value={value}
            placeholder={online ? "Écrivez à Jarvis, ou parlez…" : "Brain injoignable"}
            disabled={!online}
            onChange={(e) => {
              setValue(e.target.value);
              autoSize(e.target);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <button
            type="button"
            className="composer-send"
            onClick={submit}
            disabled={!online || busy || !value.trim()}
            aria-label="Envoyer"
          >
            <Icon name="send" size={17} />
          </button>
        </div>
      </div>
      <div className="composer-hint">
        <span className="kbd">Entrée</span> pour envoyer · <span className="kbd">Maj</span>+
        <span className="kbd">Entrée</span> pour aller à la ligne
      </div>
    </>
  );
}

/** Bandeau de cartes au-dessus du fil — auparavant réservé au pupitre
 * (Hud.jsx). Sans ça, quelqu'un qui vit dans la vue Conversation ne
 * voyait jamais l'agenda/les mails/la capture d'écran en carte, seulement
 * en texte — voir docs/ROADMAP_DISPLAY_INTEGRATIONS.md §2, item resté
 * ouvert : « le rendu riche n'existe que dans le Hud ». */
function CardStrip({ cards, dismiss, clearAll }) {
  if (cards.length === 0) return null;
  return (
    <section className="hud-deck hud-deck--strip" aria-label="Affichages de Jarvis">
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
  );
}

export default function Console() {
  const { status, messages, activity, busy, historyLoaded, ask, clear } = useChat();
  const { cards, dismiss, clearAll } = useCardFeed();
  const lastWasVoiceRef = useRef(false);
  const wasBusyRef = useRef(false);
  const lastAnswerRef = useRef("");

  // Déclaration de fonction (hoistée) : peut référencer `voice` avant sa
  // ligne `const` ci-dessous, tant qu'elle n'est appelée qu'après coup
  // (useVoice ne l'appelle que plus tard, de façon asynchrone, une fois
  // le composant entièrement rendu — voir onCommandRef dans useVoice.js).
  function handleVoiceCommand(text) {
    lastWasVoiceRef.current = true;
    voice.pause();
    ask(text);
  }

  const voice = useVoice({ onCommand: handleVoiceCommand });

  // Garde sous la main le texte complet de la dernière réponse : c'est lui
  // qu'on envoie à la synthèse vocale une fois le tour terminé.
  const lastJarvis = [...messages].reverse().find((m) => m.role === "jarvis");
  lastAnswerRef.current = lastJarvis?.text || "";

  // Un tour vient de se terminer (busy: true → false) : si la question
  // venait de la voix, on lit la réponse à voix haute puis on reprend
  // l'écoute — sinon on reprend directement (une réponse à une question
  // tapée ne doit pas se mettre à parler toute seule).
  useEffect(() => {
    if (wasBusyRef.current && !busy && lastWasVoiceRef.current) {
      lastWasVoiceRef.current = false;
      speakAnswer(lastAnswerRef.current, voice);
    }
    wasBusyRef.current = busy;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy]);

  const online = status === "online";
  const empty = messages.length === 0;

  return (
    <>
      <ViewHeader
        title="Conversation"
        subtitle={
          voice.armed ? "Écoute vocale active" : online ? "Prêt — écrivez ou parlez" : "Le brain ne répond pas"
        }
        actions={
          <>
            <StatusBadge tone={online ? "ok" : status === "connecting" ? "cyan" : "danger"} pulse={!online}>
              {online ? "en ligne" : status === "connecting" ? "connexion…" : "hors ligne"}
            </StatusBadge>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={clear}
              disabled={empty}
              title="Vide l'affichage — le journal du brain n'est pas effacé"
            >
              <Icon name="refresh" size={16} />
              Effacer l'affichage
            </button>
          </>
        }
      />

      <div className="chat">
        <CardStrip cards={cards} dismiss={dismiss} clearAll={clearAll} />
        {empty && historyLoaded ? (
          <div className="chat-welcome">
            <h2>Bonsoir, Monsieur.</h2>
            <p>
              Posez une question, donnez un ordre à un appareil, ou activez le micro et dites
              « Jarvis ». La conversation est conservée d'une session à l'autre.
            </p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="suggestion" onClick={() => ask(s)} disabled={!online}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <Thread messages={messages} activity={activity} />
        )}

        {voice.error && (
          <div className="alert alert--danger" style={{ margin: "0 var(--sp-6) var(--sp-2)" }} role="alert">
            <Icon name="alert" size={16} />
            {voice.error}
          </div>
        )}

        <VoiceBar voice={voice} />
        <Composer online={online} busy={busy} onSend={ask} voice={voice} />
      </div>
    </>
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

import { useLayoutEffect, useRef, useState } from "react";
import { ViewHeader } from "./AppShell.jsx";
import CardDeck from "./cards/CardDeck.jsx";
import Icon from "./ui/Icon.jsx";
import MicButton from "./ui/MicButton.jsx";
import StatusBadge from "./ui/StatusBadge.jsx";
import { useChatContext } from "../lib/ChatContext.jsx";
import { useCardFeed } from "../lib/useCardFeed.js";
import { useVoiceContext } from "../lib/VoiceContext.jsx";
import { useVoiceRelay } from "../lib/useVoiceRelay.js";

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
        {message.imageUrl && (
          <img
            src={message.imageUrl}
            alt="Image jointe"
            style={{ maxWidth: 220, maxHeight: 220, borderRadius: "var(--r-md)", display: "block", marginBottom: "var(--sp-2)" }}
          />
        )}
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
    <div
      className="thread"
      ref={scrollerRef}
      onScroll={onScroll}
      role="log"
      aria-live="polite"
      aria-relevant="additions"
      aria-label="Fil de conversation"
    >
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
  // Un autre appareil (le PC fixe, ou une autre Console) a la main pour
  // la réponse parlée en ce moment — voir usePresence.js / VoiceContext.jsx.
  // Cette Console continue d'afficher le texte, juste pas le son.
  const elsewhere = voice.presence?.device && voice.presence.device !== voice.deviceId;
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

      {elsewhere && (
        <span className="voicebar-heard" title="Cette Console reste silencieuse pour ne pas parler en double">
          🔊 réponse sur : {voice.presence.label}
        </span>
      )}

      <span className="spacer" />
      {voice.lastTranscript && <span className="voicebar-heard">entendu : « {voice.lastTranscript} »</span>}
    </div>
  );
}

function Composer({ online, busy, onSend, onUploadImage, voice }) {
  const [value, setValue] = useState("");
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);

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

  // Dépôt d'image (C9) : le texte déjà tapé sert de question — « décris
  // cette image » n'a pas besoin d'un second champ dédié, le composer
  // suffit. Le <input type=file> reste cosmétiquement invisible, activé
  // par le bouton trombone (pattern standard, pas de glisser-déposer :
  // moins de code pour un geste que le clic couvre déjà).
  function pickImage() {
    fileInputRef.current?.click();
  }

  function onFileChosen(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // permet de rechoisir le même fichier une 2e fois
    if (!file || busy || !online) return;
    const text = value.trim();
    if (onUploadImage(file, text)) {
      setValue("");
      requestAnimationFrame(() => autoSize(inputRef.current));
    }
  }

  return (
    <>
      <div className="composer">
        <MicButton
          voice={voice}
          title={`${voice.armed ? VOICE_LABELS[voice.status] : "Activer l'écoute vocale"} (Ctrl+Alt+J)`}
        />

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="sr-only"
          tabIndex={-1}
          onChange={onFileChosen}
        />
        <button
          type="button"
          className="mic"
          onClick={pickImage}
          disabled={!online || busy}
          aria-label="Joindre une image pour analyse"
          title="Joindre une image pour analyse"
        >
          <Icon name="camera" size={19} />
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

export default function Console() {
  const { status, messages, activity, busy, historyLoaded, ask, uploadImage, clear, setPhraseHandler, setDoneHandler } =
    useChatContext();
  const { cards, dismiss, clearAll } = useCardFeed();

  // Instance partagée avec Hud (montée dans App.jsx) — voir
  // lib/useVoiceRelay.js pour le câblage commun aux deux vues.
  const voice = useVoiceContext();
  useVoiceRelay(voice, ask, setPhraseHandler, setDoneHandler);

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
        <CardDeck cards={cards} dismiss={dismiss} clearAll={clearAll} className="hud-deck--strip" />
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
        <Composer online={online} busy={busy} onSend={ask} onUploadImage={uploadImage} voice={voice} />
      </div>
    </>
  );
}

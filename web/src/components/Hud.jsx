import { useCallback, useEffect, useRef, useState } from "react";
import CardView from "./cards/CardView.jsx";
import CardDeck from "./cards/CardDeck.jsx";
import Icon from "./ui/Icon.jsx";
import MicButton from "./ui/MicButton.jsx";
import ModeSwitcher from "./ui/ModeSwitcher.jsx";
import { useAmbient } from "../lib/useAmbient.js";
import { useChatContext } from "../lib/ChatContext.jsx";
import { useCardFeed } from "../lib/useCardFeed.js";
import { useDevices } from "../lib/useDevices.js";
import { useFullscreen } from "../lib/useFullscreen.js";
import { useVoiceContext } from "../lib/VoiceContext.jsx";
import { useVoiceRelay } from "../lib/useVoiceRelay.js";
import { useModes } from "../lib/useSystem.js";
import { formatCountdown, useTimers } from "../lib/useTimers.js";

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
//
// Le choix varie selon l'heure (le matin on part au travail, la nuit on
// écoute de la musique) et selon le mode actif quand celui-ci a un usage
// évident (mode Repas : minimal ; mode Détente : musique en avant).
const SUGGESTIONS_BY_PERIOD = {
  morning: [
    "Mes rendez-vous du jour",
    "Mes derniers mails",
    "Qu'est-ce que j'ai aujourd'hui ?",
    "Capture l'écran du PC fixe",
  ],
  afternoon: [
    "Mes derniers mails",
    "Mes rendez-vous du jour",
    "Capture l'écran du PC fixe",
    "Quelle musique joue en ce moment ?",
  ],
  evening: [
    "Mets de la musique",
    "Quelle musique joue en ce moment ?",
    "Capture l'écran du PC fixe",
    "Mes derniers mails",
  ],
  night: [
    "Quelle musique joue en ce moment ?",
    "Mets de la musique",
    "Capture l'écran du PC fixe",
    "Mes rendez-vous du jour",
  ],
};

const SUGGESTIONS_BY_MODE = {
  travail: [
    "Qu'est-ce que j'ai aujourd'hui ?",
    "Mes derniers mails",
    "Mes rendez-vous du jour",
    "Capture l'écran du PC fixe",
  ],
  projet: [
    "Capture l'écran du PC fixe",
    "Mes derniers mails",
    "Qu'est-ce que j'ai aujourd'hui ?",
    "Mes rendez-vous du jour",
  ],
  detente: [
    "Mets de la musique",
    "Quelle musique joue en ce moment ?",
    "Qu'est-ce que j'ai aujourd'hui ?",
    "Capture l'écran du PC fixe",
  ],
  repas: ["Quelle musique joue en ce moment ?", "Mes derniers mails"],
};

function periodForHour(hour) {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 18) return "afternoon";
  if (hour >= 18 && hour < 23) return "evening";
  return "night";
}

/** Le mode ne prime que quand il implique un usage sans ambiguïté (Travail,
 * Projet, Détente, Repas) ; sinon (Normal, Théologie…) l'heure décide. */
function useSuggestions() {
  const now = useClock();
  const { current } = useModes();
  const modeId = current?.mode_id;
  if (modeId && SUGGESTIONS_BY_MODE[modeId]) return SUGGESTIONS_BY_MODE[modeId];
  return SUGGESTIONS_BY_PERIOD[periodForHour(now.getHours())];
}

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
function Ambient({ devicesOnline, connected, isFullscreen, onToggleFullscreen, timers }) {
  const now = useClock();
  const next = timers[0];
  return (
    <div className="hud-ambient">
      <span className="hud-clock">
        {now.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
      </span>
      <span className="hud-date">
        {now.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}
      </span>
      <span className="spacer" />
      {next && (
        <span className="hud-chip hud-chip--timer" title={next.label || "Minuteur"}>
          <Icon name="clock" size={13} />
          {formatCountdown(next.remaining)}
          {timers.length > 1 && ` (+${timers.length - 1})`}
        </span>
      )}
      <ModeSwitcher variant="chip" />
      <span className="hud-chip">
        {devicesOnline} appareil{devicesOnline > 1 ? "s" : ""} en ligne
      </span>
      <span className={`hud-chip ${connected ? "hud-chip--ok" : "hud-chip--off"}`}>
        {connected ? "liaison établie" : "liaison rompue"}
      </span>
      {/* J4 : rien à poser sur une tablette fixée au mur ou un second
          écran tant que la barre latérale et la navigation restent — ce
          bouton bascule le pupitre en plein écran, sans elles. */}
      <button
        type="button"
        className="icon-btn icon-btn--sm"
        onClick={onToggleFullscreen}
        aria-pressed={isFullscreen}
        aria-label={isFullscreen ? "Quitter le plein écran" : "Passer en plein écran"}
        title={isFullscreen ? "Quitter le plein écran" : "Passer en plein écran"}
      >
        <Icon name={isFullscreen ? "collapse" : "expand"} size={16} />
      </button>
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
        {/* Purement visuel : les transitions d'état (veille, écoute, analyse…)
         * ne sont pas des actions à annoncer. Seule la région vivante unique
         * plus bas relaie ce qui appelle une réaction de Monsieur. */}
        <span className="hud-state">
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

/** F32 : version grand format de la réponse, lisible à trois mètres — la
 * bulle de `.hud-speech` reste (elle sert de journal visuel juste sous le
 * réacteur), mais elle est bien trop petite pour un salon. Ce bandeau se
 * pose par-dessus le pupitre tant que Jarvis parle à voix haute, puis
 * s'efface avec la réponse. */
function Subtitles({ text, visible }) {
  if (!text) return null;
  return (
    <div className={`hud-subtitles${visible ? " hud-subtitles--visible" : ""}`} aria-hidden="true">
      <p className="hud-subtitles-text">{text}</p>
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

  return (
    <form className="hud-composer" onSubmit={submit}>
      <MicButton voice={voice} large />

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
  // Le contexte partagé (ChatContext) charge le journal pour la Console ;
  // le Pupitre n'en veut pas — il montre ce qui se passe maintenant, pas le
  // fil d'hier. Sans le filtre `historical`, il rouvrirait en affichant la
  // dernière réponse du journal comme si Jarvis venait de la prononcer.
  const { status, messages: allMessages, activity, busy, ask, setPhraseHandler, setDoneHandler } =
    useChatContext();
  const messages = allMessages.filter((m) => !m.historical);
  // Notification navigateur à l'échéance d'un minuteur/rappel (C1) ou d'une
  // alerte proactive (C3) — la permission, elle, est demandée au moment où
  // Monsieur pose un minuteur (System.jsx), un vrai geste utilisateur, pas
  // ici en silence.
  const notifyCard = useCallback((card) => {
    if (card.type !== "timer" && card.type !== "proactive") return;
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    new Notification(card.title, { body: card.subtitle, icon: "/favicon.svg", tag: card.id });
  }, []);
  const { cards, lastExchange, connected, dismiss, clearAll } = useCardFeed(notifyCard);
  const { timers } = useTimers();
  const { devices } = useDevices();
  const ambientCards = useAmbient();
  const { isFullscreen, toggle: toggleFullscreen } = useFullscreen();

  const suggestions = useSuggestions();

  const lastLocalQuestionRef = useRef("");
  const localTurnAtRef = useRef(0);
  const [remote, setRemote] = useState(null);

  // Instance partagée avec Console (montée dans App.jsx) — voir
  // lib/useVoiceRelay.js pour le câblage commun aux deux vues.
  const voice = useVoiceContext();
  useVoiceRelay(voice, send, setPhraseHandler, setDoneHandler);

  function send(text) {
    lastLocalQuestionRef.current = text.trim();
    localTurnAtRef.current = Date.now();
    return ask(text);
  }

  // Réveil à la voix (J4) : une tablette fixée au mur n'a ni clavier ni
  // souris à portée. Passer en plein écran arme donc l'écoute du mot-clé
  // si elle ne l'était pas déjà, pour qu'un simple « Jarvis » suffise —
  // sans quoi le mode kiosque resterait sourd tant que personne n'a
  // retrouvé la vue Conversation pour armer le micro à la main.
  useEffect(() => {
    if (isFullscreen && !voice.armed) voice.arm();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFullscreen]);

  // Réveil au clic (J4) : un tapotement n'importe où sur le pupitre en
  // plein écran arme l'écoute — le pendant tactile du wake word pour la
  // même tablette sans clavier.
  function handleKioskWake() {
    if (isFullscreen && !voice.armed) voice.arm();
  }

  // Un tour diffusé qui n'est pas le nôtre : Monsieur a parlé au PC fixe
  // (ou depuis une autre Console). On l'affiche à l'identique — c'est tout
  // l'intérêt d'un écran qui reste allumé dans la pièce.
  useEffect(() => {
    if (!lastExchange) return;
    if (lastExchange.question === lastLocalQuestionRef.current) return;
    setRemote(lastExchange);
  }, [lastExchange]);

  // Texte affiché à l'écran — la lecture à voix haute, elle, part
  // maintenant phrase par phrase via handlePhrase/handleDone ci-dessus.
  const lastJarvis = [...messages].reverse().find((m) => m.role === "jarvis");
  const lastAnswerRef = useRef("");
  lastAnswerRef.current = lastJarvis?.text || "";

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
    <div className={`hud${isFullscreen ? " hud--kiosk" : ""}`} onClick={handleKioskWake}>
      <Ambient
        devicesOnline={devicesOnline}
        connected={connected && online}
        isFullscreen={isFullscreen}
        onToggleFullscreen={toggleFullscreen}
        timers={timers}
      />

      <div className="hud-body">
        <Stage
          state={state}
          question={question}
          answer={answer}
          activity={activity}
          compact={hasCards}
        />
        <Subtitles text={answer} visible={state === "speaking"} />

        {hasCards ? (
          <CardDeck cards={cards} dismiss={dismiss} clearAll={clearAll} />
        ) : (
          <>
            {/* Un écran laissé allumé dans une pièce doit dire quelque
             * chose : météo, agenda du jour, santé système — tant que
             * personne n'a rien demandé (F29). Lecture seule, à la
             * différence des cartes du flux : rien ici n'a été "affiché"
             * par une action de Monsieur, donc rien à écarter. */}
            {ambientCards.length > 0 && (
              <section className="hud-deck hud-deck--ambient" aria-label="Panorama">
                <div className="hud-deck-grid">
                  {ambientCards.map((card) => (
                    <CardView key={card.id} card={card} readOnly />
                  ))}
                </div>
              </section>
            )}
            <div className="hud-suggestions">
              {suggestions.map((s) => (
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
          </>
        )}
      </div>

      {/* Région vivante unique pour la voix : le seul rôle="status" du pupitre.
       * On n'y annonce que ce qui appelle une action de Monsieur — pas les
       * transitions d'état (déjà visibles dans .hud-state ci-dessus). Les
       * erreurs micro sont annoncées par l'alerte role="alert" plus bas, pas
       * ici, pour ne pas les vocaliser deux fois. */}
      <span className="sr-only" role="status" aria-live="polite">
        {!voice.error && state === "heard" ? "Je vous écoute" : ""}
      </span>

      {voice.error && (
        <div className="alert alert--danger hud-alert" role="alert">
          <Icon name="alert" size={16} />
          {voice.error}
        </div>
      )}

      {voice.armed && (
        <div className="hud-listen">
          <span className={`dot ${voice.wakeWordHeard ? "dot--ok" : "dot--cyan"} dot--pulse`} aria-hidden="true" />
          {voice.wakeWordHeard ? "« Jarvis » détecté" : "En écoute — dites « Jarvis »"}
          <span className="meter" aria-hidden="true">
            <span className="meter-fill" style={{ width: `${Math.min(100, voice.lastScore * 100)}%` }} />
          </span>
          {voice.presence?.device && voice.presence.device !== voice.deviceId && (
            <span className="hud-heard" title="Le pupitre reste silencieux pour ne pas parler en double">
              🔊 réponse sur : {voice.presence.label}
            </span>
          )}
          {voice.lastTranscript && <span className="hud-heard">entendu : « {voice.lastTranscript} »</span>}
        </div>
      )}

      <Composer online={online} busy={busy} onSend={send} voice={voice} />
    </div>
  );
}

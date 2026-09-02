import Icon from "./Icon.jsx";

/** État visuel du micro (armé / en écoute active), partagé par tous les
 * boutons micro — Pupitre, Conversation, et toute future vue. */
export function useMicState(voice) {
  return voice.armed
    ? voice.status === "listening_command" || voice.status === "transcribing"
      ? "mic--active"
      : "mic--armed"
    : "";
}

/** Bouton d'armement de l'écoute vocale. `large` ajoute la variante du
 * Pupitre (`mic--lg`) ; `title` permet à la Conversation d'afficher le
 * libellé d'état détaillé (VOICE_LABELS) plutôt que le libellé générique. */
export default function MicButton({ voice, large = false, title, size }) {
  const micState = useMicState(voice);
  const label = voice.armed ? "Couper l'écoute vocale" : "Activer l'écoute vocale";
  return (
    <button
      type="button"
      className={`mic${large ? " mic--lg" : ""} ${micState}`.trim()}
      onClick={() => (voice.armed ? voice.disarm() : voice.arm())}
      aria-pressed={voice.armed}
      aria-label={label}
      title={title ?? `${label} (Ctrl+Alt+J)`}
    >
      <Icon name="mic" size={size ?? (large ? 22 : 20)} />
    </button>
  );
}

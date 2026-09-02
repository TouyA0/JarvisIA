import { useRef } from "react";

/**
 * Câblage voix ↔ chat commun au Pupitre et à la Conversation : la commande
 * dictée met le wake word en pause le temps de la requête, et seule une
 * réponse déclenchée par la voix est relue à voix haute (phrase par phrase
 * via `setPhraseHandler`, puis close par `setDoneHandler`) — une question
 * tapée ne doit jamais se mettre à parler toute seule.
 *
 * `voice` est l'instance partagée (VoiceContext) montée dans App.jsx : on
 * réenregistre les gestionnaires à chaque rendu, pas dans un effet, pour
 * qu'une commande ou une phrase ne puisse jamais arriver avant que la vue
 * appelante ait pris la main.
 */
export function useVoiceRelay(voice, send, setPhraseHandler, setDoneHandler) {
  const lastWasVoiceRef = useRef(false);

  function handleVoiceCommand(text) {
    lastWasVoiceRef.current = true;
    voice.pause();
    // Le tour précédent n'a pas fini de streamer sa réponse (send() refuse) :
    // rien à écouter côté chat, on reprend l'écoute au lieu de rester bloqué
    // en pause sans qu'aucun chat.done ne vienne jamais la lever.
    if (!send(text)) {
      lastWasVoiceRef.current = false;
      voice.resume();
    }
  }

  function handlePhrase(text) {
    if (lastWasVoiceRef.current) voice.speakPhrase(text);
  }

  function handleDone() {
    if (lastWasVoiceRef.current) {
      lastWasVoiceRef.current = false;
      voice.speakEnd();
    }
  }

  voice.setCommandHandler(handleVoiceCommand);
  setPhraseHandler(handlePhrase);
  setDoneHandler(handleDone);
}

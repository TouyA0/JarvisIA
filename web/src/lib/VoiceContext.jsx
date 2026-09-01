import { createContext, useCallback, useContext, useRef } from "react";
import { useVoice } from "./useVoice.js";

/**
 * Une seule écoute vocale pour toute l'app, montée ici plutôt que dans
 * Hud et Console séparément — même raison que ChatContext.jsx.
 *
 * Avant : chaque écran instanciait son propre useVoice(), avec son propre
 * flux micro et son propre `armed`. Passer du Pupitre à la Conversation
 * démontait celui de l'écran quitté — disarm() au démontage (voir
 * useVoice.js) coupait le flux micro et désarmait l'écoute, sans que rien
 * ne la réarme côté nouvel écran. Il fallait re-cliquer le micro à chaque
 * changement d'écran, et le navigateur pouvait redemander la permission.
 *
 * Le gestionnaire de commande dépend en revanche de l'écran actif (Hud et
 * Console n'envoient pas la commande de la même façon). Chaque écran
 * l'enregistre à chaque rendu via `setCommandHandler` — assignation
 * directe dans le corps du composant, pas un effet, pour éviter une
 * fenêtre où une commande arriverait avant l'enregistrement (même
 * principe que onCommandRef dans useVoice.js).
 */
const VoiceContext = createContext(null);

export function VoiceProvider({ children }) {
  const handlerRef = useRef(null);

  const onCommand = useCallback((text) => {
    handlerRef.current?.(text);
  }, []);

  const voice = useVoice({ onCommand });

  const setCommandHandler = useCallback((fn) => {
    handlerRef.current = fn;
  }, []);

  const value = { ...voice, setCommandHandler };

  return <VoiceContext.Provider value={value}>{children}</VoiceContext.Provider>;
}

export function useVoiceContext() {
  const ctx = useContext(VoiceContext);
  if (!ctx) throw new Error("useVoiceContext doit être utilisé dans un <VoiceProvider>");
  return ctx;
}

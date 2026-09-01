import { createContext, useContext } from "react";
import { useChat } from "./useChat.js";

/**
 * Une seule connexion /ws/chat pour toute l'app, montée ici plutôt que dans
 * Hud et Console séparément.
 *
 * Avant : chaque vue instanciait son propre useChat(), donc son propre
 * WebSocket. Passer du Pupitre à la Conversation démontait celui du
 * Pupitre — fermant la socket — pendant qu'une réponse était encore en
 * cours de rédaction. onclose remettait `busy` à faux côté Pupitre, et la
 * réponse (pourtant bien journalisée côté brain) n'arrivait plus nulle
 * part : ni sur l'écran qu'on venait de quitter (démonté), ni sur celui
 * qu'on rejoignait (nouvelle socket, tour jamais lancé par elle). En
 * partageant une seule connexion montée au niveau de App.jsx, changer
 * d'écran ne touche plus au WebSocket ni au tour en cours.
 */
const ChatContext = createContext(null);

export function ChatProvider({ children }) {
  const chat = useChat();
  return <ChatContext.Provider value={chat}>{children}</ChatContext.Provider>;
}

export function useChatContext() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChatContext doit être utilisé dans un <ChatProvider>");
  return ctx;
}

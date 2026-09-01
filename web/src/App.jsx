import { useCallback, useState } from "react";
import AppShell from "./components/AppShell.jsx";
import AuthGate from "./components/AuthGate.jsx";
import ConfirmationBanner from "./components/ConfirmationBanner.jsx";
import Console from "./components/Console.jsx";
import Devices from "./components/Devices.jsx";
import Hud from "./components/Hud.jsx";
import Integrations from "./components/Integrations.jsx";
import Notes from "./components/Notes.jsx";
import Routines from "./components/Routines.jsx";
import Settings from "./components/Settings.jsx";
import System from "./components/System.jsx";
import { ConfirmProvider } from "./components/ui/Confirm.jsx";
import ErrorBoundary from "./components/ui/ErrorBoundary.jsx";
import { ToastProvider } from "./components/ui/Toast.jsx";
import { ChatProvider } from "./lib/ChatContext.jsx";
import { useConsoleAuth } from "./lib/useConsoleAuth.js";
import { VoiceProvider } from "./lib/VoiceContext.jsx";

const SCREENS = {
  hud: Hud,
  console: Console,
  devices: Devices,
  notes: Notes,
  routines: Routines,
  integrations: Integrations,
  system: System,
  settings: Settings,
};

export default function App() {
  // Le pupitre, pas la conversation : Jarvis est d'abord une présence qui
  // affiche des choses (voir Hud.jsx). Le fil de discussion reste
  // accessible, en second.
  const [view, setView] = useState("hud");
  const { needsAuth, login } = useConsoleAuth();

  const navigate = useCallback((next) => setView(next), []);

  if (needsAuth) {
    return <AuthGate onSubmit={login} />;
  }

  const Screen = SCREENS[view] || Hud;

  return (
    <ToastProvider>
      <ConfirmProvider>
        {/* Montée ici (pas dans Hud/Console) : passer du Pupitre à la
            Conversation ne doit pas fermer la socket /ws/chat en plein
            tour — voir lib/ChatContext.jsx. */}
        <ChatProvider>
          {/* Montée ici (pas dans Hud/Console) : changer d'écran ne doit
              pas couper le flux micro ni désarmer l'écoute — voir
              lib/VoiceContext.jsx. */}
          <VoiceProvider>
            {/* Montée ici (pas dans un panneau précis) : une confirmation
                d'écriture Drive doit rester visible quelle que soit la vue
                active — voir ConfirmationBanner.jsx. */}
            <ConfirmationBanner />
            <AppShell view={view} onNavigate={navigate}>
              {/* `key={view}` : changer d'écran repart d'une boundary saine —
                  un crash sur Console ne doit pas laisser le Pupitre KO au
                  retour. */}
              <ErrorBoundary key={view} label={`screen:${view}`}>
                <Screen />
              </ErrorBoundary>
            </AppShell>
          </VoiceProvider>
        </ChatProvider>
      </ConfirmProvider>
    </ToastProvider>
  );
}

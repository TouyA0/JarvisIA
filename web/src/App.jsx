import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import AppShell from "./components/AppShell.jsx";
import AuthGate from "./components/AuthGate.jsx";
import ConfirmationBanner from "./components/ConfirmationBanner.jsx";
import Hud from "./components/Hud.jsx";
import { ConfirmProvider } from "./components/ui/Confirm.jsx";
import ErrorBoundary from "./components/ui/ErrorBoundary.jsx";
import { ToastProvider } from "./components/ui/Toast.jsx";
import { ChatProvider } from "./lib/ChatContext.jsx";
import { useConsoleAuth } from "./lib/useConsoleAuth.js";
import { VoiceProvider } from "./lib/VoiceContext.jsx";

// Hud est chargé en dur (c'est l'écran affiché au premier rendu, inutile
// d'attendre un aller-retour réseau pour lui). Les sept autres ne sont
// demandés qu'au clic sur leur entrée de nav — pas de raison de les faire
// payer à tout le monde dans le bundle initial (P6).
const SCREENS = {
  hud: Hud,
  console: lazy(() => import("./components/Console.jsx")),
  devices: lazy(() => import("./components/Devices.jsx")),
  notes: lazy(() => import("./components/Notes.jsx")),
  routines: lazy(() => import("./components/Routines.jsx")),
  integrations: lazy(() => import("./components/Integrations.jsx")),
  system: lazy(() => import("./components/System.jsx")),
  settings: lazy(() => import("./components/Settings.jsx")),
};

// URL = état de navigation, pas juste un useState (P1) : sans ça, F5 ramène
// toujours au Pupitre, le bouton retour du navigateur quitte l'appli, et le
// geste de retour Android sort de la PWA au lieu de revenir en arrière. Le
// hash (`#/devices`) suffit pour six vues et ne demande aucun changement
// côté serveur — le serveur ne voit jamais que `/`, `history.pushState`
// avec un vrai chemin aurait cassé le rechargement en prod (brain/server.py
// sert web/dist en statique, sans repli SPA sur les chemins profonds).
function viewFromHash() {
  const id = window.location.hash.replace(/^#\/?/, "");
  return SCREENS[id] ? id : "hud";
}

export default function App() {
  // Le pupitre, pas la conversation : Jarvis est d'abord une présence qui
  // affiche des choses (voir Hud.jsx). Le fil de discussion reste
  // accessible, en second.
  const [view, setView] = useState(viewFromHash);
  const { needsAuth, login } = useConsoleAuth();

  useEffect(() => {
    // Normalise l'URL initiale (hash absent ou invalide) sans empiler une
    // entrée d'historique supplémentaire.
    const normalized = viewFromHash();
    if (window.location.hash !== `#/${normalized}`) {
      window.history.replaceState(null, "", `#/${normalized}`);
    }

    const onHashChange = () => setView(viewFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = useCallback((next) => {
    if (!SCREENS[next]) return;
    // Le hashchange déclenché par cette assignation met à jour `view` via
    // l'effet ci-dessus ; pas besoin de setView ici.
    window.location.hash = `#/${next}`;
  }, []);

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
                <Suspense fallback={null}>
                  <Screen />
                </Suspense>
              </ErrorBoundary>
            </AppShell>
          </VoiceProvider>
        </ChatProvider>
      </ConfirmProvider>
    </ToastProvider>
  );
}

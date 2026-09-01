import { useState } from "react";
import AuthGate from "./components/AuthGate.jsx";
import ConfirmationBanner from "./components/ConfirmationBanner.jsx";
import Console from "./components/Console.jsx";
import Devices from "./components/Devices.jsx";
import Focus from "./components/Focus.jsx";
import Integrations from "./components/Integrations.jsx";
import Routines from "./components/Routines.jsx";
import { useConsoleAuth } from "./lib/useConsoleAuth.js";

export default function App() {
  const [view, setView] = useState("console");
  const [focusDeviceId, setFocusDeviceId] = useState(null);
  const { needsAuth, login } = useConsoleAuth();

  function openFocus(deviceId) {
    setFocusDeviceId(deviceId);
    setView("focus");
  }

  if (needsAuth) {
    return <AuthGate onSubmit={login} />;
  }

  let screen;
  if (view === "devices") {
    screen = <Devices onNavigate={setView} onOpenFocus={openFocus} focusEnabled={!!focusDeviceId} />;
  } else if (view === "focus" && focusDeviceId) {
    screen = <Focus deviceId={focusDeviceId} onNavigate={setView} />;
  } else if (view === "routines") {
    screen = <Routines onNavigate={setView} focusEnabled={!!focusDeviceId} />;
  } else if (view === "integrations") {
    screen = <Integrations onNavigate={setView} focusEnabled={!!focusDeviceId} />;
  } else {
    screen = <Console onNavigate={setView} focusEnabled={!!focusDeviceId} />;
  }

  return (
    <>
      {/* Montée ici (pas dans un panneau précis) : une confirmation
          d'écriture Drive doit rester visible quelle que soit la vue
          active — voir ConfirmationBanner.jsx. */}
      <ConfirmationBanner />
      {screen}
    </>
  );
}

import { useState } from "react";
import AuthGate from "./components/AuthGate.jsx";
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

  if (view === "devices") {
    return <Devices onNavigate={setView} onOpenFocus={openFocus} focusEnabled={!!focusDeviceId} />;
  }
  if (view === "focus" && focusDeviceId) {
    return <Focus deviceId={focusDeviceId} onNavigate={setView} />;
  }
  if (view === "routines") {
    return <Routines onNavigate={setView} focusEnabled={!!focusDeviceId} />;
  }
  if (view === "integrations") {
    return <Integrations onNavigate={setView} focusEnabled={!!focusDeviceId} />;
  }
  return <Console onNavigate={setView} focusEnabled={!!focusDeviceId} />;
}

import { useState } from "react";
import Console from "./components/Console.jsx";
import Devices from "./components/Devices.jsx";
import Focus from "./components/Focus.jsx";
import Routines from "./components/Routines.jsx";

export default function App() {
  const [view, setView] = useState("console");
  const [focusDeviceId, setFocusDeviceId] = useState(null);

  function openFocus(deviceId) {
    setFocusDeviceId(deviceId);
    setView("focus");
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
  return <Console onNavigate={setView} focusEnabled={!!focusDeviceId} />;
}

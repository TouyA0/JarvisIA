import { useState } from "react";
import Console from "./components/Console.jsx";
import Devices from "./components/Devices.jsx";

export default function App() {
  const [view, setView] = useState("console");

  if (view === "devices") return <Devices onNavigate={setView} />;
  return <Console onNavigate={setView} />;
}

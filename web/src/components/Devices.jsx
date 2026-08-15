import { useState } from "react";
import Frame from "./Frame.jsx";
import { useDevices } from "../lib/useDevices.js";

const dot = (color, size = 7) => ({
  width: size,
  height: size,
  borderRadius: "50%",
  background: color,
  boxShadow: `0 0 8px ${color}`,
  flex: "none",
});

function Topbar({ count }) {
  return (
    <div
      style={{
        height: 54,
        flex: "none",
        borderBottom: "1px solid var(--stroke-soft)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 22px",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16 }}>Appareils</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--faint)" }}>
          {count} appairé{count > 1 ? "s" : ""}
        </span>
      </div>
    </div>
  );
}

function DeviceCard({ device, onForget }) {
  const online = device.status === "online";
  return (
    <div
      style={{
        background: "var(--bg-2)",
        border: "1px solid var(--stroke-soft)",
        borderRadius: 15,
        padding: 16,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 11, marginBottom: 14 }}>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            color: "var(--muted)",
            border: "1px solid var(--stroke-soft)",
            borderRadius: 7,
            padding: "5px 8px",
            textTransform: "uppercase",
          }}
        >
          {device.device_type}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 14, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {device.name}
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--faint)" }}>
            {device.capabilities.join(", ") || "aucune capacité déclarée"}
          </div>
        </div>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: online ? "var(--online)" : "var(--faint)", flex: "none" }}>
          <span style={dot(online ? "var(--online)" : "var(--faint)")} />
          {online ? "en ligne" : "hors ligne"}
        </span>
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button
          onClick={() => onForget(device.device_id)}
          style={{
            border: "1px solid var(--stroke-soft)",
            borderRadius: 9,
            padding: "7px 11px",
            fontSize: 12,
            background: "transparent",
            color: "var(--muted)",
            cursor: "pointer",
          }}
        >
          Oublier
        </button>
      </div>
    </div>
  );
}

function PairingPanel() {
  const [code, setCode] = useState(null);
  const [expired, setExpired] = useState(false);

  async function generate() {
    setExpired(false);
    const res = await fetch("/api/pairing/code", { method: "POST" });
    const data = await res.json();
    setCode(data.code);
    setTimeout(() => setExpired(true), 5 * 60 * 1000);
  }

  return (
    <div
      style={{
        width: 298,
        flex: "none",
        borderLeft: "1px solid var(--stroke-soft)",
        background: "var(--bg-2)",
        padding: "22px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 18,
      }}
    >
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: ".16em", textTransform: "uppercase", color: "var(--faint)" }}>
        Appairage
      </div>

      {code && !expired ? (
        <>
          <div
            style={{
              textAlign: "center",
              fontFamily: "var(--font-mono)",
              fontSize: 26,
              letterSpacing: ".2em",
              color: "var(--cyan)",
              textShadow: "0 0 14px var(--glow)",
              padding: "20px 0",
              border: "1px solid var(--stroke)",
              borderRadius: 14,
              boxShadow: "0 0 34px -14px var(--glow)",
            }}
          >
            {code}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12, fontSize: 12, color: "var(--muted)" }}>
            <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--cyan)" }}>1</span>
              Lance <code>python -m agents.desktop.agent_client</code> sur le nouvel appareil
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--cyan)" }}>2</span>
              Saisis le code ci-dessus quand il est demandé
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--cyan)" }}>3</span>
              Il apparaît ici, en ligne, une fois connecté
            </div>
          </div>
          <div style={{ fontSize: 11, color: "var(--faint)" }}>Valable 5 minutes, usage unique.</div>
        </>
      ) : (
        <div style={{ fontSize: 12, color: "var(--faint)" }}>
          {expired ? "Code expiré." : "Aucun code généré."}
        </div>
      )}

      <button
        onClick={generate}
        style={{
          marginTop: "auto",
          border: "1px solid var(--stroke)",
          borderRadius: 9,
          padding: "10px 14px",
          fontSize: 13,
          background: "var(--cyan-dim)",
          color: "var(--cyan)",
          cursor: "pointer",
        }}
      >
        Générer un nouveau code
      </button>
    </div>
  );
}

export default function Devices({ onNavigate }) {
  const { devices, forget } = useDevices();

  return (
    <Frame active="devices" onNavigate={onNavigate}>
      <Topbar count={devices.length} />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div style={{ flex: 1, padding: 22, overflow: "auto", minWidth: 0 }}>
          {devices.length === 0 ? (
            <div style={{ color: "var(--faint)", fontSize: 13 }}>
              Aucun appareil appairé pour l'instant — génère un code d'appairage à droite.
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              {devices.map((d) => (
                <DeviceCard key={d.device_id} device={d} onForget={forget} />
              ))}
            </div>
          )}
        </div>
        <PairingPanel />
      </div>
    </Frame>
  );
}

import Frame from "./Frame.jsx";
import { useFocusDevice } from "../lib/useFocusDevice.js";

const dot = (color, size = 7) => ({
  width: size,
  height: size,
  borderRadius: "50%",
  background: color,
  boxShadow: `0 0 8px ${color}`,
  flex: "none",
});

function Topbar({ device }) {
  const online = device?.status === "online";
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
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16 }}>
          Focus · {device?.name || "…"}
        </span>
      </div>
      <span style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 11, color: online ? "var(--online)" : "var(--danger)", fontFamily: "var(--font-mono)" }}>
        <span style={dot(online ? "var(--online)" : "var(--danger)")} />
        {online ? "en ligne" : "hors ligne"}
      </span>
    </div>
  );
}

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function Focus({ deviceId, onNavigate }) {
  const { device, activityLog, screenshot, busy, error, capture, lock } = useFocusDevice(deviceId);

  function handleLock() {
    if (window.confirm("Verrouiller cet appareil maintenant ?")) lock();
  }

  return (
    <Frame active="focus" onNavigate={onNavigate} focusEnabled>
      <Topbar device={device} />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div
          style={{
            flex: 1,
            position: "relative",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 20,
            background:
              "radial-gradient(600px 500px at 50% 50%, var(--cyan-dim), transparent 64%)," +
              "repeating-linear-gradient(0deg,var(--grid) 0 1px,transparent 1px 44px)," +
              "repeating-linear-gradient(90deg,var(--grid) 0 1px,transparent 1px 44px)",
            minWidth: 0,
          }}
        >
          {screenshot ? (
            <img
              src={`data:image/jpeg;base64,${screenshot}`}
              alt="Capture d'écran"
              style={{ maxWidth: "70%", maxHeight: "70%", borderRadius: 12, border: "1px solid var(--stroke)", boxShadow: "0 0 60px -18px var(--glow)" }}
            />
          ) : (
            <div
              style={{
                width: 236,
                height: 160,
                borderRadius: 16,
                border: "1px solid var(--stroke)",
                display: "grid",
                placeItems: "center",
                boxShadow: "0 0 60px -18px var(--glow), inset 0 0 40px -20px var(--glow)",
              }}
            >
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--faint)", textAlign: "center", lineHeight: 1.7 }}>
                aucune capture pour l'instant
              </span>
            </div>
          )}

          {error && (
            <div style={{ color: "var(--danger)", fontSize: 12, fontFamily: "var(--font-mono)" }}>{error}</div>
          )}

          <div style={{ display: "flex", gap: 12 }}>
            <button
              onClick={capture}
              disabled={busy || device?.status !== "online"}
              style={{
                display: "flex", alignItems: "center", gap: 9,
                border: "1px solid var(--stroke-soft)", borderRadius: 12, padding: "11px 15px",
                fontSize: 13, background: "transparent", color: "var(--text)",
                cursor: busy ? "default" : "pointer", opacity: device?.status === "online" ? 1 : 0.5,
              }}
            >
              <span style={{ width: 11, height: 11, background: "var(--cyan)", transform: "rotate(45deg)", borderRadius: 2 }} />
              Capturer
            </button>
            <button
              onClick={handleLock}
              disabled={busy || device?.status !== "online"}
              style={{
                display: "flex", alignItems: "center", gap: 9,
                border: "1px solid var(--stroke-soft)", borderRadius: 12, padding: "11px 15px",
                fontSize: 13, background: "transparent", color: "var(--text)",
                cursor: busy ? "default" : "pointer", opacity: device?.status === "online" ? 1 : 0.5,
              }}
            >
              <span style={{ width: 11, height: 11, border: "2px solid var(--cyan)", borderRadius: 3 }} />
              Verrouiller
            </button>
          </div>
        </div>

        <div
          style={{
            width: 298, flex: "none", borderLeft: "1px solid var(--stroke-soft)",
            background: "var(--bg-2)", padding: "22px 20px", display: "flex",
            flexDirection: "column", gap: 18, overflow: "auto",
          }}
        >
          <div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: ".16em", textTransform: "uppercase", color: "var(--faint)", marginBottom: 12 }}>
              Appareil
            </div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, lineHeight: 2, color: "var(--muted)" }}>
              <div>type · <span style={{ color: "var(--text)" }}>{device?.device_type || "—"}</span></div>
              <div>capacités · {device?.capabilities?.join(", ") || "—"}</div>
              <div>appairé le · {device ? new Date(device.paired_at * 1000).toLocaleDateString("fr-FR") : "—"}</div>
            </div>
          </div>

          <div style={{ flex: 1 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: ".16em", textTransform: "uppercase", color: "var(--faint)", marginBottom: 12 }}>
              Journal
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, fontFamily: "var(--font-mono)", fontSize: 11, lineHeight: 1.4 }}>
              {activityLog.length === 0 ? (
                <span style={{ color: "var(--faint)" }}>Aucune activité pour l'instant.</span>
              ) : (
                activityLog.map((entry, i) => (
                  <div key={i} style={{ display: "flex", gap: 9 }}>
                    <span style={{ color: entry.ok ? "var(--cyan)" : "var(--danger)" }}>{formatTime(entry.ts)}</span>
                    <span style={{ color: "var(--muted)" }}>{entry.tool}{entry.ok ? "" : ` — ${entry.error || "échec"}`}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </Frame>
  );
}

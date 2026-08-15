import { useState } from "react";
import Frame from "./Frame.jsx";
import { useRoutines } from "../lib/useRoutines.js";
import { useDevices } from "../lib/useDevices.js";
import { useIsMobile } from "../lib/useIsMobile.js";

// Set volontairement restreint et curaté (pas de console PowerShell libre
// dans le builder) — même logique de prudence que Focus.jsx : une routine
// s'exécute d'un clic, sans confirmation étape par étape, donc pas de
// commande arbitraire ici.
const STEP_KINDS = [
  { id: "capture", label: "Capturer l'écran", tool: "take_screenshot", needsUrl: false },
  { id: "lock", label: "Verrouiller", tool: "run_powershell", needsUrl: false,
    args: { command: "rundll32.exe user32.dll,LockWorkStation" } },
  { id: "open_url", label: "Ouvrir une URL", tool: "open_url", needsUrl: true },
];

function Topbar({ count }) {
  return (
    <div
      style={{
        height: 54, flex: "none", borderBottom: "1px solid var(--stroke-soft)",
        display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 22px",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16 }}>Routines</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--faint)" }}>
          {count} routine{count > 1 ? "s" : ""}
        </span>
      </div>
    </div>
  );
}

function RoutineCard({ routine, devices, onRun, onDelete }) {
  const run = routine.run_status;
  const running = run?.status === "running";
  const deviceName = (id) => devices.find((d) => d.device_id === id)?.name || id;

  return (
    <div
      style={{
        background: "var(--bg-2)",
        border: `1px solid ${running ? "var(--stroke)" : "var(--stroke-soft)"}`,
        borderRadius: 15,
        padding: 16,
        boxShadow: running ? "inset 0 0 34px -20px var(--glow)" : "none",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {running && (
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--cyan)", boxShadow: "0 0 10px var(--cyan)", animation: "breathe 1.6s ease-in-out infinite" }} />
          )}
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15 }}>
            {routine.name}{running ? " — en cours" : ""}
          </span>
        </div>
        {run && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: run.status === "error" ? "var(--danger)" : "var(--cyan)" }}>
            {run.status === "error" ? `erreur : ${run.error}` : `${run.step_index + (run.status === "done" ? 1 : 0)} / ${run.total}`}
          </span>
        )}
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
        {routine.steps.map((step, i) => (
          <span
            key={i}
            style={{
              fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)",
              border: "1px solid var(--stroke-soft)", borderRadius: 6, padding: "4px 7px",
            }}
          >
            {step.tool} · {deviceName(step.device_id)}
          </span>
        ))}
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button
          onClick={() => onDelete(routine.id)}
          style={{ border: "1px solid var(--stroke-soft)", borderRadius: 9, padding: "7px 11px", fontSize: 12, background: "transparent", color: "var(--muted)", cursor: "pointer" }}
        >
          Supprimer
        </button>
        <button
          onClick={() => onRun(routine.id)}
          disabled={running}
          style={{
            border: "1px solid var(--stroke)", borderRadius: 9, padding: "7px 11px", fontSize: 12,
            background: "var(--cyan-dim)", color: "var(--cyan)", cursor: running ? "default" : "pointer",
            opacity: running ? 0.5 : 1,
          }}
        >
          Lancer
        </button>
      </div>
    </div>
  );
}

function Builder({ devices, onCreate, isMobile }) {
  const [name, setName] = useState("");
  const [steps, setSteps] = useState([]);
  const [kind, setKind] = useState(STEP_KINDS[0].id);
  const [deviceId, setDeviceId] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState(null);

  function addStep() {
    if (!deviceId) return;
    const k = STEP_KINDS.find((s) => s.id === kind);
    const args = k.needsUrl ? { url } : k.args || {};
    if (k.needsUrl && !url.trim()) return;
    setSteps((prev) => [...prev, { device_id: deviceId, tool: k.tool, args, label: k.label }]);
    setUrl("");
  }

  function removeStep(i) {
    setSteps((prev) => prev.filter((_, idx) => idx !== i));
  }

  async function save() {
    setError(null);
    try {
      await onCreate(name, steps.map(({ device_id, tool, args }) => ({ device_id, tool, args })));
      setName("");
      setSteps([]);
    } catch (e) {
      setError(e.message);
    }
  }

  const deviceName = (id) => devices.find((d) => d.device_id === id)?.name || id;

  return (
    <div
      style={{
        width: isMobile ? "100%" : 298, flex: "none",
        borderLeft: isMobile ? "none" : "1px solid var(--stroke-soft)",
        borderTop: isMobile ? "1px solid var(--stroke-soft)" : "none",
        background: "var(--bg-2)", padding: "22px 20px", display: "flex",
        flexDirection: "column", gap: 16, overflow: "auto",
      }}
    >
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: ".16em", textTransform: "uppercase", color: "var(--faint)" }}>
        Nouvelle routine
      </div>

      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Nom de la routine"
        style={{ border: "1px solid var(--stroke-soft)", borderRadius: 11, padding: "11px 13px", fontSize: 13, background: "transparent", color: "var(--text)" }}
      />

      <div>
        <div style={{ fontSize: 11, color: "var(--faint)", marginBottom: 7 }}>Étapes</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {steps.map((s, i) => (
            <div key={i} style={{ border: "1px solid var(--stroke-soft)", borderRadius: 11, padding: "10px 13px", display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12 }}>
              <span>{s.label} · {deviceName(s.device_id)}</span>
              <button onClick={() => removeStep(i)} style={{ background: "none", border: "none", color: "var(--faint)", cursor: "pointer", fontSize: 14, lineHeight: 1 }}>×</button>
            </div>
          ))}

          <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)}
            style={{ border: "1px solid var(--stroke-soft)", borderRadius: 9, padding: "8px 10px", fontSize: 12, background: "var(--bg)", color: "var(--text)" }}>
            <option value="">Appareil…</option>
            {devices.map((d) => <option key={d.device_id} value={d.device_id}>{d.name}</option>)}
          </select>
          <select value={kind} onChange={(e) => setKind(e.target.value)}
            style={{ border: "1px solid var(--stroke-soft)", borderRadius: 9, padding: "8px 10px", fontSize: 12, background: "var(--bg)", color: "var(--text)" }}>
            {STEP_KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
          </select>
          {STEP_KINDS.find((k) => k.id === kind)?.needsUrl && (
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…"
              style={{ border: "1px solid var(--stroke-soft)", borderRadius: 9, padding: "8px 10px", fontSize: 12, background: "transparent", color: "var(--text)" }} />
          )}
          <div
            onClick={addStep}
            style={{ border: "1px dashed var(--stroke)", borderRadius: 11, padding: "11px 13px", display: "flex", alignItems: "center", gap: 9, fontSize: 13, color: "var(--muted)", cursor: "pointer" }}
          >
            <span style={{ color: "var(--cyan)", fontSize: 16, lineHeight: 1 }}>+</span>Ajouter une action
          </div>
        </div>
      </div>

      {error && <div style={{ color: "var(--danger)", fontSize: 12 }}>{error}</div>}

      <button
        onClick={save}
        disabled={!name.trim() || steps.length === 0}
        style={{
          marginTop: "auto", background: "var(--cyan)", color: "var(--bg)", textAlign: "center",
          fontWeight: 600, fontSize: 14, border: "none", borderRadius: 12, padding: 13,
          boxShadow: "0 0 24px -6px var(--glow)", cursor: "pointer",
          opacity: !name.trim() || steps.length === 0 ? 0.5 : 1,
        }}
      >
        Enregistrer la routine
      </button>
    </div>
  );
}

export default function Routines({ onNavigate, focusEnabled }) {
  const { routines, create, remove, run } = useRoutines();
  const { devices } = useDevices();
  const isMobile = useIsMobile();

  return (
    <Frame active="routines" onNavigate={onNavigate} focusEnabled={focusEnabled}>
      <Topbar count={routines.length} />
      <div style={{ flex: 1, display: "flex", flexDirection: isMobile ? "column" : "row", minHeight: 0, overflow: "auto" }}>
        <div style={{ flex: 1, padding: 22, overflow: "visible", display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
          {routines.length === 0 ? (
            <div style={{ color: "var(--faint)", fontSize: 13 }}>
              Aucune routine — crées-en une {isMobile ? "en dessous" : "à droite"}.
            </div>
          ) : (
            routines.map((r) => (
              <RoutineCard key={r.id} routine={r} devices={devices} onRun={run} onDelete={remove} />
            ))
          )}
        </div>
        <Builder devices={devices} onCreate={create} isMobile={isMobile} />
      </div>
    </Frame>
  );
}

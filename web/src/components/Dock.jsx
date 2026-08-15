import Reactor from "./Reactor.jsx";

// focus/routines pas encore codés (Phase 4 suite / Phase 5) — icônes
// visibles pour la fidélité au design mais inertes plutôt que de mener
// vers un écran vide.
const ITEMS = [
  { id: "console", enabled: true },
  { id: "devices", enabled: true },
  { id: "focus", enabled: false },
  { id: "routines", enabled: false },
];

function DockShape({ id, active }) {
  const color = active ? "var(--cyan)" : "var(--faint)";
  if (id === "devices") {
    return <div style={{ width: 12, height: 12, background: color, transform: "rotate(45deg)", borderRadius: 2 }} />;
  }
  if (id === "focus") {
    return <div style={{ width: 13, height: 13, border: `1.5px solid ${color}`, borderRadius: 3 }} />;
  }
  if (id === "routines") {
    return (
      <span
        style={{
          width: 0,
          height: 0,
          borderLeft: "7px solid transparent",
          borderRight: "7px solid transparent",
          borderBottom: `12px solid ${color}`,
        }}
      />
    );
  }
  return <div style={{ width: 12, height: 12, borderRadius: "50%", background: color }} />;
}

export default function Dock({ active, onNavigate }) {
  return (
    <div
      style={{
        width: 70,
        flex: "none",
        borderRight: "1px solid var(--stroke-soft)",
        background: "var(--bg-2)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "18px 0",
        gap: 22,
      }}
    >
      <Reactor />
      <div style={{ display: "flex", flexDirection: "column", gap: 14, alignItems: "center" }}>
        {ITEMS.map((item) => {
          const isActive = item.id === active;
          return (
            <button
              key={item.id}
              type="button"
              title={item.enabled ? item.id : `${item.id} — bientôt`}
              onClick={() => item.enabled && onNavigate(item.id)}
              disabled={!item.enabled}
              style={{
                width: 42,
                height: 42,
                borderRadius: 12,
                display: "grid",
                placeItems: "center",
                background: isActive ? "var(--cyan-dim)" : "transparent",
                border: isActive ? "1px solid var(--stroke)" : "1px solid transparent",
                boxShadow: isActive ? "0 0 16px -6px var(--glow)" : "none",
                cursor: item.enabled ? "pointer" : "default",
                opacity: item.enabled ? 1 : 0.5,
                padding: 0,
              }}
            >
              <DockShape id={item.id} active={isActive} />
            </button>
          );
        })}
      </div>
      <div
        style={{
          marginTop: "auto",
          width: 34,
          height: 34,
          borderRadius: "50%",
          background: "var(--bg-3)",
          border: "1px solid var(--stroke-soft)",
        }}
      />
    </div>
  );
}

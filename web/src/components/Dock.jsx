import Reactor from "./Reactor.jsx";
import { useIsMobile } from "../lib/useIsMobile.js";

// focus n'a de sens qu'une fois un appareil choisi (bouton "Focus" d'une
// carte dans Appareils) — inerte tant qu'aucun n'est sélectionné.
const BASE_ITEMS = [
  { id: "console", enabled: true },
  { id: "devices", enabled: true },
  { id: "focus", enabled: false },
  { id: "routines", enabled: true },
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

export default function Dock({ active, onNavigate, focusEnabled = false }) {
  const isMobile = useIsMobile();
  const items = BASE_ITEMS.map((item) =>
    item.id === "focus" ? { ...item, enabled: focusEnabled } : item,
  );

  // Sur mobile, le dock devient une barre basse (pas de reactor ni de
  // pastille compte — juste la navigation, à portée de pouce). Sur
  // desktop, barre latérale complète comme dans le design.
  if (isMobile) {
    return (
      <div
        style={{
          height: 64,
          flex: "none",
          borderTop: "1px solid var(--stroke-soft)",
          background: "var(--bg-2)",
          display: "flex",
          justifyContent: "space-around",
          alignItems: "center",
          order: 2,
        }}
      >
        {items.map((item) => {
          const isActive = item.id === active;
          return (
            <button
              key={item.id}
              type="button"
              title={item.enabled ? item.id : `${item.id} — bientôt`}
              onClick={() => item.enabled && onNavigate(item.id)}
              disabled={!item.enabled}
              style={{
                width: 44,
                height: 44,
                borderRadius: 12,
                display: "grid",
                placeItems: "center",
                background: isActive ? "var(--cyan-dim)" : "transparent",
                border: "none",
                opacity: item.enabled ? 1 : 0.4,
                padding: 0,
              }}
            >
              <DockShape id={item.id} active={isActive} />
            </button>
          );
        })}
      </div>
    );
  }

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
        {items.map((item) => {
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

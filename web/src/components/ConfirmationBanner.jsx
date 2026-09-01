import { useConfirmations } from "../lib/useConfirmations.js";

// Montée au niveau App.jsx (pas dans un panneau précis) : une confirmation
// d'écriture Drive peut arriver pendant que Monsieur regarde n'importe
// quelle vue de la Console, elle doit rester visible partout. Miroir web de
// la bulle Qt bloquante du HUD desktop (agents/desktop/ui/dialogs.py) —
// voir brain/integrations/confirm.py pour le mécanisme côté brain.
export default function ConfirmationBanner() {
  const { pending, resolve } = useConfirmations();

  if (pending.length === 0) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: 16,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        width: "min(520px, calc(100vw - 32px))",
      }}
    >
      {pending.map((c) => (
        <div
          key={c.id}
          style={{
            background: "var(--bg-2)",
            border: "1px solid var(--cyan)",
            borderRadius: 14,
            padding: "16px 18px",
            boxShadow: "0 12px 40px -12px var(--glow)",
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--cyan)", boxShadow: "0 0 8px var(--cyan)", flex: "none" }} />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: ".14em", textTransform: "uppercase", color: "var(--cyan)" }}>
              Confirmation requise
            </span>
          </div>
          <div style={{ fontSize: 13, lineHeight: 1.5 }}>{c.summary}</div>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button
              onClick={() => resolve(c.id, false)}
              style={{
                border: "1px solid var(--stroke-soft)", borderRadius: 9, padding: "8px 14px", fontSize: 12,
                background: "transparent", color: "var(--muted)", cursor: "pointer",
              }}
            >
              Refuser
            </button>
            <button
              onClick={() => resolve(c.id, true)}
              style={{
                border: "1px solid var(--stroke)", borderRadius: 9, padding: "8px 14px", fontSize: 12,
                background: "var(--cyan-dim)", color: "var(--cyan)", cursor: "pointer", fontWeight: 600,
              }}
            >
              Confirmer
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

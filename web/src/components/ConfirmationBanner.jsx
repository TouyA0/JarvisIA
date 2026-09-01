import Icon from "./ui/Icon.jsx";
import { useConfirmations } from "../lib/useConfirmations.js";

// Montée au niveau App.jsx (pas dans un panneau précis) : une confirmation
// d'écriture Drive peut arriver pendant que Monsieur regarde n'importe
// quelle vue de la Console, elle doit rester visible partout. Miroir web de
// la bulle Qt bloquante du HUD desktop (agents/desktop/ui/dialogs.py) —
// voir brain/integrations/confirm.py pour le mécanisme côté brain.
//
// `role="alertdialog"` + `aria-live="assertive"` : contrairement aux
// notifications ordinaires (Toast.jsx, en `polite`), celle-ci mérite
// d'interrompre — un thread côté brain attend la réponse jusqu'à 90 s, et
// sans réponse l'action est simplement abandonnée.
export default function ConfirmationBanner() {
  const { pending, resolve } = useConfirmations();

  if (pending.length === 0) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: "var(--sp-4)",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 140,
        display: "flex",
        flexDirection: "column",
        gap: "var(--sp-2)",
        width: "min(520px, calc(100vw - 32px))",
      }}
      role="alertdialog"
      aria-live="assertive"
      aria-label="Confirmation requise"
    >
      {pending.map((c) => (
        <div
          key={c.id}
          className="card"
          style={{
            borderColor: "var(--cyan)",
            boxShadow: "var(--shadow-md), 0 0 40px -20px var(--glow)",
            animation: "fade-up var(--dur) var(--ease)",
          }}
        >
          <div className="row" style={{ gap: "var(--sp-2)" }}>
            <span className="dot dot--cyan dot--pulse" aria-hidden="true" />
            <span className="section-label" style={{ color: "var(--cyan)" }}>
              Confirmation requise
            </span>
          </div>
          <p style={{ fontSize: "var(--text-base)", lineHeight: 1.5 }}>{c.summary}</p>
          <div className="card-actions">
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => resolve(c.id, false)}>
              <Icon name="x" size={15} />
              Refuser
            </button>
            <button type="button" className="btn btn--primary btn--sm" onClick={() => resolve(c.id, true)}>
              <Icon name="check" size={15} />
              Confirmer
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

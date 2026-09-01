/**
 * Pastille d'état textuelle. La couleur ne porte jamais l'information à
 * elle seule — il y a toujours le mot à côté (« en ligne », « hors
 * ligne »), sans quoi l'état est invisible pour un daltonien comme pour
 * un lecteur d'écran.
 */
const TONES = {
  ok: { badge: "badge--ok", dot: "dot--ok" },
  danger: { badge: "badge--danger", dot: "dot--danger" },
  cyan: { badge: "badge--cyan", dot: "dot--cyan" },
  warn: { badge: "badge--warn", dot: "" },
  neutral: { badge: "", dot: "" },
};

export default function StatusBadge({ tone = "neutral", children, pulse = false }) {
  const t = TONES[tone] || TONES.neutral;
  return (
    <span className={`badge ${t.badge}`.trim()}>
      <span className={`dot ${t.dot} ${pulse ? "dot--pulse" : ""}`.trim()} aria-hidden="true" />
      {children}
    </span>
  );
}

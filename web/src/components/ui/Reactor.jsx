/**
 * Le réacteur : signature visuelle de Jarvis, et accessoirement le seul
 * indicateur d'état permanent de l'interface. Il porte maintenant une
 * information (`state`) au lieu de tourner toujours pareil — arc rapide
 * quand le brain travaille, cœur qui respire quand le micro écoute,
 * rouge et figé quand le brain est injoignable.
 *
 * Purement décoratif pour un lecteur d'écran : l'état est écrit en toutes
 * lettres à côté (voir StatusBadge), donc `aria-hidden`.
 */
export default function Reactor({ size = 34, state = "idle" }) {
  return (
    <span
      className={`reactor reactor--${state}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <span className="reactor-core" style={{ width: size * 0.26, height: size * 0.26 }} />
      <span className="reactor-arc" />
    </span>
  );
}

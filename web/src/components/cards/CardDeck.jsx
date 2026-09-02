import CardView from "./CardView.jsx";
import Icon from "../ui/Icon.jsx";

/** Bandeau de cartes (agenda, mails, capture d'écran…) partagé par le
 * Pupitre et la Conversation — voir docs/ROADMAP_DISPLAY_INTEGRATIONS.md §2.
 * `className` ajoute la variante propre à chaque vue (ex. `hud-deck--strip`
 * pour l'accroche au-dessus du fil de la Conversation). */
export default function CardDeck({ cards, dismiss, clearAll, className = "" }) {
  if (cards.length === 0) return null;
  return (
    <section className={`hud-deck${className ? ` ${className}` : ""}`} aria-label="Affichages de Jarvis">
      <div className="hud-deck-head">
        <h2 className="section-label">Affichage</h2>
        <button type="button" className="btn btn--ghost btn--sm" onClick={clearAll}>
          <Icon name="x" size={15} />
          Tout effacer
        </button>
      </div>
      <div className="hud-deck-grid">
        {cards.map((card) => (
          <CardView key={card.id} card={card} onDismiss={dismiss} />
        ))}
      </div>
    </section>
  );
}

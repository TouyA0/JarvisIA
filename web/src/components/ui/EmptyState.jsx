import Icon from "./Icon.jsx";

/**
 * Écran vide utile : ce qu'on regarde, pourquoi c'est vide, et le geste
 * suivant sous forme de bouton. L'ancienne Console se contentait d'une
 * phrase grise (« Aucune routine — crées-en une à droite »), qui pointe
 * vers un panneau que Monsieur ne voit même pas sur mobile.
 */
export default function EmptyState({ icon = "info", title, text, action }) {
  return (
    <div className="empty">
      <span className="empty-icon" aria-hidden="true">
        <Icon name={icon} size={24} />
      </span>
      <h2 className="empty-title">{title}</h2>
      {text && <p className="empty-text">{text}</p>}
      {action}
    </div>
  );
}

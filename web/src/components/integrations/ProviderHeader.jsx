import Icon from "../ui/Icon.jsx";
import StatusBadge from "../ui/StatusBadge.jsx";

/** En-tête de section : l'unique endroit où vivent les identifiants
 * d'application d'un fournisseur, et où leur état est affiché. */
export default function ProviderHeader({ group, status, provider, onConfigure }) {
  return (
    <div className="group-head">
      <div className="view-heading spacer">
        <h2 className="group-title">{group.title}</h2>
        {group.description && <p className="hint">{group.description}</p>}
      </div>

      {provider && (
        <div className="group-status">
          {status?.configured ? (
            <>
              <StatusBadge tone="ok">identifiants enregistrés</StatusBadge>
              <span className="hint">
                {status.source === "console" ? "saisis ici" : "lus depuis .env"}
                {status.region ? ` · région .${status.region}` : ""}
                {status.client_id ? ` · ${status.client_id.slice(0, 16)}…` : ""}
              </span>
            </>
          ) : (
            <>
              <StatusBadge tone="warn">identifiants manquants</StatusBadge>
              <span className="hint">
                Aucune connexion {provider.label} possible tant qu'ils ne sont pas remplis.
              </span>
            </>
          )}
          <button type="button" className="btn btn--sm" onClick={() => onConfigure(group)}>
            <Icon name="key" size={15} />
            {status?.configured ? "Modifier" : "Renseigner"}
          </button>
        </div>
      )}
    </div>
  );
}

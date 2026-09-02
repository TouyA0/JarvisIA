import { useState } from "react";
import Icon from "../ui/Icon.jsx";

/** Compte inconnu de `health` (pas encore sondé) : traité comme sain plutôt
 * que d'afficher un état d'échec injustifié avant la première réponse. */
export default function AccountRow({ account, health, onDisconnect, onCheck }) {
  const [checking, setChecking] = useState(false);
  const unhealthy = health?.healthy === false;

  async function check() {
    setChecking(true);
    try {
      await onCheck(account.id);
    } finally {
      setChecking(false);
    }
  }

  return (
    <li className="account-row">
      <span className={`dot ${unhealthy ? "dot--danger" : "dot--ok"}`} aria-hidden="true" />
      <span className="spacer account-label">
        {account.label}
        {unhealthy && (
          <span className="hint" style={{ display: "block" }} title={health.error || undefined}>
            à reconnecter — jeton refusé
          </span>
        )}
      </span>
      <button
        type="button"
        className="icon-btn icon-btn--sm"
        onClick={check}
        disabled={checking}
        aria-label={`Vérifier ${account.label}`}
        title="Vérifier la connexion"
      >
        <Icon name="refresh" size={14} />
      </button>
      <button
        type="button"
        className="btn btn--ghost btn--sm"
        onClick={() => onDisconnect(account)}
        aria-label={`Déconnecter ${account.label}`}
      >
        Déconnecter
      </button>
    </li>
  );
}

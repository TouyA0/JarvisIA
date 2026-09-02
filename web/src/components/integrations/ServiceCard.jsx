import Icon from "../ui/Icon.jsx";
import StatusBadge from "../ui/StatusBadge.jsx";
import AccountRow from "./AccountRow.jsx";

export default function ServiceCard({
  service,
  provider,
  providerReady,
  accounts,
  health = {},
  onConnect,
  onConfigure,
  onDisconnect,
  onCheckHealth,
  connecting,
}) {
  const connected = accounts.length > 0;
  const anyUnhealthy = accounts.some((a) => health[a.id]?.healthy === false);

  return (
    <div className="card card--interactive">
      <div className="card-head" style={{ alignItems: "center" }}>
        <span className="empty-icon" style={{ width: 36, height: 36 }} aria-hidden="true">
          <Icon name={service.icon} size={17} />
        </span>
        <h3 className="card-title spacer">{service.label}</h3>
        {connected &&
          (anyUnhealthy ? (
            <StatusBadge tone="warn">à reconnecter</StatusBadge>
          ) : (
            <StatusBadge tone="ok">{accounts.length > 1 ? `${accounts.length} comptes` : "connecté"}</StatusBadge>
          ))}
      </div>

      <p className="card-sub" style={{ whiteSpace: "normal", overflow: "visible" }}>
        {service.summary}
      </p>

      {accounts.length > 0 && (
        <ul className="account-list">
          {accounts.map((a) => (
            <AccountRow key={a.id} account={a} health={health[a.id]} onDisconnect={onDisconnect} onCheck={onCheckHealth} />
          ))}
        </ul>
      )}

      <div className="card-actions">
        {provider && (
          <button
            type="button"
            className="btn btn--accent btn--sm"
            onClick={() => onConnect(service)}
            disabled={!providerReady || connecting}
            title={providerReady ? undefined : `Renseignez d'abord les identifiants ${provider.label}`}
          >
            {connecting ? <span className="spinner" aria-hidden="true" /> : <Icon name="link" size={15} />}
            {connected ? "Ajouter un compte" : "Connecter"}
          </button>
        )}
        {service.connect && (
          <button type="button" className="btn btn--accent btn--sm" onClick={() => onConfigure(service)}>
            <Icon name="link" size={15} />
            {connected ? "Ajouter un compte" : "Connecter"}
          </button>
        )}
        {service.settings && (
          <button type="button" className="btn btn--sm" onClick={() => onConfigure(service)}>
            <Icon name="system" size={15} />
            Configurer
          </button>
        )}
      </div>
    </div>
  );
}

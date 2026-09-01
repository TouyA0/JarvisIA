import { useState } from "react";
import { ViewHeader } from "./AppShell.jsx";
import Icon from "./ui/Icon.jsx";
import Modal from "./ui/Modal.jsx";
import StatusBadge from "./ui/StatusBadge.jsx";
import { SelectField, TextField } from "./ui/Field.jsx";
import { useConfirm } from "./ui/Confirm.jsx";
import { useToast } from "./ui/Toast.jsx";
import { useIntegrations } from "../lib/useIntegrations.js";

/**
 * Services tiers, rangés par fournisseur.
 *
 * Deux erreurs corrigées ici. La première version empilait sept
 * accordéons dans une colonne de 298 px. La deuxième posait une carte par
 * service, mais répétait le bouton « Paramètres Google » sur les quatre
 * cartes Google — alors qu'il s'agit d'un seul et même compte
 * d'application — sans jamais dire clairement s'il était déjà rempli.
 *
 * Maintenant : une section par fournisseur. Les identifiants
 * d'application (Client ID / Secret) appartiennent à la section, pas aux
 * services ; leur état est écrit en toutes lettres en tête de section,
 * une seule fois. Les cartes ne portent plus que ce qui leur est propre :
 * leurs comptes connectés.
 */

// ── Fournisseurs OAuth ──────────────────────────────────────────────────
const PROVIDERS = {
  google: {
    label: "Google",
    settingsKey: "googleSettings",
    connectKey: "connectGoogle",
    fields: [
      { name: "clientId", label: "Client ID", required: true },
      { name: "clientSecret", label: "Client Secret", type: "password", required: true },
    ],
    save: (api, v) => api.saveGoogleSettings(v.clientId, v.clientSecret),
    clear: (api) => api.clearGoogleSettings(),
    doc: "À créer une seule fois dans la Google Cloud Console (voir README.md, section Google Calendar) — c'est la seule étape que Google n'autorise pas à faire depuis un site tiers.",
  },
  zoho: {
    label: "Zoho",
    settingsKey: "zohoSettings",
    connectKey: "connectZoho",
    fields: [
      { name: "clientId", label: "Client ID", required: true },
      { name: "clientSecret", label: "Client Secret", type: "password", required: true },
      {
        name: "region",
        label: "Région du compte",
        type: "select",
        default: "com",
        options: [
          { value: "com", label: ".com (États-Unis, par défaut)" },
          { value: "eu", label: ".eu (Europe)" },
          { value: "in", label: ".in (Inde)" },
          { value: "com.au", label: ".com.au (Australie)" },
          { value: "jp", label: ".jp (Japon)" },
          { value: "ca", label: ".ca (Canada)" },
        ],
        hint: "Doit correspondre au datacenter de votre compte Zoho, sinon la connexion échoue entièrement.",
      },
    ],
    save: (api, v) => api.saveZohoSettings(v.clientId, v.clientSecret, v.region),
    clear: (api) => api.clearZohoSettings(),
    doc: "À créer une seule fois dans la Console API Zoho (voir README.md, section Zoho Mail).",
  },
  spotify: {
    label: "Spotify",
    settingsKey: "spotifySettings",
    connectKey: "connectSpotify",
    fields: [
      { name: "clientId", label: "Client ID", required: true },
      { name: "clientSecret", label: "Client Secret", type: "password", required: true },
    ],
    save: (api, v) => api.saveSpotifySettings(v.clientId, v.clientSecret),
    clear: (api) => api.clearSpotifySettings(),
    doc: "À créer une seule fois sur developer.spotify.com/dashboard (voir README.md, section Spotify).",
  },
};

// ── Sections ────────────────────────────────────────────────────────────
// `summary` répond à la seule question qui compte devant un bouton
// « Connecter » : qu'est-ce que Jarvis saura faire de plus après ?
const GROUPS = [
  {
    id: "google",
    title: "Google",
    provider: "google",
    description:
      "Un seul compte d'application Google ouvre ces quatre services : les identifiants ne sont à renseigner qu'une fois.",
    services: [
      {
        type: "google_calendar",
        label: "Calendar",
        icon: "clock",
        summary: "Consulter l'agenda et annoncer les prochains rendez-vous.",
      },
      { type: "gmail", label: "Gmail", icon: "chat", summary: "Chercher, lire et rédiger des mails." },
      {
        type: "google_drive",
        label: "Drive",
        icon: "copy",
        summary: "Chercher, lire et créer des documents (toute écriture est confirmée).",
      },
      {
        type: "google_contacts",
        label: "Contacts",
        icon: "devices",
        summary: "Retrouver un contact par son nom.",
      },
    ],
  },
  {
    id: "zoho",
    title: "Zoho",
    provider: "zoho",
    services: [
      {
        type: "zoho_mail",
        label: "Zoho Mail",
        icon: "chat",
        summary: "Même chose que Gmail, pour une boîte Zoho.",
      },
    ],
  },
  {
    id: "spotify",
    title: "Spotify",
    provider: "spotify",
    services: [
      {
        type: "spotify",
        label: "Spotify",
        icon: "play",
        summary: "Lancer une musique, contrôler la lecture, afficher la pochette.",
      },
    ],
  },
  {
    id: "local",
    title: "Serveurs personnels",
    description: "Chez vous, sans OAuth : une adresse et une clé suffisent.",
    services: [
      {
        type: "jellyfin",
        label: "Jellyfin",
        icon: "play",
        summary: "Reprendre un film ou une série depuis votre médiathèque.",
        connect: {
          title: "Connecter Jellyfin",
          fields: [
            { name: "baseUrl", label: "URL du serveur", placeholder: "http://192.168.1.20:8096", required: true },
            { name: "apiKey", label: "Clé API", type: "password", required: true },
            {
              name: "username",
              label: "Utilisateur Jellyfin",
              hint: "Facultatif. Sans lui, Jellyfin prend le premier compte du serveur — à préciser si plusieurs comptes existent, la reprise de lecture en dépend.",
            },
          ],
          submitLabel: "Connecter",
          submit: (api, v) => api.connectJellyfin(v.baseUrl, v.apiKey, v.username),
          doc: "Clé API générée depuis le tableau de bord Jellyfin : Admin → Clés API.",
        },
      },
      {
        type: "home_assistant",
        label: "Home Assistant",
        icon: "power",
        summary: "Piloter les lumières, prises, volets et scènes.",
        connect: {
          title: "Connecter Home Assistant",
          fields: [
            { name: "baseUrl", label: "URL de l'instance", placeholder: "http://192.168.1.30:8123", required: true },
            { name: "token", label: "Token longue durée", type: "password", required: true },
          ],
          submitLabel: "Connecter",
          submit: (api, v) => api.connectHomeAssistant(v.baseUrl, v.token),
          doc: "Token généré depuis votre profil Home Assistant, en bas de page : « Jetons d'accès de longue durée » → Créer un jeton.",
        },
      },
    ],
  },
  {
    id: "keys",
    title: "Services à clé API",
    description: "Clés gratuites, à créer une fois chez le fournisseur.",
    services: [
      {
        type: "tisseo",
        label: "Tisséo",
        icon: "clock",
        summary: "Prochains passages aux arrêts favoris (transports toulousains).",
        settingsKey: "tisseoSettings",
        settings: {
          title: "Tisséo",
          sections: [
            {
              id: "key",
              title: "Clé API",
              fields: [{ name: "apiKey", label: "Clé API Tisséo", type: "password", required: true }],
              submitLabel: "Enregistrer la clé",
              submit: (api, v) => api.saveTisseoSettings(v.apiKey),
              clearLabel: "Effacer la clé",
              clear: (api) => api.clearTisseoSettings(),
              canClear: (s) => s.configured,
            },
            {
              id: "stop",
              title: "Arrêt favori",
              fields: [{ name: "stop", label: "Nom de l'arrêt", placeholder: "Jean Jaurès", required: true }],
              submitLabel: "Ajouter aux favoris",
              submit: (api, v) => api.connectTisseo(v.stop),
              requiresConfigured: true,
              hint: "Plusieurs arrêts peuvent être ajoutés : leurs prochains passages sont fusionnés automatiquement.",
            },
          ],
          doc: "Clé gratuite (voir README.md, section Tisséo).",
        },
      },
      {
        type: "ors",
        label: "Itinéraires",
        icon: "link",
        summary: "Temps de trajet et itinéraires (OpenRouteService).",
        settingsKey: "orsSettings",
        noAccounts: true,
        settings: {
          title: "Itinéraires (OpenRouteService)",
          sections: [
            {
              id: "key",
              title: "Clé API",
              fields: [{ name: "apiKey", label: "Clé API OpenRouteService", type: "password", required: true }],
              submitLabel: "Enregistrer la clé",
              submit: (api, v) => api.saveOrsSettings(v.apiKey),
              clearLabel: "Effacer la clé",
              clear: (api) => api.clearOrsSettings(),
              canClear: (s) => s.configured,
            },
            {
              id: "home",
              title: "Adresse du domicile",
              fields: [
                { name: "address", label: "Adresse", placeholder: "12 rue de la Paix, Toulouse", required: true },
              ],
              submitLabel: "Enregistrer le domicile",
              submit: (api, v) => api.saveHomeAddress(v.address),
              clearLabel: "Effacer",
              clear: (api) => api.clearHomeAddress(),
              canClear: (s) => !!s.home_address,
              hint: "Origine par défaut quand vous ne donnez que la destination (« combien de temps pour aller à X ? »).",
            },
          ],
          doc: "Clé gratuite et sans facturation, sur openrouteservice.org (voir README.md, section Itinéraires).",
        },
      },
      {
        type: "brave",
        label: "Recherche web",
        icon: "search",
        summary: "Chercher sur le web et résumer une page pour répondre à une question d'actualité.",
        settingsKey: "braveSettings",
        noAccounts: true,
        settings: {
          title: "Recherche web (Brave Search)",
          sections: [
            {
              id: "key",
              title: "Clé API",
              fields: [{ name: "apiKey", label: "Clé API Brave Search", type: "password", required: true }],
              submitLabel: "Enregistrer la clé",
              submit: (api, v) => api.saveBraveSettings(v.apiKey),
              clearLabel: "Effacer la clé",
              clear: (api) => api.clearBraveSettings(),
              canClear: (s) => s.configured,
            },
          ],
          doc: "Clé gratuite (2000 requêtes/mois), sur brave.com/search/api (voir README.md, section Recherche web).",
        },
      },
    ],
  },
];

/** Formulaire générique : une ou plusieurs sections, chacune avec ses
 * champs, son bouton d'envoi et son éventuel bouton d'effacement. Couvre
 * les trois familles (identifiants d'application, connexion directe, clé
 * API), qui étaient auparavant trois composants quasi identiques recopiés
 * à sept exemplaires. */
function FormModal({ open, onClose, title, description, doc, sections, api, status, onDone }) {
  const toast = useToast();
  const [values, setValues] = useState({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  function valueOf(section, field) {
    return values[`${section.id || "main"}.${field.name}`] ?? field.default ?? "";
  }

  function setValue(section, field, v) {
    setValues((prev) => ({ ...prev, [`${section.id || "main"}.${field.name}`]: v }));
  }

  async function submit(section) {
    const payload = Object.fromEntries(section.fields.map((f) => [f.name, valueOf(section, f).trim()]));
    const missing = section.fields.find((f) => f.required && !payload[f.name]);
    if (missing) {
      setError(`« ${missing.label} » est obligatoire.`);
      return;
    }
    setError("");
    setBusy(section.id || "main");
    try {
      await section.submit(api, payload);
      toast.success(section.successMessage || "Enregistré.");
      setValues((prev) => {
        const next = { ...prev };
        section.fields.forEach((f) => delete next[`${section.id || "main"}.${f.name}`]);
        return next;
      });
      onDone?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  async function clear(section) {
    setBusy(section.id || "main");
    try {
      await section.clear(api);
      toast.info("Réglage effacé.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      footer={
        <button type="button" className="btn btn--ghost" onClick={onClose}>
          Fermer
        </button>
      }
    >
      {error && (
        <div className="alert alert--danger" role="alert">
          <Icon name="alert" size={16} />
          {error}
        </div>
      )}

      {sections.map((section) => {
        const blocked = section.requiresConfigured && !status?.configured;
        return (
          <section key={section.id || "main"} className="stack">
            {sections.length > 1 && <h3 className="section-label">{section.title}</h3>}

            {blocked && (
              <div className="alert alert--warn">
                <Icon name="info" size={16} />
                Enregistrez d'abord la clé API ci-dessus.
              </div>
            )}

            {section.fields.map((field) =>
              field.type === "select" ? (
                <SelectField
                  key={field.name}
                  label={field.label}
                  hint={field.hint}
                  value={valueOf(section, field)}
                  onChange={(e) => setValue(section, field, e.target.value)}
                >
                  {field.options.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </SelectField>
              ) : (
                <TextField
                  key={field.name}
                  label={field.label}
                  type={field.type || "text"}
                  placeholder={field.placeholder}
                  hint={field.hint}
                  required={field.required}
                  autoComplete="off"
                  value={valueOf(section, field)}
                  onChange={(e) => setValue(section, field, e.target.value)}
                  disabled={blocked}
                />
              ),
            )}

            {section.hint && <p className="hint">{section.hint}</p>}

            <div className="row" style={{ justifyContent: "flex-end" }}>
              {section.clear && section.canClear?.(status || {}) && (
                <button
                  type="button"
                  className="btn btn--danger btn--sm"
                  onClick={() => clear(section)}
                  disabled={busy !== ""}
                >
                  {section.clearLabel || "Effacer"}
                </button>
              )}
              <button
                type="button"
                className="btn btn--primary btn--sm"
                onClick={() => submit(section)}
                disabled={busy !== "" || blocked}
              >
                {busy === (section.id || "main") && <span className="spinner" aria-hidden="true" />}
                {section.submitLabel || "Enregistrer"}
              </button>
            </div>
          </section>
        );
      })}

      {doc && (
        <div className="alert">
          <Icon name="info" size={16} />
          {doc}
        </div>
      )}
    </Modal>
  );
}

/** En-tête de section : l'unique endroit où vivent les identifiants
 * d'application d'un fournisseur, et où leur état est affiché. */
function ProviderHeader({ group, status, provider, onConfigure }) {
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

function ServiceCard({
  service,
  provider,
  providerReady,
  accounts,
  onConnect,
  onConfigure,
  onDisconnect,
  connecting,
}) {
  const connected = accounts.length > 0;

  return (
    <div className="card card--interactive">
      <div className="card-head" style={{ alignItems: "center" }}>
        <span className="empty-icon" style={{ width: 36, height: 36 }} aria-hidden="true">
          <Icon name={service.icon} size={17} />
        </span>
        <h3 className="card-title spacer">{service.label}</h3>
        {connected && (
          <StatusBadge tone="ok">{accounts.length > 1 ? `${accounts.length} comptes` : "connecté"}</StatusBadge>
        )}
      </div>

      <p className="card-sub" style={{ whiteSpace: "normal", overflow: "visible" }}>
        {service.summary}
      </p>

      {accounts.length > 0 && (
        <ul className="account-list">
          {accounts.map((a) => (
            <li key={a.id} className="account-row">
              <span className="dot dot--ok" aria-hidden="true" />
              <span className="spacer account-label">{a.label}</span>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => onDisconnect(a)}
                aria-label={`Déconnecter ${a.label}`}
              >
                Déconnecter
              </button>
            </li>
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

export default function Integrations() {
  const api = useIntegrations();
  const confirm = useConfirm();
  const toast = useToast();
  const [dialog, setDialog] = useState(null); // { kind: "provider" | "service", … }
  const [connecting, setConnecting] = useState(null);

  async function handleConnect(service) {
    const group = GROUPS.find((g) => g.services.includes(service));
    const provider = PROVIDERS[group.provider];
    setConnecting(service.type);
    try {
      await api[provider.connectKey](service.type);
      toast.info("Autorisez Jarvis dans la fenêtre qui vient de s'ouvrir.");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setConnecting(null);
    }
  }

  async function handleDisconnect(account) {
    const ok = await confirm({
      title: `Déconnecter « ${account.label} » ?`,
      message: "Jarvis perdra l'accès à ce compte. Vous pourrez le reconnecter à tout moment.",
      confirmLabel: "Déconnecter",
    });
    if (!ok) return;
    await api.remove(account.id);
    toast.success("Compte déconnecté.");
  }

  const accountsFor = (type) => api.accounts.filter((a) => a.type === type);

  // Un seul dialogue générique, alimenté selon ce qui a été ouvert :
  // identifiants d'un fournisseur, connexion directe, ou clé API.
  let dialogProps = null;
  if (dialog?.kind === "provider") {
    const provider = PROVIDERS[dialog.group.provider];
    const status = api[provider.settingsKey];
    dialogProps = {
      title: `Identifiants ${provider.label}`,
      description: status.configured
        ? "Déjà configuré — remplacez les valeurs ci-dessous pour les changer."
        : `Compte d'application ${provider.label}, à créer une fois chez le fournisseur.`,
      doc: provider.doc,
      status,
      sections: [
        {
          id: "app",
          fields: provider.fields,
          submitLabel: "Enregistrer",
          submit: (a, v) => provider.save(a, v),
          clear: (a) => provider.clear(a),
          clearLabel: "Effacer",
          canClear: (s) => s.configured,
          successMessage: `Identifiants ${provider.label} enregistrés.`,
        },
      ],
      closeOnDone: true,
    };
  } else if (dialog?.kind === "service") {
    const service = dialog.service;
    if (service.connect) {
      dialogProps = {
        title: service.connect.title,
        doc: service.connect.doc,
        status: null,
        sections: [
          {
            id: "connect",
            fields: service.connect.fields,
            submitLabel: service.connect.submitLabel,
            submit: service.connect.submit,
            successMessage: `${service.label} connecté.`,
          },
        ],
        // Une connexion réussie n'a pas de suite dans ce dialogue : on
        // referme. Les réglages à deux temps (clé Tisséo puis arrêt
        // favori) restent ouverts, la seconde section suit la première.
        closeOnDone: true,
      };
    } else if (service.settings) {
      dialogProps = {
        title: service.settings.title,
        doc: service.settings.doc,
        status: api[service.settingsKey],
        sections: service.settings.sections,
      };
    }
  }

  const connectedCount = api.accounts.length;

  return (
    <>
      <ViewHeader
        title="Intégrations"
        subtitle={
          connectedCount === 0
            ? "Aucun compte connecté"
            : `${connectedCount} compte${connectedCount > 1 ? "s" : ""} connecté${connectedCount > 1 ? "s" : ""}`
        }
      />

      <div className="view-body">
        <div className="view-main">
          <div className="stack" style={{ gap: "var(--sp-8)", maxWidth: "var(--content-max)" }}>
            {GROUPS.map((group) => {
              const provider = group.provider ? PROVIDERS[group.provider] : null;
              const status = provider ? api[provider.settingsKey] : null;
              return (
                <section key={group.id} className="group">
                  <ProviderHeader
                    group={group}
                    provider={provider}
                    status={status}
                    onConfigure={(g) => setDialog({ kind: "provider", group: g })}
                  />
                  <div className="grid">
                    {group.services.map((service) => (
                      <ServiceCard
                        key={service.type}
                        service={service}
                        provider={provider}
                        providerReady={!!status?.configured}
                        accounts={service.noAccounts ? [] : accountsFor(service.type)}
                        connecting={connecting === service.type}
                        onConnect={handleConnect}
                        onConfigure={(s) => setDialog({ kind: "service", service: s })}
                        onDisconnect={handleDisconnect}
                      />
                    ))}
                  </div>
                </section>
              );
            })}

            <p className="hint">
              Plusieurs comptes peuvent être connectés en parallèle sur un même service — les résultats de
              chacun sont fusionnés automatiquement.
            </p>
          </div>
        </div>
      </div>

      {dialogProps && (
        <FormModal
          open={!!dialog}
          onClose={() => setDialog(null)}
          api={api}
          onDone={() => {
            if (dialogProps.closeOnDone) setDialog(null);
          }}
          {...dialogProps}
        />
      )}
    </>
  );
}

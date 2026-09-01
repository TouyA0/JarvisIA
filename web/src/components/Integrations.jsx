import { useState } from "react";
import Frame from "./Frame.jsx";
import { useIntegrations } from "../lib/useIntegrations.js";
import { useIsMobile } from "../lib/useIsMobile.js";

const TYPE_LABELS = {
  google_calendar: "Google Calendar",
  google_drive: "Google Drive",
  gmail: "Gmail",
  google_contacts: "Google Contacts",
  zoho_mail: "Zoho Mail",
  spotify: "Spotify",
  jellyfin: "Jellyfin",
};

// Catalogue affiché à droite — google_calendar/google_drive/gmail/
// google_contacts (Google, un seul Client ID/Secret), zoho_mail (Zoho) et
// spotify (Spotify) sont branchés ; le reste vient
// docs/ROADMAP_DISPLAY_INTEGRATIONS.md et attend son tour (même socle, un
// module brain/integrations/<service>.py de plus).
const CATALOG = [
  { type: "google_calendar", label: "Google Calendar", provider: "google", available: true },
  { type: "google_drive", label: "Google Drive", provider: "google", available: true },
  { type: "gmail", label: "Gmail", provider: "google", available: true },
  { type: "google_contacts", label: "Google Contacts", provider: "google", available: true },
  { type: "zoho_mail", label: "Zoho Mail", provider: "zoho", available: true },
  { type: "spotify", label: "Spotify", provider: "spotify", available: true },
];

function Topbar({ count }) {
  return (
    <div
      style={{
        height: 54,
        flex: "none",
        borderBottom: "1px solid var(--stroke-soft)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 22px",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16 }}>Intégrations</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--faint)" }}>
          {count} compte{count > 1 ? "s" : ""} connecté{count > 1 ? "s" : ""}
        </span>
      </div>
    </div>
  );
}

function AccountCard({ account, onRemove }) {
  return (
    <div
      style={{
        background: "var(--bg-2)",
        border: "1px solid var(--stroke-soft)",
        borderRadius: 15,
        padding: 16,
        display: "flex",
        alignItems: "center",
        gap: 12,
      }}
    >
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--online)", boxShadow: "0 0 8px var(--online)", flex: "none" }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 14, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {account.label}
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--faint)" }}>
          {TYPE_LABELS[account.type] || account.type}
        </div>
      </div>
      <button
        onClick={() => onRemove(account.id)}
        style={{
          border: "1px solid var(--stroke-soft)",
          borderRadius: 9,
          padding: "7px 11px",
          fontSize: 12,
          background: "transparent",
          color: "var(--muted)",
          cursor: "pointer",
          flex: "none",
        }}
      >
        Déconnecter
      </button>
    </div>
  );
}

const _inputStyle = {
  background: "var(--bg)",
  border: "1px solid var(--stroke-soft)",
  borderRadius: 8,
  padding: "8px 10px",
  fontSize: 12,
  color: "var(--fg)",
  fontFamily: "var(--font-mono)",
};

function GoogleAppSettings({ status, onSave, onClear }) {
  const [open, setOpen] = useState(false);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSave() {
    setError("");
    setBusy(true);
    try {
      await onSave(clientId.trim(), clientSecret.trim());
      setClientId("");
      setClientSecret("");
      setOpen(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ borderTop: "1px solid var(--stroke-soft)", paddingTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left", display: "flex", justifyContent: "space-between", alignItems: "center" }}
      >
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: ".16em", textTransform: "uppercase", color: "var(--faint)" }}>
          Paramètres Google
        </span>
        <span style={{ fontSize: 11, color: "var(--cyan)" }}>{open ? "−" : "+"}</span>
      </button>

      <div style={{ fontSize: 11, color: status.configured ? "var(--online)" : "var(--faint)" }}>
        {status.configured
          ? `Configuré (${status.source === "console" ? "saisi ici" : ".env"}) — ${status.client_id?.slice(0, 24)}…`
          : "Non configuré — aucune connexion Google possible tant que ça n'est pas rempli."}
      </div>

      {open && (
        <>
          <input placeholder="Client ID" value={clientId} onChange={(e) => setClientId(e.target.value)} style={_inputStyle} />
          <input placeholder="Client Secret" type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} style={_inputStyle} />
          {error && <div style={{ fontSize: 11, color: "#f87171" }}>{error}</div>}
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={handleSave}
              disabled={busy || !clientId.trim() || !clientSecret.trim()}
              style={{
                flex: 1, border: "1px solid var(--stroke)", borderRadius: 9, padding: "8px 0", fontSize: 12,
                background: "var(--cyan-dim)", color: "var(--cyan)", cursor: "pointer", opacity: busy ? 0.6 : 1,
              }}
            >
              Enregistrer
            </button>
            {status.configured && status.source === "console" && (
              <button
                onClick={onClear}
                style={{ border: "1px solid var(--stroke-soft)", borderRadius: 9, padding: "8px 11px", fontSize: 12, background: "transparent", color: "var(--muted)", cursor: "pointer" }}
              >
                Effacer
              </button>
            )}
          </div>
          <div style={{ fontSize: 11, color: "var(--faint)" }}>
            À créer une seule fois dans Google Cloud Console (voir README.md,
            section Google Calendar) — c'est la seule étape que Google
            n'autorise pas à faire depuis un site tiers.
          </div>
        </>
      )}
    </div>
  );
}

const _ZOHO_REGIONS = ["com", "eu", "in", "com.au", "jp", "ca"];

function ZohoAppSettings({ status, onSave, onClear }) {
  const [open, setOpen] = useState(false);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [region, setRegion] = useState("com");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSave() {
    setError("");
    setBusy(true);
    try {
      await onSave(clientId.trim(), clientSecret.trim(), region);
      setClientId("");
      setClientSecret("");
      setOpen(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ borderTop: "1px solid var(--stroke-soft)", paddingTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left", display: "flex", justifyContent: "space-between", alignItems: "center" }}
      >
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: ".16em", textTransform: "uppercase", color: "var(--faint)" }}>
          Paramètres Zoho
        </span>
        <span style={{ fontSize: 11, color: "var(--cyan)" }}>{open ? "−" : "+"}</span>
      </button>

      <div style={{ fontSize: 11, color: status.configured ? "var(--online)" : "var(--faint)" }}>
        {status.configured
          ? `Configuré (région .${status.region}) — ${status.client_id?.slice(0, 24)}…`
          : "Non configuré — aucune connexion Zoho possible tant que ça n'est pas rempli."}
      </div>

      {open && (
        <>
          <input placeholder="Client ID" value={clientId} onChange={(e) => setClientId(e.target.value)} style={_inputStyle} />
          <input placeholder="Client Secret" type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} style={_inputStyle} />
          <select value={region} onChange={(e) => setRegion(e.target.value)} style={_inputStyle}>
            {_ZOHO_REGIONS.map((r) => (
              <option key={r} value={r}>.{r} ({r === "com" ? "US, par défaut" : r === "eu" ? "Europe" : r})</option>
            ))}
          </select>
          {error && <div style={{ fontSize: 11, color: "#f87171" }}>{error}</div>}
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={handleSave}
              disabled={busy || !clientId.trim() || !clientSecret.trim()}
              style={{
                flex: 1, border: "1px solid var(--stroke)", borderRadius: 9, padding: "8px 0", fontSize: 12,
                background: "var(--cyan-dim)", color: "var(--cyan)", cursor: "pointer", opacity: busy ? 0.6 : 1,
              }}
            >
              Enregistrer
            </button>
            {status.configured && (
              <button
                onClick={onClear}
                style={{ border: "1px solid var(--stroke-soft)", borderRadius: 9, padding: "8px 11px", fontSize: 12, background: "transparent", color: "var(--muted)", cursor: "pointer" }}
              >
                Effacer
              </button>
            )}
          </div>
          <div style={{ fontSize: 11, color: "var(--faint)" }}>
            À créer une seule fois dans la Console API Zoho (voir README.md,
            section Zoho Mail). La région doit correspondre au datacenter de
            ton compte Zoho, sinon la connexion échoue entièrement.
          </div>
        </>
      )}
    </div>
  );
}

function SpotifyAppSettings({ status, onSave, onClear }) {
  const [open, setOpen] = useState(false);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSave() {
    setError("");
    setBusy(true);
    try {
      await onSave(clientId.trim(), clientSecret.trim());
      setClientId("");
      setClientSecret("");
      setOpen(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ borderTop: "1px solid var(--stroke-soft)", paddingTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left", display: "flex", justifyContent: "space-between", alignItems: "center" }}
      >
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: ".16em", textTransform: "uppercase", color: "var(--faint)" }}>
          Paramètres Spotify
        </span>
        <span style={{ fontSize: 11, color: "var(--cyan)" }}>{open ? "−" : "+"}</span>
      </button>

      <div style={{ fontSize: 11, color: status.configured ? "var(--online)" : "var(--faint)" }}>
        {status.configured
          ? `Configuré — ${status.client_id?.slice(0, 24)}…`
          : "Non configuré — aucune connexion Spotify possible tant que ça n'est pas rempli."}
      </div>

      {open && (
        <>
          <input placeholder="Client ID" value={clientId} onChange={(e) => setClientId(e.target.value)} style={_inputStyle} />
          <input placeholder="Client Secret" type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} style={_inputStyle} />
          {error && <div style={{ fontSize: 11, color: "#f87171" }}>{error}</div>}
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={handleSave}
              disabled={busy || !clientId.trim() || !clientSecret.trim()}
              style={{
                flex: 1, border: "1px solid var(--stroke)", borderRadius: 9, padding: "8px 0", fontSize: 12,
                background: "var(--cyan-dim)", color: "var(--cyan)", cursor: "pointer", opacity: busy ? 0.6 : 1,
              }}
            >
              Enregistrer
            </button>
            {status.configured && (
              <button
                onClick={onClear}
                style={{ border: "1px solid var(--stroke-soft)", borderRadius: 9, padding: "8px 11px", fontSize: 12, background: "transparent", color: "var(--muted)", cursor: "pointer" }}
              >
                Effacer
              </button>
            )}
          </div>
          <div style={{ fontSize: 11, color: "var(--faint)" }}>
            À créer une seule fois sur developer.spotify.com/dashboard (voir
            README.md, section Spotify).
          </div>
        </>
      )}
    </div>
  );
}

function JellyfinConnect({ onConnect }) {
  const [open, setOpen] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [username, setUsername] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Pas d'OAuth (serveur perso) : un seul formulaire, connexion directe —
  // pas de bloc "Paramètres" séparé comme pour Google/Zoho/Spotify.
  async function handleConnect() {
    setError("");
    setBusy(true);
    try {
      await onConnect(baseUrl.trim(), apiKey.trim(), username.trim());
      setBaseUrl("");
      setApiKey("");
      setUsername("");
      setOpen(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ borderTop: "1px solid var(--stroke-soft)", paddingTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left", display: "flex", justifyContent: "space-between", alignItems: "center" }}
      >
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: ".16em", textTransform: "uppercase", color: "var(--faint)" }}>
          Jellyfin
        </span>
        <span style={{ fontSize: 11, color: "var(--cyan)" }}>{open ? "−" : "+"}</span>
      </button>

      {open && (
        <>
          <input placeholder="URL du serveur (http://192.168.1.x:8096)" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} style={_inputStyle} />
          <input placeholder="Clé API" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} style={_inputStyle} />
          <input placeholder="Utilisateur Jellyfin (optionnel)" value={username} onChange={(e) => setUsername(e.target.value)} style={_inputStyle} />
          {error && <div style={{ fontSize: 11, color: "#f87171" }}>{error}</div>}
          <button
            onClick={handleConnect}
            disabled={busy || !baseUrl.trim() || !apiKey.trim()}
            style={{
              border: "1px solid var(--stroke)", borderRadius: 9, padding: "8px 0", fontSize: 12,
              background: "var(--cyan-dim)", color: "var(--cyan)", cursor: "pointer", opacity: busy ? 0.6 : 1,
            }}
          >
            Connecter
          </button>
          <div style={{ fontSize: 11, color: "var(--faint)" }}>
            Clé API générée depuis ton tableau de bord Jellyfin (Admin → Clés
            API). Sans nom d'utilisateur, Jellyfin prend le premier compte
            trouvé sur le serveur — précise-le si plusieurs comptes existent
            (reprise de lecture / nouveautés en dépendent).
          </div>
        </>
      )}
    </div>
  );
}

function CatalogRow({ entry, onConnect, busy, error }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 13, color: entry.available ? "var(--fg)" : "var(--faint)" }}>{entry.label}</span>
        {entry.available ? (
          <button
            onClick={() => onConnect(entry.type)}
            disabled={busy}
            style={{
              border: "1px solid var(--stroke)",
              borderRadius: 9,
              padding: "6px 11px",
              fontSize: 12,
              background: "var(--cyan-dim)",
              color: "var(--cyan)",
              cursor: busy ? "default" : "pointer",
              opacity: busy ? 0.6 : 1,
            }}
          >
            Connecter
          </button>
        ) : (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--faint)", textTransform: "uppercase" }}>
            bientôt
          </span>
        )}
      </div>
      {error && <div style={{ fontSize: 11, color: "#f87171" }}>{error}</div>}
    </div>
  );
}

const _CONNECTORS = {
  google: { connectKey: "connectGoogle", settingsKey: "googleSettings", label: "Paramètres Google" },
  zoho: { connectKey: "connectZoho", settingsKey: "zohoSettings", label: "Paramètres Zoho" },
  spotify: { connectKey: "connectSpotify", settingsKey: "spotifySettings", label: "Paramètres Spotify" },
};

export default function Integrations({ onNavigate, focusEnabled }) {
  const integrations = useIntegrations();
  const { accounts, remove } = integrations;
  const isMobile = useIsMobile();
  const [busyType, setBusyType] = useState(null);
  const [errors, setErrors] = useState({});

  async function handleConnect(type) {
    const entry = CATALOG.find((c) => c.type === type);
    const connector = entry && _CONNECTORS[entry.provider];
    if (!connector) return;

    const status = integrations[connector.settingsKey];
    if (!status.configured) {
      setErrors((e) => ({ ...e, [type]: `Renseigne d'abord Client ID / Client Secret ci-dessous (${connector.label}).` }));
      return;
    }
    setErrors((e) => ({ ...e, [type]: "" }));
    setBusyType(type);
    try {
      await integrations[connector.connectKey](type);
    } catch (e) {
      setErrors((err) => ({ ...err, [type]: e.message }));
    } finally {
      setBusyType(null);
    }
  }

  return (
    <Frame active="integrations" onNavigate={onNavigate} focusEnabled={focusEnabled}>
      <Topbar count={accounts.length} />
      <div style={{ flex: 1, display: "flex", flexDirection: isMobile ? "column" : "row", minHeight: 0, overflow: "auto" }}>
        <div style={{ flex: 1, padding: 22, overflow: isMobile ? "visible" : "auto", minWidth: 0 }}>
          {accounts.length === 0 ? (
            <div style={{ color: "var(--faint)", fontSize: 13 }}>
              Aucun compte connecté — ajoute-en un {isMobile ? "en dessous" : "à droite"}.
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 14 }}>
              {accounts.map((a) => (
                <AccountCard key={a.id} account={a} onRemove={remove} />
              ))}
            </div>
          )}
        </div>
        <div
          style={{
            width: isMobile ? "100%" : 298,
            flex: "none",
            borderLeft: isMobile ? "none" : "1px solid var(--stroke-soft)",
            borderTop: isMobile ? "1px solid var(--stroke-soft)" : "none",
            background: "var(--bg-2)",
            padding: "22px 20px",
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: ".16em", textTransform: "uppercase", color: "var(--faint)" }}>
            Ajouter un compte
          </div>
          {CATALOG.map((entry) => (
            <CatalogRow
              key={entry.type}
              entry={entry}
              onConnect={handleConnect}
              busy={busyType === entry.type}
              error={errors[entry.type] || ""}
            />
          ))}
          <div style={{ fontSize: 11, color: "var(--faint)" }}>
            Plusieurs comptes peuvent être connectés en parallèle, y compris sur
            différents services d'un même fournisseur — les résultats de chacun
            sont fusionnés automatiquement.
          </div>
          <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
            <GoogleAppSettings status={integrations.googleSettings} onSave={integrations.saveGoogleSettings} onClear={integrations.clearGoogleSettings} />
            <ZohoAppSettings status={integrations.zohoSettings} onSave={integrations.saveZohoSettings} onClear={integrations.clearZohoSettings} />
            <SpotifyAppSettings status={integrations.spotifySettings} onSave={integrations.saveSpotifySettings} onClear={integrations.clearSpotifySettings} />
            <JellyfinConnect onConnect={integrations.connectJellyfin} />
          </div>
        </div>
      </div>
    </Frame>
  );
}

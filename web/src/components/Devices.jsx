import { useEffect, useState } from "react";
import { ViewHeader } from "./AppShell.jsx";
import Focus from "./Focus.jsx";
import EmptyState from "./ui/EmptyState.jsx";
import Icon from "./ui/Icon.jsx";
import Modal from "./ui/Modal.jsx";
import StatusBadge from "./ui/StatusBadge.jsx";
import { useConfirm } from "./ui/Confirm.jsx";
import { useToast } from "./ui/Toast.jsx";
import { authFetch } from "../lib/consoleAuth.js";
import { useDevices } from "../lib/useDevices.js";

const TYPE_LABELS = {
  desktop: "PC fixe",
  laptop: "Portable",
  mobile: "Téléphone",
  tablet: "Tablette",
};

// Les capacités arrivent en identifiants techniques depuis l'agent
// (agents/protocol/messages.py) — traduites ici, sinon une carte affiche
// « screen_capture, input_control » et ne dit rien à personne.
const CAPABILITY_LABELS = {
  screen_capture: "Capture d'écran",
  input_control: "Clavier / souris",
  powershell: "PowerShell",
  audio: "Audio",
  tts: "Synthèse vocale",
  stt: "Transcription",
  notifications: "Notifications",
};

const PAIRING_TTL_MS = 5 * 60 * 1000;

function DeviceCard({ device, onForget, onFocus }) {
  const online = device.status === "online";
  return (
    <div className="card card--interactive">
      <div className="card-head">
        <div className="spacer">
          <h2 className="card-title">{device.name}</h2>
          <span className="card-sub">{TYPE_LABELS[device.device_type] || device.device_type}</span>
        </div>
        <StatusBadge tone={online ? "ok" : "neutral"}>{online ? "en ligne" : "hors ligne"}</StatusBadge>
      </div>

      <div className="row row--wrap" style={{ gap: "var(--sp-2)" }}>
        {device.capabilities.length === 0 ? (
          <span className="hint">Aucune capacité déclarée</span>
        ) : (
          device.capabilities.map((c) => (
            <span key={c} className="chip">
              {CAPABILITY_LABELS[c] || c}
            </span>
          ))
        )}
      </div>

      <div className="card-actions">
        <button type="button" className="btn btn--danger btn--sm" onClick={() => onForget(device)}>
          <Icon name="trash" size={15} />
          Oublier
        </button>
        <button
          type="button"
          className="btn btn--accent btn--sm"
          onClick={() => onFocus(device)}
          disabled={!online}
          title={online ? "Piloter cet appareil" : "Appareil hors ligne"}
        >
          <Icon name="focus" size={15} />
          Piloter
        </button>
      </div>
    </div>
  );
}

/** L'appairage était un panneau permanent occupant un tiers de l'écran
 * pour une action qu'on fait deux fois par an. Il devient un dialogue,
 * ouvert à la demande — avec un compte à rebours, parce qu'un code
 * valable 5 minutes sans indication de temps restant est un piège. */
function PairingDialog({ open, onClose }) {
  const toast = useToast();
  const [code, setCode] = useState(null);
  const [expiresAt, setExpiresAt] = useState(0);
  const [remaining, setRemaining] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!expiresAt) return undefined;
    const tick = () => setRemaining(Math.max(0, expiresAt - Date.now()));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [expiresAt]);

  useEffect(() => {
    if (!open) {
      setCode(null);
      setExpiresAt(0);
      setError("");
    }
  }, [open]);

  async function generate() {
    setBusy(true);
    setError("");
    try {
      const res = await authFetch("/api/pairing/code", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "génération impossible");
      setCode(data.code);
      setExpiresAt(Date.now() + PAIRING_TTL_MS);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      toast.success("Code copié.");
    } catch {
      toast.error("Copie refusée par le navigateur.");
    }
  }

  const expired = code && remaining <= 0;
  const mmss = `${String(Math.floor(remaining / 60000)).padStart(2, "0")}:${String(
    Math.floor((remaining % 60000) / 1000),
  ).padStart(2, "0")}`;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Appairer un appareil"
      description="Un code à usage unique, valable 5 minutes."
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Fermer
          </button>
          <button type="button" className="btn btn--primary" onClick={generate} disabled={busy}>
            {busy ? <span className="spinner" aria-hidden="true" /> : <Icon name="key" size={16} />}
            {code ? "Générer un nouveau code" : "Générer un code"}
          </button>
        </>
      }
    >
      {error && (
        <div className="alert alert--danger" role="alert">
          <Icon name="alert" size={16} />
          {error}
        </div>
      )}

      {code ? (
        <div className="stack">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "var(--sp-3)",
              padding: "var(--sp-5)",
              border: "1px solid var(--line-strong)",
              borderRadius: "var(--r-lg)",
              background: "var(--bg)",
              boxShadow: expired ? "none" : "0 0 40px -20px var(--glow)",
              opacity: expired ? 0.5 : 1,
            }}
          >
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-2xl)",
                letterSpacing: "0.28em",
                color: "var(--cyan)",
              }}
            >
              {code}
            </span>
            <button type="button" className="icon-btn" onClick={copyCode} aria-label="Copier le code">
              <Icon name="copy" size={17} />
            </button>
          </div>

          <div className="row" style={{ justifyContent: "center" }}>
            {expired ? (
              <StatusBadge tone="danger">code expiré</StatusBadge>
            ) : (
              <StatusBadge tone="cyan">valable encore {mmss}</StatusBadge>
            )}
          </div>

          <ol className="stack stack--tight" style={{ margin: 0, paddingLeft: "var(--sp-5)" }}>
            <li className="hint">
              Sur l'appareil à ajouter, lancez <code>python -m agents.desktop.agent_client</code>.
            </li>
            <li className="hint">Saisissez le code ci-dessus quand il vous est demandé.</li>
            <li className="hint">L'appareil apparaît dans la liste, en ligne, dès qu'il s'est connecté.</li>
          </ol>
        </div>
      ) : (
        <p className="hint">
          Générez un code, puis saisissez-le sur l'appareil à ajouter. Chaque code ne sert qu'une fois.
        </p>
      )}
    </Modal>
  );
}

export default function Devices() {
  const { devices, loaded, forget } = useDevices();
  const confirm = useConfirm();
  const toast = useToast();
  const [pairingOpen, setPairingOpen] = useState(false);
  // Piloter un appareil ouvre une vue de détail *ici*, avec un retour à la
  // liste — et non une entrée de plus dans la navigation, qui listait
  // alors un endroit qui n'existait pas cinq secondes plus tôt.
  const [piloted, setPiloted] = useState(null);

  async function handleForget(device) {
    const ok = await confirm({
      title: `Oublier « ${device.name} » ?`,
      message:
        "Jarvis ne pourra plus le piloter, et il faudra le réappairer avec un nouveau code pour le retrouver.",
      confirmLabel: "Oublier",
    });
    if (!ok) return;
    await forget(device.device_id);
    toast.success(`« ${device.name} » a été oublié.`);
  }

  const onlineCount = devices.filter((d) => d.status === "online").length;

  if (piloted) {
    return <Focus deviceId={piloted.device_id} onBack={() => setPiloted(null)} />;
  }

  return (
    <>
      <ViewHeader
        title="Appareils"
        subtitle={
          loaded
            ? `${devices.length} appairé${devices.length > 1 ? "s" : ""} · ${onlineCount} en ligne`
            : "Chargement…"
        }
        actions={
          <button type="button" className="btn btn--primary btn--sm" onClick={() => setPairingOpen(true)}>
            <Icon name="plus" size={16} />
            Appairer
          </button>
        }
      />

      <div className="view-body">
        <div className="view-main">
          {devices.length === 0 ? (
            <EmptyState
              icon="devices"
              title="Aucun appareil appairé"
              text="Un appareil appairé peut être piloté à distance : capture d'écran, verrouillage, ouverture de pages, et exécution de routines."
              action={
                <button type="button" className="btn btn--primary" onClick={() => setPairingOpen(true)}>
                  <Icon name="plus" size={16} />
                  Appairer un appareil
                </button>
              }
            />
          ) : (
            <div className="grid">
              {devices.map((d) => (
                <DeviceCard key={d.device_id} device={d} onForget={handleForget} onFocus={setPiloted} />
              ))}
            </div>
          )}
        </div>
      </div>

      <PairingDialog open={pairingOpen} onClose={() => setPairingOpen(false)} />
    </>
  );
}

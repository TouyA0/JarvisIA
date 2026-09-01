import { useState } from "react";
import { ViewHeader } from "./AppShell.jsx";
import Icon from "./ui/Icon.jsx";
import Modal from "./ui/Modal.jsx";
import StatusBadge from "./ui/StatusBadge.jsx";
import { TextField } from "./ui/Field.jsx";
import { useConfirm } from "./ui/Confirm.jsx";
import { useToast } from "./ui/Toast.jsx";
import { useFocusDevice } from "../lib/useFocusDevice.js";

// Traductions des noms d'outils tels que l'agent les journalise
// (agents/desktop/tools/registry.py) — le journal affichait
// « run_powershell » brut, ce qui ne dit rien de ce qui s'est passé.
const TOOL_LABELS = {
  take_screenshot: "Capture d'écran",
  run_powershell: "Commande système",
  open_url: "Ouverture d'une page",
  type_text: "Saisie de texte",
  press_keys: "Raccourci clavier",
  mouse_click: "Clic souris",
  read_screen: "Lecture de l'écran",
  scroll_page: "Défilement",
  get_browser_url: "Lecture de l'URL",
  read_clipboard: "Lecture du presse-papiers",
  search_file: "Recherche de fichier",
  open_file: "Ouverture d'un fichier",
  list_folder: "Listage d'un dossier",
  read_file_content: "Lecture d'un fichier",
};

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function Focus({ deviceId, onBack }) {
  const { device, activityLog, screenshot, busy, error, capture, lock, dispatch } = useFocusDevice(deviceId);
  const confirm = useConfirm();
  const toast = useToast();
  const [urlOpen, setUrlOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [zoomed, setZoomed] = useState(false);

  const online = device?.status === "online";

  async function handleLock() {
    const ok = await confirm({
      title: "Verrouiller cet appareil ?",
      message: `La session de « ${device?.name || "cet appareil"} » sera verrouillée immédiatement. Tout travail non enregistré reste ouvert, mais il faudra ressaisir le mot de passe.`,
      confirmLabel: "Verrouiller",
    });
    if (!ok) return;
    const result = await lock();
    if (result !== null) toast.success("Appareil verrouillé.");
  }

  async function handleCapture() {
    const shot = await capture();
    if (shot) toast.success("Capture reçue.");
  }

  async function handleOpenUrl(e) {
    e.preventDefault();
    const target = url.trim();
    if (!target) return;
    const result = await dispatch("open_url", { url: target });
    if (result !== null) {
      toast.success("Page ouverte sur l'appareil.");
      setUrl("");
      setUrlOpen(false);
    }
  }

  return (
    <>
      <ViewHeader
        title={device?.name || "Appareil"}
        subtitle={online ? "Pilotage à distance" : "Appareil hors ligne — les actions sont indisponibles"}
        onBack={onBack}
        backLabel="Retour à la liste des appareils"
        actions={
          <StatusBadge tone={online ? "ok" : "danger"}>{online ? "en ligne" : "hors ligne"}</StatusBadge>
        }
      />

      <div className="view-body">
        <div className="view-main">
          <div className="stack">
            <div className="row row--wrap">
              <button type="button" className="btn btn--accent" onClick={handleCapture} disabled={busy || !online}>
                {busy ? <span className="spinner" aria-hidden="true" /> : <Icon name="camera" size={16} />}
                Capturer l'écran
              </button>
              <button type="button" className="btn" onClick={() => setUrlOpen(true)} disabled={busy || !online}>
                <Icon name="link" size={16} />
                Ouvrir une page
              </button>
              <button type="button" className="btn btn--danger" onClick={handleLock} disabled={busy || !online}>
                <Icon name="lock" size={16} />
                Verrouiller
              </button>
            </div>

            {error && (
              <div className="alert alert--danger" role="alert">
                <Icon name="alert" size={16} />
                {error}
              </div>
            )}

            {screenshot ? (
              <figure style={{ margin: 0 }}>
                <button
                  type="button"
                  onClick={() => setZoomed(true)}
                  style={{ display: "block", width: "100%", padding: 0, background: "none", border: "none" }}
                  aria-label="Agrandir la capture"
                >
                  <img
                    src={`data:image/jpeg;base64,${screenshot}`}
                    alt={`Écran de ${device?.name || "l'appareil"}`}
                    style={{
                      width: "100%",
                      borderRadius: "var(--r-lg)",
                      border: "1px solid var(--line-strong)",
                      boxShadow: "var(--shadow-md)",
                    }}
                  />
                </button>
                <figcaption className="hint" style={{ marginTop: "var(--sp-2)" }}>
                  Cliquez sur l'image pour l'agrandir.
                </figcaption>
              </figure>
            ) : (
              <div
                className="card"
                style={{ alignItems: "center", justifyContent: "center", minHeight: 260, textAlign: "center" }}
              >
                <span className="empty-icon" aria-hidden="true">
                  <Icon name="eye" size={24} />
                </span>
                <p className="hint" style={{ maxWidth: 340 }}>
                  Aucune capture pour l'instant. « Capturer l'écran » demande une image à l'appareil et
                  l'affiche ici.
                </p>
              </div>
            )}
          </div>
        </div>

        <aside className="rail" aria-label="Détails de l'appareil">
          <section className="stack stack--tight">
            <h2 className="section-label">Appareil</h2>
            <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "auto 1fr", gap: "var(--sp-2) var(--sp-3)", fontSize: "var(--text-sm)" }}>
              <dt className="hint">Type</dt>
              <dd style={{ margin: 0 }}>{device?.device_type || "—"}</dd>
              <dt className="hint">Capacités</dt>
              <dd style={{ margin: 0 }}>{device?.capabilities?.join(", ") || "—"}</dd>
              <dt className="hint">Appairé le</dt>
              <dd style={{ margin: 0 }}>
                {device ? new Date(device.paired_at * 1000).toLocaleDateString("fr-FR") : "—"}
              </dd>
            </dl>
          </section>

          <section className="stack stack--tight">
            <h2 className="section-label">Journal d'activité</h2>
            {activityLog.length === 0 ? (
              <p className="hint">Rien encore. Chaque action envoyée à cet appareil s'inscrit ici.</p>
            ) : (
              <ul className="stack stack--tight" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {activityLog.map((entry, i) => (
                  <li key={i} className="row" style={{ alignItems: "flex-start", gap: "var(--sp-2)" }}>
                    <span className={`dot ${entry.ok ? "dot--ok" : "dot--danger"}`} style={{ marginTop: 6 }} aria-hidden="true" />
                    <span style={{ fontSize: "var(--text-sm)" }}>
                      {TOOL_LABELS[entry.tool] || entry.tool}
                      {!entry.ok && (
                        <span style={{ color: "var(--danger-text)" }}> — {entry.error || "échec"}</span>
                      )}
                      <br />
                      <span className="hint" style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}>
                        {formatTime(entry.ts)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>

      <Modal
        open={urlOpen}
        onClose={() => setUrlOpen(false)}
        title="Ouvrir une page sur cet appareil"
        description="La page s'ouvre dans le navigateur par défaut de l'appareil distant."
        footer={
          <>
            <button type="button" className="btn btn--ghost" onClick={() => setUrlOpen(false)}>
              Annuler
            </button>
            <button type="button" className="btn btn--primary" onClick={handleOpenUrl} disabled={busy || !url.trim()}>
              Ouvrir
            </button>
          </>
        }
      >
        <form onSubmit={handleOpenUrl}>
          <TextField
            label="Adresse"
            placeholder="https://…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            hint="Une adresse complète, protocole compris."
          />
        </form>
      </Modal>

      <Modal open={zoomed} onClose={() => setZoomed(false)} title="Capture d'écran" wide>
        {screenshot && (
          <img
            src={`data:image/jpeg;base64,${screenshot}`}
            alt={`Écran de ${device?.name || "l'appareil"}`}
            style={{ width: "100%", borderRadius: "var(--r-md)" }}
          />
        )}
      </Modal>
    </>
  );
}

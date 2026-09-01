import { useState } from "react";
import Icon from "../ui/Icon.jsx";
import Modal from "../ui/Modal.jsx";
import { useToast } from "../ui/Toast.jsx";
import { authFetch } from "../../lib/consoleAuth.js";
import { CARD_META, Fallback, RENDERERS } from "./renderers.jsx";

/**
 * Le cadre commun de toutes les cartes : même en-tête (icône, titre,
 * source, heure), même bouton « écarter ». Seul le corps change selon le
 * type — c'est ce qui permet d'ajouter une intégration sans redessiner
 * une UI complète, comme prévu par la roadmap (§2.3).
 *
 * `card.actions` (voir brain/cards.py) rend une rangée de boutons communs à
 * TOUS les types de carte — pas seulement Spotify, n'importe quel outil
 * futur qui pose des actions dans sa carte en profite gratuitement. Chaque
 * clic appelle /api/tools/execute (server.py), qui réexécute exactement le
 * même outil que Claude aurait appelé, mêmes garde-fous compris.
 */
function ago(at) {
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - at));
  if (seconds < 60) return "à l'instant";
  if (seconds < 3600) return `il y a ${Math.floor(seconds / 60)} min`;
  return new Date(at * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

function base64ToBlob(base64, mediaType) {
  const bytes = atob(base64);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return new Blob([arr], { type: mediaType });
}

function CardActions({ actions, toast }) {
  const [busyIndex, setBusyIndex] = useState(-1);

  async function run(action, i) {
    setBusyIndex(i);
    try {
      const res = await authFetch("/api/tools/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool: action.tool, args: action.args || {} }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "action refusée");
      // La carte à jour arrive via /ws/cards (le tool ré-émet la sienne) —
      // rien à faire ici sinon signaler un échec silencieux (ex: Spotify
      // "pas d'appareil actif" ne lève pas d'erreur HTTP, juste un texte).
      if (data.text && /refus|erreur|Monsieur —/.test(data.text)) toast.info(data.text);
    } catch (e) {
      toast.error(e.message || "Action impossible.");
    } finally {
      setBusyIndex(-1);
    }
  }

  return (
    <div className="card-actions">
      {actions.map((a, i) => (
        <button
          key={i}
          type="button"
          className="btn btn--ghost btn--sm"
          disabled={busyIndex >= 0}
          onClick={() => run(a, i)}
        >
          <Icon name={a.icon || "play"} size={15} />
          {a.label}
        </button>
      ))}
    </div>
  );
}

function ScreenshotActions({ data, toast }) {
  const mediaType = data.media_type || "image/jpeg";

  async function copy() {
    try {
      const blob = base64ToBlob(data.image_b64, mediaType);
      await navigator.clipboard.write([new ClipboardItem({ [mediaType]: blob })]);
      toast.success("Capture copiée.");
    } catch {
      toast.error("Copie impossible (navigateur non compatible ou permission refusée).");
    }
  }

  function save() {
    const blob = base64ToBlob(data.image_b64, mediaType);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `jarvis-capture-${Date.now()}.${mediaType.includes("png") ? "png" : "jpg"}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="card-actions">
      <button type="button" className="btn btn--ghost btn--sm" onClick={copy}>
        <Icon name="copy" size={15} />
        Copier
      </button>
      <button type="button" className="btn btn--ghost btn--sm" onClick={save}>
        <Icon name="download" size={15} />
        Enregistrer
      </button>
    </div>
  );
}

/** `readOnly` : posée pour une carte d'historique (System.jsx) — pas de
 * bouton écarter (rien à écarter, ce n'est déjà plus sur le pupitre) et
 * surtout pas de boutons d'action : une carte "musique" vieille de trois
 * jours ne doit jamais pouvoir agir sur la lecture Spotify ACTUELLE. */
export default function CardView({ card, onDismiss, readOnly = false }) {
  const [zoomed, setZoomed] = useState(false);
  const toast = useToast();
  const meta = CARD_META[card.type] || { icon: "info", source: card.type };
  const Body = RENDERERS[card.type] || Fallback;

  return (
    <article className={`hud-card hud-card--${card.type}`}>
      <header className="hud-card-head">
        <span className="hud-card-icon" aria-hidden="true">
          <Icon name={meta.icon} size={15} />
        </span>
        <span className="hud-card-heading">
          <span className="hud-card-title">{card.title}</span>
          <span className="hud-card-sub">
            {card.subtitle || meta.source} · {ago(card.at)}
          </span>
        </span>
        {!readOnly && (
          <button
            type="button"
            className="icon-btn icon-btn--sm"
            onClick={() => onDismiss(card.id)}
            aria-label={`Écarter la carte ${card.title}`}
          >
            <Icon name="x" size={14} />
          </button>
        )}
      </header>

      <div className="hud-card-body">
        <Body data={card.data} onZoom={() => setZoomed(true)} />
      </div>

      {!readOnly && card.type === "screenshot" && <ScreenshotActions data={card.data} toast={toast} />}
      {!readOnly && card.actions && card.actions.length > 0 && <CardActions actions={card.actions} toast={toast} />}

      {card.type === "screenshot" && (
        <Modal open={zoomed} onClose={() => setZoomed(false)} title={card.title} wide>
          <img
            src={`data:${card.data.media_type || "image/jpeg"};base64,${card.data.image_b64}`}
            alt="Capture d'écran"
            style={{ width: "100%", borderRadius: "var(--r-md)" }}
          />
        </Modal>
      )}
    </article>
  );
}

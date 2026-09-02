import { useMemo, useState } from "react";
import { ViewHeader } from "./AppShell.jsx";
import Icon from "./ui/Icon.jsx";
import { useToast } from "./ui/Toast.jsx";
import { authFetch } from "../lib/consoleAuth.js";

/**
 * Écran de réception du partage Android (C3) — cible de `share_target` dans
 * manifest.webmanifest. « Partager » un lien YouTube/Netflix/Prime depuis
 * n'importe quelle app vers la PWA installée ouvre `/?share_url=...` (ou
 * `share_text=...` selon ce que l'appli source remplit) ; App.jsx détecte
 * ces paramètres et route ici plutôt que vers le Pupitre.
 *
 * Contournement à l'agent mobile (Phase 7, jamais commencée) : pas de
 * notification ni de contrôle depuis le téléphone, juste ce point d'entrée
 * à sens unique, mais qui couvre le cas d'usage réel (« j'ai un lien sur le
 * téléphone, je veux le voir sur la télé ») pour une poignée de lignes.
 */

const URL_RE = /https?:\/\/\S+/;

/** `share_url` est le champ normal, mais certaines apps (ex. YouTube côté
 * Android) ne remplissent que `share_text` avec le lien noyé dans une
 * phrase ("Regarde cette vidéo : https://youtu.be/xxx") — on extrait la
 * première URL trouvée plutôt que d'afficher un écran vide. */
function extractSharedUrl(params) {
  const direct = params.get("share_url");
  if (direct) return direct.trim();
  const text = params.get("share_text") || params.get("share_title") || "";
  const m = text.match(URL_RE);
  return m ? m[0] : null;
}

export default function Share({ onNavigate }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const url = useMemo(() => extractSharedUrl(params), [params]);
  const rawText = params.get("share_text") || params.get("share_title") || "";

  async function sendToTv() {
    if (!url || busy) return;
    setBusy(true);
    try {
      const res = await authFetch("/api/tools/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool: "send_to_tv", args: { url } }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "envoi refusé");
      toast.success(data.text || "Envoyé sur la télé.");
      setSent(true);
    } catch (err) {
      toast.error(err.message || "Impossible d'envoyer sur la télé.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <ViewHeader
        title="Partagé à Jarvis"
        subtitle="Lien reçu depuis une autre application"
        onBack={() => onNavigate("hud")}
      />
      <div className="view-body">
        <div className="view-main">
          <div className="stack" style={{ gap: "var(--sp-6)", maxWidth: "var(--content-max)" }}>
            {!url ? (
              <p className="hint">
                Aucun lien reconnaissable dans ce qui a été partagé
                {rawText ? ` (« ${rawText} »)` : ""}.
              </p>
            ) : (
              <>
                <div className="card">
                  <div className="card-head">
                    <span className="card-title" style={{ wordBreak: "break-all" }}>
                      {url}
                    </span>
                  </div>
                </div>

                <div className="row" style={{ gap: "var(--sp-3)", flexWrap: "wrap" }}>
                  <button type="button" className="btn btn--primary" onClick={sendToTv} disabled={busy || sent}>
                    <Icon name="tv" size={16} />
                    {sent ? "Envoyé sur la télé" : busy ? "Envoi…" : "Envoyer sur la télé"}
                  </button>
                  <a className="btn btn--ghost" href={url} target="_blank" rel="noreferrer">
                    <Icon name="link" size={16} />
                    Ouvrir le lien
                  </a>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => navigator.clipboard?.writeText(url).then(() => toast.info("Lien copié."))}
                  >
                    <Icon name="copy" size={16} />
                    Copier
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

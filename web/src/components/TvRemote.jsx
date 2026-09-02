import { useEffect, useState } from "react";
import { ViewHeader } from "./AppShell.jsx";
import Icon from "./ui/Icon.jsx";
import { useToast } from "./ui/Toast.jsx";
import { authFetch } from "../lib/consoleAuth.js";
import { useTvLiveFrame } from "../lib/useTvLiveFrame.js";

/**
 * Télécommande visuelle de la télé du salon (C9) — appuyer sur un bouton
 * bat la voix pour naviguer un menu, et le téléphone est déjà l'appareil
 * connecté à la Console en permanence : c'est l'usage quotidien que la
 * carte "tv" (T5/C6, éphémère, posée après une commande vocale) ne couvre
 * pas — un écran dédié, toujours au même endroit (Intégrations → Télé →
 * Télécommande), avec le direct démarré automatiquement pour voir où on
 * navigue.
 *
 * Les boutons appellent /api/tools/execute exactement comme card.actions
 * (voir CardActions dans CardView.jsx) — même outils tv_key/tv_volume que
 * Claude, mêmes garde-fous (STOP demande confirmation côté serveur, voir
 * android_tv.py::send_key). Le direct réutilise useTvLiveFrame(), partagé
 * avec la carte "tv" (renderers.jsx).
 */

async function sendTool(tool, args = {}) {
  const res = await authFetch("/api/tools/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool, args }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "action refusée");
  return data;
}

function RemoteButton({ icon, label, onPress, primary, danger, style }) {
  return (
    <button
      type="button"
      className={`btn ${primary ? "btn--accent" : danger ? "btn--danger" : "btn--ghost"}`.trim()}
      onClick={onPress}
      aria-label={label}
      title={label}
      style={{ width: 56, height: 56, padding: 0, borderRadius: "var(--r-full, 999px)", ...style }}
    >
      <Icon name={icon} size={20} />
    </button>
  );
}

export default function TvRemote({ onBack }) {
  const toast = useToast();
  const { live, frame, error: liveError, start: startLive, stop: stopLive } = useTvLiveFrame();
  const [busy, setBusy] = useState(false);

  // Direct démarré à l'ouverture : le point même de cet écran est de
  // naviguer un menu à vue, pas de devoir cliquer un second bouton avant.
  useEffect(() => {
    startLive();
    return stopLive;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function press(tool, args, label) {
    setBusy(true);
    try {
      const data = await sendTool(tool, args);
      if (data.text && /refus|erreur|Monsieur —/.test(data.text)) toast.info(data.text);
    } catch (e) {
      toast.error(e.message || `${label} impossible.`);
    } finally {
      setBusy(false);
    }
  }

  const key = (command, label) => () => press("tv_key", { command }, label);
  const volume = (direction, label) => () => press("tv_volume", { direction }, label);

  return (
    <>
      <ViewHeader
        title="Télécommande"
        subtitle="Télé du salon"
        onBack={onBack}
        backLabel="Retour aux intégrations"
      />

      <div className="view-body">
        <div className="view-main">
          <div className="stack" style={{ alignItems: "center", maxWidth: 420, margin: "0 auto" }}>
            <figure style={{ margin: 0, width: "100%", position: "relative" }}>
              {frame?.image_b64 ? (
                <img
                  src={`data:${frame.media_type || "image/png"};base64,${frame.image_b64}`}
                  alt="Écran de la télé"
                  style={{ display: "block", width: "100%", borderRadius: "var(--r-lg)", border: "1px solid var(--line-strong)" }}
                />
              ) : (
                <div
                  className="card"
                  style={{ alignItems: "center", justifyContent: "center", minHeight: 180, textAlign: "center" }}
                >
                  <span className="empty-icon" aria-hidden="true">
                    <Icon name="tv" size={22} />
                  </span>
                  <p className="hint">Connexion au direct…</p>
                </div>
              )}
              {live && frame?.image_b64 && (
                <span
                  className="row"
                  style={{
                    position: "absolute", top: "var(--sp-2)", left: "var(--sp-2)",
                    gap: "var(--sp-1)", alignItems: "center", padding: "3px 8px",
                    borderRadius: "var(--r-full, 999px)", background: "rgba(0,0,0,.55)",
                    color: "#fff", fontSize: "var(--text-xs)", fontFamily: "var(--font-mono)",
                  }}
                >
                  <span className="dot dot--danger dot--pulse" aria-hidden="true" />
                  EN DIRECT
                </span>
              )}
            </figure>
            {liveError && (
              <div className="row" style={{ alignItems: "center", gap: "var(--sp-2)" }}>
                <p className="hint" style={{ color: "var(--danger-text)", margin: 0 }}>
                  Direct interrompu : {liveError}
                </p>
                <button type="button" className="btn btn--ghost btn--sm" onClick={startLive}>
                  Relancer
                </button>
              </div>
            )}

            {/* Croix directionnelle */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "56px 56px 56px",
                gridTemplateRows: "56px 56px 56px",
                gap: "var(--sp-2)",
                marginTop: "var(--sp-2)",
              }}
            >
              <span />
              <RemoteButton icon="chevron-up" label="Haut" onPress={key("DPAD_UP", "Haut")} />
              <span />
              <RemoteButton icon="chevron-left" label="Gauche" onPress={key("DPAD_LEFT", "Gauche")} />
              <RemoteButton icon="check" label="OK" primary onPress={key("DPAD_CENTER", "OK")} />
              <RemoteButton icon="chevron-right" label="Droite" onPress={key("DPAD_RIGHT", "Droite")} />
              <span />
              <RemoteButton icon="chevron-down" label="Bas" onPress={key("DPAD_DOWN", "Bas")} />
              <span />
            </div>

            <div className="row row--wrap" style={{ justifyContent: "center", gap: "var(--sp-3)" }}>
              <RemoteButton icon="back" label="Retour" onPress={key("BACK", "Retour")} />
              <RemoteButton icon="home" label="Accueil" onPress={key("HOME", "Accueil")} />
            </div>

            <div className="row row--wrap" style={{ justifyContent: "center", gap: "var(--sp-3)" }}>
              <RemoteButton icon="skip-prev" label="Précédent" onPress={key("PREVIOUS", "Précédent")} />
              <RemoteButton icon="play" label="Lecture / pause" onPress={key("PLAY_PAUSE", "Lecture")} />
              <RemoteButton icon="skip-next" label="Suivant" onPress={key("NEXT", "Suivant")} />
              <RemoteButton icon="stop" label="Stop" danger onPress={key("STOP", "Stop")} />
            </div>

            <div className="row row--wrap" style={{ justifyContent: "center", gap: "var(--sp-3)" }}>
              <RemoteButton icon="chevron-down" label="Volume -" onPress={volume("down", "Volume -")} />
              <RemoteButton icon="x" label="Muet" onPress={volume("mute", "Muet")} />
              <RemoteButton icon="chevron-up" label="Volume +" onPress={volume("up", "Volume +")} />
            </div>

            {busy && <span className="hint">Envoi…</span>}
          </div>
        </div>
      </div>
    </>
  );
}

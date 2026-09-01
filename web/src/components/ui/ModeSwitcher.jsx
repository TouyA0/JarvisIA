import { useEffect, useRef, useState } from "react";
import Icon from "./Icon.jsx";
import { useToast } from "./Toast.jsx";
import { useModes } from "../../lib/useSystem.js";

/**
 * Changement de mode contextuel en deux clics, depuis n'importe où.
 *
 * Le mode conditionne le ton et la concision de toutes les réponses : il
 * change plusieurs fois par jour. L'enterrer au milieu de la vue Système
 * revenait à ne jamais s'en servir autrement qu'à la voix — d'où ce
 * raccourci, en pied de barre latérale et sur le pupitre.
 *
 * `variant` : "nav" (pied de barre latérale) ou "chip" (bandeau du pupitre).
 */
export default function ModeSwitcher({ variant = "nav" }) {
  const { modes, current, activate } = useModes();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function onPointerDown(e) {
      if (!rootRef.current?.contains(e.target)) setOpen(false);
    }
    function onKeyDown(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const active = modes.find((m) => m.id === current?.mode_id);
  const label = (active?.name || "Mode").replace(/^Mode\s+/i, "");

  async function choose(mode) {
    setBusy(mode.id);
    try {
      await activate(mode.id);
      toast.success(`${mode.name} activé.`);
      setOpen(false);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="mode-switch" ref={rootRef}>
      <button
        type="button"
        className={variant === "chip" ? "hud-chip hud-chip--button" : "nav-item mode-switch-trigger"}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <Icon name="system" size={variant === "nav" ? 18 : 13} />
        {variant === "nav" ? (
          <>
            <span className="nav-item-label">Mode {label}</span>
            <Icon name="chevron" size={14} className="rot-up" />
          </>
        ) : (
          label
        )}
      </button>

      {open && (
        <ul className={`mode-menu mode-menu--${variant}`} role="menu">
          {modes.map((mode) => {
            const isActive = mode.id === current?.mode_id;
            return (
              <li key={mode.id} role="none">
                <button
                  type="button"
                  role="menuitemradio"
                  aria-checked={isActive}
                  className="mode-menu-item"
                  disabled={busy !== ""}
                  onClick={() => (isActive ? setOpen(false) : choose(mode))}
                >
                  <span className={`dot ${isActive ? "dot--cyan" : ""}`} aria-hidden="true" />
                  <span className="mode-menu-text">
                    <span>{mode.name.replace(/^Mode\s+/i, "")}</span>
                    <span className="mode-menu-desc">{mode.description}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

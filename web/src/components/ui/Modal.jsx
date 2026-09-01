import { useEffect, useId, useRef } from "react";
import Icon from "./Icon.jsx";

/**
 * Dialogue modal accessible : Échap ferme, le clic sur le voile ferme, le
 * focus part dans le dialogue à l'ouverture et revient à l'élément
 * déclencheur à la fermeture, et Tab reste piégé à l'intérieur.
 *
 * Remplace les deux façons de demander quelque chose à Monsieur dans
 * l'ancienne Console : `window.confirm()` (Focus.jsx, pour verrouiller
 * une machine à distance) et les gros panneaux latéraux permanents
 * (appairage, builder de routine) qui occupaient un tiers de l'écran en
 * permanence pour une action ponctuelle.
 */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function Modal({ open, onClose, title, description, children, footer, wide = false }) {
  const cardRef = useRef(null);
  const previousFocusRef = useRef(null);
  const titleId = useId();
  const descId = useId();

  useEffect(() => {
    if (!open) return undefined;
    previousFocusRef.current = document.activeElement;

    // Le premier champ plutôt que le premier bouton quand il y en a un :
    // ouvrir « Nouvelle routine » et pouvoir taper le nom tout de suite.
    const node = cardRef.current;
    const first = node?.querySelector("input, textarea, select") || node?.querySelector(FOCUSABLE);
    first?.focus();

    function onKeyDown(e) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !node) return;
      const items = [...node.querySelectorAll(FOCUSABLE)].filter((el) => el.offsetParent !== null);
      if (items.length === 0) return;
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      if (e.shiftKey && document.activeElement === firstItem) {
        e.preventDefault();
        lastItem.focus();
      } else if (!e.shiftKey && document.activeElement === lastItem) {
        e.preventDefault();
        firstItem.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown, true);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      document.body.style.overflow = previousOverflow;
      previousFocusRef.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={cardRef}
        className={`modal${wide ? " modal--wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
      >
        <div className="modal-header">
          <div className="view-heading">
            <h2 className="modal-title" id={titleId}>
              {title}
            </h2>
            {description && (
              <p className="modal-desc" id={descId}>
                {description}
              </p>
            )}
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Fermer">
            <Icon name="x" />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}

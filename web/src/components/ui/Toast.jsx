import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import Icon from "./Icon.jsx";

/**
 * File de notifications éphémères. Avant, chaque écran affichait ses
 * erreurs à sa façon (une ligne rouge sous un bouton, un texte perdu dans
 * un rail, ou rien du tout pour les actions qui réussissent) — donc une
 * suppression d'appareil ou une routine lancée ne donnaient aucun retour.
 *
 * `aria-live="polite"` : annoncé sans interrompre ce que Monsieur est en
 * train de lire, contrairement à `assertive` qui coupe la parole.
 */
const ToastContext = createContext(null);

const DURATION_MS = 5000;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (message, tone = "info") => {
      const id = ++nextId.current;
      setToasts((list) => [...list, { id, message, tone }]);
      setTimeout(() => dismiss(id), DURATION_MS);
      return id;
    },
    [dismiss],
  );

  const api = useMemo(
    () => ({
      info: (m) => push(m, "info"),
      success: (m) => push(m, "success"),
      error: (m) => push(m, "error"),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.tone}`}>
            <Icon
              name={t.tone === "error" ? "alert" : t.tone === "success" ? "check" : "info"}
              size={16}
            />
            <span className="spacer">{t.message}</span>
            <button type="button" className="icon-btn icon-btn--sm" onClick={() => dismiss(t.id)} aria-label="Ignorer">
              <Icon name="x" size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast doit être utilisé dans un <ToastProvider>");
  return ctx;
}

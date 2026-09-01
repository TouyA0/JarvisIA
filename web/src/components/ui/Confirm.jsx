import { createContext, useCallback, useContext, useRef, useState } from "react";
import Modal from "./Modal.jsx";

/**
 * Confirmation avant une action destructrice ou irréversible, sous forme
 * de promesse : `await confirm({ ... })`. Remplace `window.confirm()`,
 * qui verrouillait un PC distant derrière une boîte système sans titre,
 * sans contexte, et impossible à styler ou à traduire.
 *
 * Les actions concernées ici : oublier un appareil (il faudra le
 * réappairer), verrouiller une machine distante, supprimer une routine,
 * déconnecter un compte tiers, oublier un fait mémorisé.
 */
const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
  const [request, setRequest] = useState(null);
  const resolveRef = useRef(null);

  const confirm = useCallback((options) => {
    setRequest({
      title: options.title,
      message: options.message,
      confirmLabel: options.confirmLabel || "Confirmer",
      cancelLabel: options.cancelLabel || "Annuler",
      danger: options.danger !== false,
    });
    return new Promise((resolve) => {
      resolveRef.current = resolve;
    });
  }, []);

  const settle = useCallback((value) => {
    setRequest(null);
    resolveRef.current?.(value);
    resolveRef.current = null;
  }, []);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Modal
        open={!!request}
        onClose={() => settle(false)}
        title={request?.title || ""}
        footer={
          request && (
            <>
              <button type="button" className="btn btn--ghost" onClick={() => settle(false)}>
                {request.cancelLabel}
              </button>
              <button
                type="button"
                className={`btn ${request.danger ? "btn--danger" : "btn--primary"}`}
                onClick={() => settle(true)}
              >
                {request.confirmLabel}
              </button>
            </>
          )
        }
      >
        <p className="hint" style={{ fontSize: "var(--text-base)" }}>
          {request?.message}
        </p>
      </Modal>
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm doit être utilisé dans un <ConfirmProvider>");
  return ctx;
}

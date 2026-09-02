import { useState } from "react";
import Icon from "../ui/Icon.jsx";
import Modal from "../ui/Modal.jsx";
import { SelectField, TextField } from "../ui/Field.jsx";
import { useToast } from "../ui/Toast.jsx";

/** Formulaire générique : une ou plusieurs sections, chacune avec ses
 * champs, son bouton d'envoi et son éventuel bouton d'effacement. Couvre
 * les trois familles (identifiants d'application, connexion directe, clé
 * API), qui étaient auparavant trois composants quasi identiques recopiés
 * à sept exemplaires. */
export default function FormModal({ open, onClose, title, description, doc, sections, api, status, onDone }) {
  const toast = useToast();
  const [values, setValues] = useState({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  function valueOf(section, field) {
    return values[`${section.id || "main"}.${field.name}`] ?? field.default ?? "";
  }

  function setValue(section, field, v) {
    setValues((prev) => ({ ...prev, [`${section.id || "main"}.${field.name}`]: v }));
  }

  async function submit(section) {
    const payload = Object.fromEntries(section.fields.map((f) => [f.name, valueOf(section, f).trim()]));
    const missing = section.fields.find((f) => f.required && !payload[f.name]);
    if (missing) {
      setError(`« ${missing.label} » est obligatoire.`);
      return;
    }
    setError("");
    setBusy(section.id || "main");
    try {
      await section.submit(api, payload);
      toast.success(section.successMessage || "Enregistré.");
      setValues((prev) => {
        const next = { ...prev };
        section.fields.forEach((f) => delete next[`${section.id || "main"}.${f.name}`]);
        return next;
      });
      onDone?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  async function clear(section) {
    setBusy(section.id || "main");
    try {
      await section.clear(api);
      toast.info("Réglage effacé.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      footer={
        <button type="button" className="btn btn--ghost" onClick={onClose}>
          Fermer
        </button>
      }
    >
      {error && (
        <div className="alert alert--danger" role="alert">
          <Icon name="alert" size={16} />
          {error}
        </div>
      )}

      {sections.map((section) => {
        const blocked = section.requiresConfigured && !status?.configured;
        return (
          <section key={section.id || "main"} className="stack">
            {sections.length > 1 && <h3 className="section-label">{section.title}</h3>}

            {blocked && (
              <div className="alert alert--warn">
                <Icon name="info" size={16} />
                Enregistrez d'abord la clé API ci-dessus.
              </div>
            )}

            {section.fields.map((field) =>
              field.type === "select" ? (
                <SelectField
                  key={field.name}
                  label={field.label}
                  hint={field.hint}
                  value={valueOf(section, field)}
                  onChange={(e) => setValue(section, field, e.target.value)}
                >
                  {field.options.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </SelectField>
              ) : (
                <TextField
                  key={field.name}
                  label={field.label}
                  type={field.type || "text"}
                  placeholder={field.placeholder}
                  hint={field.hint}
                  required={field.required}
                  autoComplete="off"
                  value={valueOf(section, field)}
                  onChange={(e) => setValue(section, field, e.target.value)}
                  disabled={blocked}
                />
              ),
            )}

            {section.hint && <p className="hint">{section.hint}</p>}

            <div className="row" style={{ justifyContent: "flex-end" }}>
              {section.clear && section.canClear?.(status || {}) && (
                <button
                  type="button"
                  className="btn btn--danger btn--sm"
                  onClick={() => clear(section)}
                  disabled={busy !== ""}
                >
                  {section.clearLabel || "Effacer"}
                </button>
              )}
              <button
                type="button"
                className="btn btn--primary btn--sm"
                onClick={() => submit(section)}
                disabled={busy !== "" || blocked}
              >
                {busy === (section.id || "main") && <span className="spinner" aria-hidden="true" />}
                {section.submitLabel || "Enregistrer"}
              </button>
            </div>
          </section>
        );
      })}

      {doc && (
        <div className="alert">
          <Icon name="info" size={16} />
          {doc}
        </div>
      )}
    </Modal>
  );
}

import { useId } from "react";

/**
 * Champ de formulaire avec une vraie étiquette liée (`for`/`id`), une
 * aide et une erreur rattachées via `aria-describedby`.
 *
 * L'ancienne Console n'utilisait que des `placeholder` en guise
 * d'étiquettes : ils disparaissent dès qu'on tape (impossible de
 * vérifier ce qu'on remplit), ne sont pas annoncés de façon fiable par
 * les lecteurs d'écran, et sur les formulaires longs (Client ID / Client
 * Secret / région) ça devient franchement risqué.
 */
export function Field({ label, hint, error, children, required = false }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div className="field">
      <label className="label" htmlFor={id}>
        {label}
        {required && <span aria-hidden="true"> *</span>}
      </label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined, required })}
      {hint && (
        <span className="hint" id={hintId}>
          {hint}
        </span>
      )}
      {error && (
        <span className="field-error" id={errorId} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

/** Raccourci pour le cas courant : une étiquette + un `<input>`. */
export function TextField({ label, hint, error, required, ...inputProps }) {
  return (
    <Field label={label} hint={hint} error={error} required={required}>
      {(a11y) => <input className="input" {...a11y} {...inputProps} />}
    </Field>
  );
}

/** Idem pour un `<select>`. */
export function SelectField({ label, hint, error, required, children, ...selectProps }) {
  return (
    <Field label={label} hint={hint} error={error} required={required}>
      {(a11y) => (
        <select className="select" {...a11y} {...selectProps}>
          {children}
        </select>
      )}
    </Field>
  );
}

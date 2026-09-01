import { useState } from "react";
import Icon from "./ui/Icon.jsx";
import Reactor from "./ui/Reactor.jsx";

/** Recouvre tout l'écran tant que le brain répond 401 — voir
 * useConsoleAuth.js. Un seul champ, pas de compte : le mot de passe
 * lui-même sert de token (CONSOLE_PASSWORD côté brain). */
export default function AuthGate({ onSubmit }) {
  const [value, setValue] = useState("");

  function submit(e) {
    e.preventDefault();
    if (value.trim()) onSubmit(value);
  }

  return (
    <div
      style={{
        minHeight: "100dvh",
        display: "grid",
        placeItems: "center",
        padding: "var(--sp-4)",
        background:
          "radial-gradient(700px 500px at 50% 30%, var(--cyan-dim), transparent 70%), var(--bg)",
      }}
    >
      <main
        className="card"
        style={{
          width: "min(380px, 100%)",
          gap: "var(--sp-4)",
          padding: "var(--sp-6)",
          boxShadow: "var(--shadow-lg)",
        }}
      >
        <div className="row">
          <Reactor size={40} />
          <span className="view-heading">
            <h1 className="nav-brand-title" style={{ fontSize: "var(--text-lg)" }}>
              J.A.R.V.I.S.
            </h1>
            <span className="hint">Console</span>
          </span>
        </div>

        <p className="hint">
          Authentification requise, Monsieur. Le mot de passe est celui défini côté serveur
          (<code>CONSOLE_PASSWORD</code>).
        </p>

        <form className="stack" onSubmit={submit}>
          <div className="field">
            <label className="label" htmlFor="console-password">
              Mot de passe
            </label>
            <input
              id="console-password"
              className="input"
              type="password"
              autoFocus
              autoComplete="current-password"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </div>
          <button type="submit" className="btn btn--primary btn--block" disabled={!value.trim()}>
            <Icon name="power" size={16} />
            Entrer
          </button>
        </form>
      </main>
    </div>
  );
}

import { useState } from "react";

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
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        background: "var(--bg)",
      }}
    >
      <form
        onSubmit={submit}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 14,
          width: "min(320px, 84vw)",
          padding: 28,
          border: "1px solid var(--stroke-soft)",
          borderRadius: 16,
          background: "var(--bg-2)",
        }}
      >
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16, color: "var(--cyan)" }}>
          J.A.R.V.I.S.
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--faint)" }}>
          Authentification requise, Monsieur.
        </div>
        <input
          type="password"
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Mot de passe"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 13,
            padding: "10px 12px",
            borderRadius: 8,
            border: "1px solid var(--stroke-soft)",
            background: "var(--bg)",
            color: "var(--text)",
            outline: "none",
          }}
        />
        <button
          type="submit"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            padding: "10px 12px",
            borderRadius: 8,
            border: "1px solid var(--cyan)",
            background: "transparent",
            color: "var(--cyan)",
            cursor: "pointer",
          }}
        >
          Entrer
        </button>
      </form>
    </div>
  );
}

import { useState } from "react";
import { useChat } from "../lib/useChat.js";

const dot = (color, size = 7) => ({
  width: size,
  height: size,
  borderRadius: "50%",
  background: color,
  boxShadow: `0 0 8px ${color}`,
  flex: "none",
});

function Reactor({ size = 38 }) {
  return (
    <div
      style={{
        position: "relative",
        width: size,
        height: size,
        borderRadius: "50%",
        border: "1px solid var(--stroke)",
        display: "grid",
        placeItems: "center",
        boxShadow: "0 0 18px -6px var(--glow)",
        flex: "none",
      }}
    >
      <div style={dot("var(--cyan)", size * 0.24)} />
      <div
        style={{
          position: "absolute",
          inset: -1,
          borderRadius: "50%",
          borderTop: "1.5px solid var(--cyan)",
          animation: "spin 5s linear infinite",
        }}
      />
    </div>
  );
}

function Dock() {
  const items = ["console", "devices", "focus", "routines"];
  const [active] = useState("console");
  return (
    <div
      style={{
        width: 70,
        flex: "none",
        borderRight: "1px solid var(--stroke-soft)",
        background: "var(--bg-2)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "18px 0",
        gap: 22,
      }}
    >
      <Reactor />
      <div style={{ display: "flex", flexDirection: "column", gap: 14, alignItems: "center" }}>
        {items.map((id) => (
          <div
            key={id}
            title={id}
            style={{
              width: 42,
              height: 42,
              borderRadius: 12,
              display: "grid",
              placeItems: "center",
              background: id === active ? "var(--cyan-dim)" : "transparent",
              border: id === active ? "1px solid var(--stroke)" : "1px solid transparent",
              boxShadow: id === active ? "0 0 16px -6px var(--glow)" : "none",
            }}
          >
            <div
              style={{
                width: 12,
                height: 12,
                borderRadius: id === "devices" ? 2 : id === "focus" ? 3 : "50%",
                background: id === active ? "var(--cyan)" : "var(--faint)",
                transform: id === "devices" ? "rotate(45deg)" : "none",
                border: id === "focus" ? "1.5px solid var(--faint)" : "none",
              }}
            />
          </div>
        ))}
      </div>
      <div
        style={{
          marginTop: "auto",
          width: 34,
          height: 34,
          borderRadius: "50%",
          background: "var(--bg-3)",
          border: "1px solid var(--stroke-soft)",
        }}
      />
    </div>
  );
}

function Topbar({ status }) {
  const online = status === "online";
  return (
    <div
      style={{
        height: 54,
        flex: "none",
        borderBottom: "1px solid var(--stroke-soft)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 22px",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16 }}>
          Console
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--faint)" }}>
          {online ? "en écoute" : status === "connecting" ? "connexion…" : "hors ligne"}
        </span>
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          color: "var(--muted)",
        }}
      >
        <span
          style={{
            display: "flex",
            alignItems: "center",
            gap: 7,
            color: online ? "var(--online)" : "var(--danger)",
          }}
        >
          <span style={dot(online ? "var(--online)" : "var(--danger)")} />
          {online ? "cerveau actif" : "cerveau injoignable"}
        </span>
      </div>
    </div>
  );
}

function Hub({ question, answer, busy }) {
  return (
    <div
      style={{
        flex: 1,
        position: "relative",
        background:
          "radial-gradient(560px 440px at 50% 44%, var(--cyan-dim), transparent 62%)," +
          "repeating-linear-gradient(0deg,var(--grid) 0 1px,transparent 1px 44px)," +
          "repeating-linear-gradient(90deg,var(--grid) 0 1px,transparent 1px 44px)",
        minWidth: 0,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 18,
          left: 20,
          right: 20,
          fontFamily: "var(--font-mono)",
          fontSize: 10,
          color: "var(--faint)",
          letterSpacing: ".14em",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        INTENTION · {question || "—"}
      </div>

      <div
        style={{
          position: "absolute",
          top: "44%",
          left: "50%",
          transform: "translate(-50%,-50%)",
          width: 250,
          height: 250,
        }}
      >
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            width: 250,
            height: 250,
            margin: "-125px 0 0 -125px",
            borderRadius: "50%",
            border: "1px dashed var(--stroke-soft)",
          }}
        />
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            width: 214,
            height: 214,
            margin: "-107px 0 0 -107px",
            borderRadius: "50%",
            border: "1px solid var(--stroke-soft)",
            borderTopColor: "var(--cyan)",
            animation: `spin ${busy ? "2.5s" : "14s"} linear infinite`,
          }}
        />
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            width: 120,
            height: 120,
            margin: "-60px 0 0 -60px",
            borderRadius: "50%",
            background: "radial-gradient(circle,var(--glow),transparent 68%)",
            animation: "breathe 5s ease-in-out infinite",
          }}
        />
        <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)", textAlign: "center" }}>
          <div
            style={{
              fontFamily: "var(--font-display)",
              fontWeight: 600,
              fontSize: 14,
              letterSpacing: ".3em",
              color: "var(--cyan)",
              textShadow: "0 0 18px var(--glow)",
            }}
          >
            JARVIS
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", letterSpacing: ".12em", marginTop: 5 }}>
            PC FIXE · CERVEAU
          </div>
        </div>
      </div>

      {(answer || busy) && (
        <div
          style={{
            position: "absolute",
            bottom: 90,
            left: "50%",
            transform: "translateX(-50%)",
            maxWidth: 560,
            textAlign: "center",
            padding: "14px 20px",
            borderRadius: 14,
            border: "1px solid var(--stroke-soft)",
            background: "var(--bg-2)",
            fontSize: 14,
            lineHeight: 1.5,
            color: "var(--text)",
          }}
        >
          {answer || <span style={{ color: "var(--faint)" }}>Réflexion…</span>}
        </div>
      )}
    </div>
  );
}

function CommandBar({ status, busy, onSend }) {
  const [value, setValue] = useState("");

  function submit() {
    if (!value.trim() || busy) return;
    onSend(value);
    setValue("");
  }

  return (
    <div
      style={{
        height: 62,
        flex: "none",
        borderTop: "1px solid var(--stroke-soft)",
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "0 22px",
        background: "var(--bg-2)",
      }}
    >
      <div
        style={{
          position: "relative",
          width: 40,
          height: 40,
          borderRadius: "50%",
          background: "var(--cyan-dim)",
          border: "1px solid var(--stroke)",
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "center",
          gap: 3,
          paddingBottom: 13,
          boxShadow: "0 0 22px -6px var(--glow)",
          flex: "none",
          opacity: 0.5,
        }}
        title="Micro — pas encore branché (Phase 3)"
      >
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            style={{
              width: 3,
              height: [12, 17, 10][i],
              borderRadius: 3,
              background: "var(--cyan)",
            }}
          />
        ))}
      </div>

      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="Parlez, ou tapez une commande…"
        disabled={status !== "online"}
        style={{
          flex: 1,
          background: "transparent",
          border: "none",
          outline: "none",
          color: "var(--text)",
          fontFamily: "var(--font-body)",
          fontSize: 14,
        }}
      />

      <button
        onClick={submit}
        disabled={status !== "online" || busy || !value.trim()}
        style={{
          width: 40,
          height: 40,
          borderRadius: 11,
          background: "var(--cyan)",
          border: "none",
          display: "grid",
          placeItems: "center",
          boxShadow: "0 0 24px -6px var(--glow)",
          flex: "none",
          cursor: "pointer",
          opacity: status === "online" && !busy && value.trim() ? 1 : 0.4,
        }}
        aria-label="Envoyer"
      >
        <div
          style={{
            width: 0,
            height: 0,
            borderLeft: "9px solid var(--bg)",
            borderTop: "6px solid transparent",
            borderBottom: "6px solid transparent",
            marginLeft: 3,
          }}
        />
      </button>
    </div>
  );
}

export default function Console() {
  const { status, question, answer, busy, ask } = useChat();

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        padding: 24,
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 1160,
          height: "min(720px, 90vh)",
          border: "1px solid var(--stroke-soft)",
          borderRadius: 20,
          overflow: "hidden",
          display: "flex",
          background: "var(--bg)",
          boxShadow: "0 40px 90px -50px #000",
        }}
      >
        <Dock />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          <Topbar status={status} />
          <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
            <Hub question={question} answer={answer} busy={busy} />
          </div>
          <CommandBar status={status} busy={busy} onSend={ask} />
        </div>
      </div>
    </div>
  );
}

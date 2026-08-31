import { useEffect, useRef, useState } from "react";
import { authFetch } from "../lib/consoleAuth.js";
import { useChat } from "../lib/useChat.js";
import { useVoice } from "../lib/useVoice.js";
import Frame from "./Frame.jsx";

const dot = (color, size = 7) => ({
  width: size,
  height: size,
  borderRadius: "50%",
  background: color,
  boxShadow: `0 0 8px ${color}`,
  flex: "none",
});

function Topbar({ status, voice }) {
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
        {voice.armed && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--cyan)" }}>
            · écoute vocale active
          </span>
        )}
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

const VOICE_STATUS_LABELS = {
  idle: "Micro — cliquer pour armer l'écoute vocale",
  listening: "Écoute vocale active — dites « Jarvis »",
  listening_command: "Jarvis vous écoute…",
  transcribing: "Transcription…",
  speaking: "Jarvis parle…",
};

// Visible en clair (pas juste un tooltip au survol) : ce que le micro
// entend réellement, pour répondre à « je sais pas s'il comprend ce que
// je dis » — sans ça, la fenêtre d'écoute armée est une boîte noire.
function VoiceStatusBar({ voice }) {
  if (!voice.armed) return null;
  return (
    <div
      style={{
        padding: "10px 22px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        fontSize: 12,
        background: "var(--bg-2)",
        borderTop: "1px solid var(--stroke-soft)",
      }}
    >
      <span
        style={{
          fontFamily: "var(--font-mono)",
          color: voice.wakeWordHeard ? "var(--online)" : "var(--cyan)",
          fontWeight: 600,
        }}
      >
        {voice.wakeWordHeard ? "✓ « Jarvis » détecté" : VOICE_STATUS_LABELS[voice.status]}
        {voice.status === "listening" && (
          <span style={{ color: "var(--faint)", fontWeight: 400 }}>
            {" "}· score {voice.lastScore.toFixed(2)}
          </span>
        )}
      </span>
      {voice.lastTranscript && (
        <span
          style={{
            color: "var(--faint)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            maxWidth: "60%",
          }}
        >
          entendu : « {voice.lastTranscript} »
        </span>
      )}
    </div>
  );
}

function CommandBar({ status, busy, onSend, voice }) {
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
      <button
        onClick={() => (voice.armed ? voice.disarm() : voice.arm())}
        title={VOICE_STATUS_LABELS[voice.status] || "Micro"}
        style={{
          position: "relative",
          width: 40,
          height: 40,
          borderRadius: "50%",
          background: voice.armed ? "var(--cyan)" : "var(--cyan-dim)",
          border: "1px solid var(--stroke)",
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "center",
          gap: 3,
          paddingBottom: 13,
          boxShadow: "0 0 22px -6px var(--glow)",
          flex: "none",
          cursor: "pointer",
          animation: voice.status === "listening_command" || voice.status === "transcribing"
            ? "breathe 1.2s ease-in-out infinite" : "none",
        }}
      >
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            style={{
              width: 3,
              height: [12, 17, 10][i],
              borderRadius: 3,
              background: voice.armed ? "var(--bg)" : "var(--cyan)",
            }}
          />
        ))}
      </button>

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

export default function Console({ onNavigate, focusEnabled }) {
  const { status, question, answer, busy, ask } = useChat();
  const lastWasVoiceRef = useRef(false);
  const wasBusyRef = useRef(false);

  // Déclaration de fonction (hoistée) : peut référencer `voice` avant sa
  // ligne `const` ci-dessous, tant qu'elle n'est appelée qu'après coup
  // (useVoice ne l'appelle que plus tard, de façon asynchrone, une fois
  // le composant entièrement rendu — voir onCommandRef dans useVoice.js).
  function handleVoiceCommand(text) {
    lastWasVoiceRef.current = true;
    voice.pause();
    ask(text);
  }

  const voice = useVoice({ onCommand: handleVoiceCommand });

  // Un tour vient de se terminer (busy: true → false) : si la question
  // venait de la voix, on synthétise et on lit la réponse, puis on
  // reprend l'écoute — sinon on reprend directement (une réponse à une
  // question tapée ne doit pas se mettre à parler toute seule).
  useEffect(() => {
    if (wasBusyRef.current && !busy) {
      if (lastWasVoiceRef.current) {
        lastWasVoiceRef.current = false;
        speakAnswer(answer, voice);
      }
    }
    wasBusyRef.current = busy;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy]);

  return (
    <Frame active="console" onNavigate={onNavigate} focusEnabled={focusEnabled}>
      <Topbar status={status} voice={voice} />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <Hub question={question} answer={answer} busy={busy} />
      </div>
      {voice.error && (
        <div
          style={{
            padding: "8px 22px",
            fontSize: 12,
            color: "var(--danger)",
            background: "var(--bg-2)",
            borderTop: "1px solid var(--stroke-soft)",
          }}
        >
          {voice.error}
        </div>
      )}
      <VoiceStatusBar voice={voice} />
      <CommandBar status={status} busy={busy} onSend={ask} voice={voice} />
    </Frame>
  );
}

async function speakAnswer(text, voice) {
  if (!text) {
    voice.resume();
    return;
  }
  try {
    const res = await authFetch("/api/speech/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      voice.resume();
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => {
      URL.revokeObjectURL(url);
      voice.resume();
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      voice.resume();
    };
    await audio.play();
  } catch {
    voice.resume();
  }
}

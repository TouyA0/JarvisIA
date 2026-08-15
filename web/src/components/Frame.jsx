import Dock from "./Dock.jsx";

export default function Frame({ active, onNavigate, focusEnabled, children }) {
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
        <Dock active={active} onNavigate={onNavigate} focusEnabled={focusEnabled} />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {children}
        </div>
      </div>
    </div>
  );
}

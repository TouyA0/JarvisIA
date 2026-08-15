export default function Reactor({ size = 38 }) {
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
      <div
        style={{
          width: size * 0.24,
          height: size * 0.24,
          borderRadius: "50%",
          background: "var(--cyan)",
          boxShadow: "0 0 12px var(--cyan)",
        }}
      />
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

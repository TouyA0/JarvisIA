/**
 * Jeu d'icônes en trait, une seule source. Remplace les formes
 * géométriques anonymes de l'ancien dock (losange = « appareils »,
 * triangle = « routines »…) que rien ne permettait de deviner.
 *
 * Toutes tracées sur une grille 24, en `currentColor` : la couleur vient
 * du parent, jamais de l'icône — c'est ce qui permet aux états (actif,
 * désactivé, danger) de rester cohérents partout.
 */
const PATHS = {
  chat: "M21 12a8 8 0 0 1-8 8H8l-4 3v-4.6A8 8 0 0 1 5 5.6 8 8 0 0 1 13 4a8 8 0 0 1 8 8Z",
  devices: "M4 5h11v9H4zM4 18h11M9.5 14v4M17 9h3v10h-3z",
  focus: "M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M12 9.5A2.5 2.5 0 1 0 12 14.5 2.5 2.5 0 1 0 12 9.5Z",
  routines: "M4 6h9M4 12h9M4 18h9M17 4.5v15M17 4.5l3 3M17 4.5l-3 3",
  integrations: "M9 3v5M15 3v5M6.5 8h11v4a5.5 5.5 0 0 1-11 0zM12 17.5V21",
  system: "M5 7h14M5 12h14M5 17h14M9 5v4M15 10v4M11 15v4",
  mic: "M12 3a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3ZM6 11a6 6 0 0 0 12 0M12 17v4M9 21h6",
  send: "M4.5 12 20 5l-4 14-4.5-5.5L4.5 12Zm7 1.5L20 5",
  plus: "M12 5v14M5 12h14",
  trash: "M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13M10 11v6M14 11v6",
  refresh: "M20 11a8 8 0 1 0-.7 4M20 5v6h-6",
  check: "M4.5 12.5 9.5 18 20 6.5",
  x: "M6 6l12 12M18 6 6 18",
  lock: "M6 11h12v9H6zM9 11V7.5a3 3 0 0 1 6 0V11",
  camera: "M4 8h3.5L9 5.5h6L16.5 8H20v12H4zM12 17a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z",
  key: "M14.5 10.5a4 4 0 1 0-4 4l1.5 1.5-1 1 1.5 1.5-1 1 1.5 1.5 3-3-1.5-6.5ZM15.5 7.5h.01",
  link: "M10 14a4 4 0 0 0 6 .5l2-2a4 4 0 0 0-6-6l-1 1M14 10a4 4 0 0 0-6-.5l-2 2a4 4 0 0 0 6 6l1-1",
  alert: "M12 4 2.5 20h19L12 4ZM12 10v5M12 18h.01",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 11v5M12 8h.01",
  brain: "M9.5 4a2.5 2.5 0 0 0-2.5 2.5A2.5 2.5 0 0 0 5 9c0 1 .5 1.8 1.2 2.3A2.6 2.6 0 0 0 5.5 13c0 1.5 1.3 2.7 2.8 2.7v1.8A2.5 2.5 0 0 0 10.8 20h.7V4ZM14.5 4a2.5 2.5 0 0 1 2.5 2.5A2.5 2.5 0 0 1 19 9c0 1-.5 1.8-1.2 2.3.4.5.7 1.1.7 1.7 0 1.5-1.3 2.7-2.8 2.7v1.8A2.5 2.5 0 0 1 13.2 20h-.7V4Z",
  coin: "M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM14.5 9.5a2.8 2.8 0 0 0-5 1.7c0 2.6 5 1.4 5 3.6a2.8 2.8 0 0 1-5 1.2M12 7v10",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5.2l3.2 2",
  power: "M12 4v8M7.5 6.8a7 7 0 1 0 9 0",
  eye: "M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Zm9.5 2.6a2.6 2.6 0 1 0 0-5.2 2.6 2.6 0 0 0 0 5.2Z",
  play: "M7 4.5 19 12 7 19.5v-15Z",
  chevron: "m9 5 7 7-7 7",
  copy: "M9 9h11v11H9zM5 15H4V4h11v1",
  pencil: "M4 20h4L19 9a2.12 2.12 0 0 0-3-3L5 17v3ZM14.5 6.5l3 3",
  menu: "M4 7h16M4 12h16M4 17h16",
  sun: "M12 4v2M12 18v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4 12h2M18 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4M12 8.5A3.5 3.5 0 1 0 12 15.5 3.5 3.5 0 0 0 12 8.5Z",
  pause: "M8 5v14M16 5v14",
  "skip-next": "M6 5v14l10-7-10-7Zm12 0v14",
  "skip-prev": "M18 5v14L8 12l10-7Zm-12 0v14",
  download: "M12 3v12M8 11l4 4 4-4M5 19h14",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14ZM21 21l-4.35-4.35",
  expand: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
  collapse: "M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5",
  note: "M6 3h9l4 4v14H6zM15 3v4h4M8.5 12h7M8.5 15.5h7M8.5 8.5h3",
  sliders:
    "M3 6h4M11 6h10M7 6A2 2 0 1 0 11 6A2 2 0 1 0 7 6" +
    "M3 12h10M17 12h4M13 12A2 2 0 1 0 17 12A2 2 0 1 0 13 12" +
    "M3 18h6M13 18h8M9 18A2 2 0 1 0 13 18A2 2 0 1 0 9 18",
  "chevron-up": "M5 15l7-7 7 7",
  "chevron-down": "M5 9l7 7 7-7",
  "chevron-left": "M15 5l-7 7 7 7",
  "chevron-right": "M9 5l7 7-7 7",
  home: "M4 11 12 4l8 7M6 10v9h4v-5h4v5h4v-9",
  back: "M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11",
  tv: "M3 4h18v13H3zM9 20h6M12 17v3",
};

export default function Icon({ name, size = 18, strokeWidth = 1.6, className = "" }) {
  const d = PATHS[name];
  if (!d) return null;
  return (
    <svg
      className={`icon ${className}`.trim()}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={d} />
    </svg>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import CommandPalette from "./ui/CommandPalette.jsx";
import Icon from "./ui/Icon.jsx";
import ModeSwitcher from "./ui/ModeSwitcher.jsx";
import Reactor from "./ui/Reactor.jsx";
import { useBrainStatus } from "../lib/useBrainStatus.js";
import { useFullscreen } from "../lib/useFullscreen.js";
import { useGlobalShortcuts } from "../lib/useGlobalShortcuts.js";
import { useIsMobile } from "../lib/useIsMobile.js";
import { useVoiceContext } from "../lib/VoiceContext.jsx";

/**
 * Coquille de l'application : navigation, identité, état du brain.
 *
 * Deux principes, appris des versions précédentes :
 *
 *  1. Chaque entrée a un libellé écrit. Le dock d'origine était une
 *     colonne de formes géométriques (un losange pour « Appareils »)
 *     dont le seul indice était un `title` au survol, en anglais.
 *
 *  2. La navigation ne bouge pas. Elle liste des endroits, pas des
 *     états : piloter un appareil ne fait plus apparaître une entrée
 *     « Focus » de plus — le pilotage est un détail *dans* Appareils,
 *     avec un retour à la liste, comme n'importe quelle vue de détail.
 */
const NAV_ITEMS = [
  { id: "hud", label: "Pupitre", icon: "reactor", short: "Pupitre" },
  { id: "console", label: "Conversation", icon: "chat", short: "Parler" },
  { id: "devices", label: "Appareils", icon: "devices", short: "Appareils" },
  { id: "notes", label: "Notes", icon: "note", short: "Notes" },
  { id: "routines", label: "Routines", icon: "routines", short: "Routines" },
  { id: "integrations", label: "Intégrations", icon: "integrations", short: "Comptes" },
  { id: "system", label: "Système", icon: "system", short: "Système" },
];

function reactorState(status) {
  if (status === "offline") return "offline";
  if (status === "connecting") return "busy";
  return "idle";
}

function NavIcon({ name }) {
  // Le pupitre n'a pas d'icône de trait : c'est le réacteur lui-même,
  // en miniature — la même chose que ce que l'écran affiche en grand.
  if (name === "reactor") return <Reactor size={18} />;
  return <Icon name={name} size={18} />;
}

export default function AppShell({ view, onNavigate, children }) {
  const isMobile = useIsMobile();
  const status = useBrainStatus();
  const voice = useVoiceContext();
  const { isFullscreen } = useFullscreen();
  const mainRef = useRef(null);
  const announceRef = useRef(null);
  const isFirstRender = useRef(true);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useGlobalShortcuts({ voice, onOpenPalette: () => setPaletteOpen(true) });

  // Écrans + bascule micro : les seules commandes qui existent pour
  // l'instant. Pas de « effacer l'affichage » ni d'action propre à un
  // écran — la palette est un raccourci de navigation globale, pas un
  // second menu contextuel pour chaque vue.
  const commands = useMemo(
    () => [
      ...NAV_ITEMS.map((item) => ({
        id: `nav-${item.id}`,
        label: `Aller à ${item.label}`,
        icon: item.icon === "reactor" ? "power" : item.icon,
        hint: item.id === view ? "écran actuel" : undefined,
        run: () => onNavigate(item.id),
      })),
      {
        id: "voice-toggle",
        label: voice.armed ? "Couper l'écoute vocale" : "Activer l'écoute vocale",
        icon: "mic",
        run: () => (voice.armed ? voice.disarm() : voice.arm()),
      },
    ],
    [view, onNavigate, voice],
  );

  const statusLabel =
    status === "online" ? "Brain connecté" : status === "connecting" ? "Connexion…" : "Brain injoignable";

  // Coquilles à écrans sans routeur : `onNavigate` remplace le contenu de
  // <main> mais ne bouge ni le focus ni le contexte annoncé — au lecteur
  // d'écran, rien ne se passe. On déplace le focus sur le titre de la vue
  // (ou sur <main> à défaut, pour les écrans qui n'en ont pas encore) et on
  // annonce le nouveau titre dans une région aria-live dédiée.
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    const label = NAV_ITEMS.find((item) => item.id === view)?.label ?? view;
    const heading = mainRef.current?.querySelector("#view-title");
    (heading || mainRef.current)?.focus();
    if (announceRef.current) {
      announceRef.current.textContent = label;
    }
  }, [view]);

  if (isMobile) {
    return (
      <div className="app" style={{ flexDirection: "column" }}>
        <a className="skip-link" href="#contenu">
          Aller au contenu
        </a>
        <main id="contenu" className="view" tabIndex={-1} ref={mainRef}>
          {children}
        </main>
        <div className="sr-only" role="status" aria-live="polite" ref={announceRef} />
        <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} />
        {/* En plein écran (J4), la barre d'onglets disparaît : rien à
            poser sur une tablette fixée au mur ou un second écran. */}
        {!isFullscreen && (
          <nav className="tabbar" aria-label="Navigation principale">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.id}
                type="button"
                className="tab"
                aria-current={item.id === view ? "page" : undefined}
                onClick={() => onNavigate(item.id)}
              >
                <NavIcon name={item.icon} />
                {item.short}
              </button>
            ))}
          </nav>
        )}
      </div>
    );
  }

  return (
    <div className="app">
      <a className="skip-link" href="#contenu">
        Aller au contenu
      </a>
      {/* Même principe côté bureau : le plein écran masque la barre
          latérale entière, pas seulement la liste de navigation — voir
          J4. */}
      {!isFullscreen && (
        <nav className="nav" aria-label="Navigation principale">
          <div className="nav-brand">
            <Reactor size={34} state={reactorState(status)} />
            <span className="nav-brand-text">
              <span className="nav-brand-title">J.A.R.V.I.S.</span>
              <span className="nav-brand-sub">console</span>
            </span>
          </div>

          <ul className="nav-list">
            {NAV_ITEMS.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className="nav-item"
                  aria-current={item.id === view ? "page" : undefined}
                  onClick={() => onNavigate(item.id)}
                >
                  <NavIcon name={item.icon} />
                  <span className="nav-item-label">{item.label}</span>
                </button>
              </li>
            ))}
          </ul>

          <div className="nav-foot">
            <ModeSwitcher variant="nav" />
            <button
              type="button"
              className="nav-item"
              onClick={() => setPaletteOpen(true)}
            >
              <Icon name="search" size={18} />
              <span className="nav-item-label">Commandes</span>
              <span className="kbd" aria-hidden="true" style={{ marginLeft: "auto" }}>
                Ctrl+K
              </span>
            </button>
            <div className="row" style={{ padding: "0 var(--sp-2)", gap: "var(--sp-2)" }}>
              <span
                className={`dot ${status === "online" ? "dot--ok" : status === "connecting" ? "dot--cyan" : "dot--danger"}`}
                aria-hidden="true"
              />
              <span className="nav-item-note">{statusLabel}</span>
            </div>
          </div>
        </nav>
      )}

      <main id="contenu" className="view" tabIndex={-1} ref={mainRef}>
        {children}
      </main>
      <div className="sr-only" role="status" aria-live="polite" ref={announceRef} />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} />
    </div>
  );
}

/**
 * En-tête de vue. Chaque écran avait sa propre `Topbar` recopiée à
 * l'identique — même hauteur, même bordure, même typo, quatre fois.
 * `onBack` ajoute le retour des vues de détail (le pilotage d'un
 * appareil, par exemple).
 */
export function ViewHeader({ title, subtitle, actions, onBack, backLabel = "Retour" }) {
  return (
    <header className="view-header">
      {onBack && (
        <button type="button" className="icon-btn" onClick={onBack} aria-label={backLabel}>
          <Icon name="chevron" size={18} className="rot-left" />
        </button>
      )}
      <div className="view-heading">
        <h1 id="view-title" className="view-title" tabIndex={-1}>
          {title}
        </h1>
        {subtitle && <span className="view-subtitle">{subtitle}</span>}
      </div>
      {actions && <div className="view-actions">{actions}</div>}
    </header>
  );
}

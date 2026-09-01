import Icon from "./ui/Icon.jsx";
import ModeSwitcher from "./ui/ModeSwitcher.jsx";
import Reactor from "./ui/Reactor.jsx";
import { useBrainStatus } from "../lib/useBrainStatus.js";
import { useIsMobile } from "../lib/useIsMobile.js";

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

  const statusLabel =
    status === "online" ? "Brain connecté" : status === "connecting" ? "Connexion…" : "Brain injoignable";

  if (isMobile) {
    return (
      <div className="app" style={{ flexDirection: "column" }}>
        <a className="skip-link" href="#contenu">
          Aller au contenu
        </a>
        <main id="contenu" className="view">
          {children}
        </main>
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
      </div>
    );
  }

  return (
    <div className="app">
      <a className="skip-link" href="#contenu">
        Aller au contenu
      </a>
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
          <div className="row" style={{ padding: "0 var(--sp-2)", gap: "var(--sp-2)" }}>
            <span
              className={`dot ${status === "online" ? "dot--ok" : status === "connecting" ? "dot--cyan" : "dot--danger"}`}
              aria-hidden="true"
            />
            <span className="nav-item-note">{statusLabel}</span>
          </div>
        </div>
      </nav>

      <main id="contenu" className="view">
        {children}
      </main>
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
        <h1 className="view-title">{title}</h1>
        {subtitle && <span className="view-subtitle">{subtitle}</span>}
      </div>
      {actions && <div className="view-actions">{actions}</div>}
    </header>
  );
}

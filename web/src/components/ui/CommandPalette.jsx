import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "./Icon.jsx";

/**
 * Palette de commandes (Ctrl+K, ou Cmd+K sur Mac) : aller à un écran ou
 * basculer le micro sans lâcher le clavier. Un des trois manques listés
 * sous « Confort » — avec elle et Ctrl+Alt+J (voir useGlobalShortcuts.js),
 * la Console a enfin un clavier qui ne passe plus uniquement par la souris
 * pour naviguer.
 *
 * Liste filtrée par sous-chaîne, pas de recherche floue : le nombre de
 * commandes reste petit (six écrans + le micro), une vraie recherche
 * floue serait de la complexité sans bénéfice ici.
 */
export default function CommandPalette({ open, onClose, commands }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const previousFocusRef = useRef(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => c.label.toLowerCase().includes(q));
  }, [query, commands]);

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current = document.activeElement;
    setQuery("");
    setActive(0);
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  useEffect(() => setActive(0), [query]);

  useEffect(() => {
    if (!open) return undefined;
    function onKeyDown(e) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((a) => Math.min(a + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((a) => Math.max(a - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const cmd = filtered[active];
        if (cmd) {
          onClose();
          cmd.run();
        }
      }
    }
    document.addEventListener("keydown", onKeyDown, true);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      document.body.style.overflow = previousOverflow;
      previousFocusRef.current?.focus?.();
    };
  }, [open, onClose, filtered, active]);

  if (!open) return null;

  const activeId = filtered[active] ? `cmdpal-${filtered[active].id}` : undefined;

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal command-palette" role="dialog" aria-modal="true" aria-label="Palette de commandes">
        <div className="command-palette-input">
          <Icon name="search" size={16} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Aller à un écran, basculer le micro…"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-list"
            aria-activedescendant={activeId}
            aria-autocomplete="list"
            aria-label="Rechercher une commande"
          />
        </div>
        <ul className="command-palette-list" id="command-palette-list" role="listbox">
          {filtered.length === 0 && <li className="command-palette-empty">Aucune commande</li>}
          {filtered.map((cmd, i) => (
            <li
              key={cmd.id}
              id={`cmdpal-${cmd.id}`}
              role="option"
              aria-selected={i === active}
              className={`command-palette-item${i === active ? " command-palette-item--active" : ""}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => {
                onClose();
                cmd.run();
              }}
            >
              <Icon name={cmd.icon} size={16} />
              <span>{cmd.label}</span>
              {cmd.hint && <span className="command-palette-hint">{cmd.hint}</span>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

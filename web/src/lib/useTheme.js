import { useCallback, useEffect, useState } from "react";

/**
 * Sélecteur de thème (F33) — la palette est déjà entièrement en variables
 * CSS (`styles/tokens.css`), donc changer de thème revient à poser un
 * attribut `data-theme` sur `<html>` : aucun état serveur, pas de rendu à
 * refaire. Persisté en local (par appareil, pas par compte) comme le reste
 * des préférences d'affichage de la Console.
 */

const STORAGE_KEY = "jarvis-theme";

export const THEMES = [
  { id: "default", name: "Réacteur", description: "Cyan froid, la teinte d'origine du pupitre." },
  { id: "mark42", name: "Mark 42", description: "Rouge et or." },
  { id: "warmachine", name: "War Machine", description: "Gris gunmetal." },
  { id: "vision", name: "Vision", description: "Pourpre." },
];

function apply(id) {
  if (id === "default") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", id);
  }
}

function readStored() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return THEMES.some((t) => t.id === stored) ? stored : "default";
  } catch {
    return "default";
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState(readStored);

  // Applique dès le premier rendu React — un script inline dans index.html
  // pose déjà l'attribut avant le premier paint pour éviter le flash.
  useEffect(() => {
    apply(theme);
  }, [theme]);

  const setTheme = useCallback((id) => {
    if (!THEMES.some((t) => t.id === id)) return;
    setThemeState(id);
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      // stockage indisponible (navigation privée…) — le thème tient pour la session
    }
  }, []);

  return { theme, setTheme, themes: THEMES };
}

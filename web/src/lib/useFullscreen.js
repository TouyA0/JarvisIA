import { useCallback, useEffect, useState } from "react";

/**
 * État plein écran du document (Fullscreen API), sans prop drilling :
 * AppShell (masquer nav/en-tête) et Hud (bouton + mise en page agrandie)
 * l'appellent chacun séparément et restent synchronisés via l'événement
 * natif `fullscreenchange` — pas besoin d'un contexte React pour ça.
 *
 * Voir J4 : un pupitre posé sur une tablette fixée au mur ne doit garder
 * ni barre latérale ni navigation, seulement le réacteur, l'horloge et les
 * cartes ambiantes.
 */
export function useFullscreen() {
  const [isFullscreen, setIsFullscreen] = useState(() => Boolean(document.fullscreenElement));

  useEffect(() => {
    function onChange() {
      setIsFullscreen(Boolean(document.fullscreenElement));
    }
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const enter = useCallback(() => {
    document.documentElement.requestFullscreen?.().catch(() => {});
  }, []);

  const exit = useCallback(() => {
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
  }, []);

  const toggle = useCallback(() => {
    if (document.fullscreenElement) exit();
    else enter();
  }, [enter, exit]);

  return { isFullscreen, enter, exit, toggle };
}

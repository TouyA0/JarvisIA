import { useEffect, useState } from "react";

// Sous cette largeur, le dock passe en barre basse et les panneaux
// latéraux (rail droit) passent sous le contenu principal au lieu
// d'à côté — pas un simple reflow, une réorganisation (voir design,
// écran 05 Mobile).
const BREAKPOINT = 768;

export function useIsMobile() {
  const [isMobile, setIsMobile] = useState(
    typeof window !== "undefined" ? window.innerWidth < BREAKPOINT : false,
  );

  useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${BREAKPOINT - 1}px)`);
    const onChange = () => setIsMobile(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return isMobile;
}

import { useEffect } from "react";

/**
 * Raccourcis clavier globaux — l'un des trois manques « Confort » relevés
 * dans l'audit (A11) : la Console n'avait ni raccourci « parler » (le PC
 * fixe a Ctrl+Alt+J, voir agents/desktop), ni palette de commandes, ni
 * Échap pour couper la parole à Jarvis.
 *
 * Écouteur en phase bulle sur `document`, comme le reste de la Console.
 * Un dialogue ouvert (Modal.jsx, CommandPalette.jsx) intercepte déjà Échap
 * en phase de capture et appelle `stopPropagation()` : cet écouteur ne
 * voit donc l'Échap que si rien n'est ouvert par-dessus, et ne coupe la
 * voix que dans ce cas — jamais en même temps qu'un dialogue se ferme.
 */
export function useGlobalShortcuts({ voice, onOpenPalette }) {
  useEffect(() => {
    function onKeyDown(e) {
      const key = e.key.toLowerCase();

      if (e.altKey && (e.ctrlKey || e.metaKey) && key === "j") {
        e.preventDefault();
        if (voice.armed) voice.disarm();
        else voice.arm();
        return;
      }

      if ((e.ctrlKey || e.metaKey) && !e.altKey && key === "k") {
        e.preventDefault();
        onOpenPalette();
        return;
      }

      if (key === "escape" && voice.status === "speaking") {
        voice.stopSpeaking();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [voice, onOpenPalette]);
}

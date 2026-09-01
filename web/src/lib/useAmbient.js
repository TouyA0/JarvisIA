import { useEffect, useState } from "react";
import { authFetch } from "./consoleAuth.js";

/**
 * Panorama silencieux du pupitre (F29) : météo, agenda du jour, santé
 * système — ce qu'un écran laissé allumé dans une pièce doit dire même
 * quand on ne lui a rien demandé (voir Hud.jsx::Ambient).
 *
 * `/api/ambient` (server.py) est déjà mis en cache côté brain ; le
 * polling ici n'est qu'un rafraîchissement d'affichage, pas la source du
 * cache — un intervalle plus court que le TTL brain ne coûterait qu'un
 * aller-retour réseau de plus, pas une nouvelle requête Google/psutil.
 */
const POLL_MS = 3 * 60 * 1000;

// brain/server.py::_ambient_snapshot renvoie les mêmes formes de `data`
// que cards.emit pour ces types — les renderers de cartes existants
// (renderers.jsx) s'appliquent tels quels.
function toCards(payload) {
  const cards = [];
  if (payload.weather) {
    cards.push({
      id: "ambient-weather",
      type: "weather",
      title: `${Math.round(payload.weather.temp)}°C`,
      subtitle: payload.weather.description,
      data: payload.weather,
      at: Date.now() / 1000,
    });
  }
  if (payload.agenda) {
    cards.push({
      id: "ambient-agenda",
      type: "agenda",
      title: "Aujourd'hui",
      subtitle: `${payload.agenda.events.length} événement${payload.agenda.events.length > 1 ? "s" : ""}`,
      data: payload.agenda,
      at: Date.now() / 1000,
    });
  }
  if (payload.diagnostics) {
    cards.push({
      id: "ambient-diagnostics",
      type: "diagnostics",
      title: "État du système",
      subtitle: `CPU ${payload.diagnostics.cpu}% · RAM ${payload.diagnostics.mem}%`,
      data: payload.diagnostics,
      at: Date.now() / 1000,
    });
  }
  return cards;
}

export function useAmbient() {
  const [cards, setCards] = useState([]);

  useEffect(() => {
    let cancelled = false;

    async function refresh() {
      try {
        const res = await authFetch("/api/ambient");
        if (!res.ok || cancelled) return;
        setCards(toCards(await res.json()));
      } catch {
        // brain injoignable — on garde le dernier panorama connu à l'écran
      }
    }

    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return cards;
}

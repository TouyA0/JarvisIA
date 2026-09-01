import { useEffect, useState } from "react";
import { ViewHeader } from "./AppShell.jsx";
import Icon from "./ui/Icon.jsx";
import { TextField } from "./ui/Field.jsx";
import { useToast } from "./ui/Toast.jsx";
import { usePreferences } from "../lib/usePreferences.js";

/**
 * Vue Réglages (C6 / F26 de la roadmap) — jusqu'ici uniquement dans
 * `.env`, à éditer à la main et redémarrer le brain pour voir l'effet
 * (brain/preferences.py). Ne couvre que ce qui a un sens depuis
 * n'importe quel appareil : ville météo, seuils et horaires de la
 * proactivité (C3). La voix, les seuils de barge-in et les raccourcis
 * clavier restent propres au poste physique (agents/desktop/config.py) —
 * les éditer depuis un téléphone n'aurait pas de sens, ce n'est pas ce
 * PC-là qui écoute.
 */

function hhmm(hour, minute) {
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function WeatherSection({ weather, loaded, setWeather }) {
  const [city, setCity] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  useEffect(() => {
    if (!weather) return;
    setCity(weather.city);
    setLat(String(weather.lat));
    setLon(String(weather.lon));
  }, [weather]);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await setWeather(city.trim(), Number(lat), Number(lon));
      toast.success("Ville météo enregistrée.");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!loaded || !weather) return null;

  return (
    <section className="stack">
      <h2 className="section-label">Météo</h2>
      <p className="hint" style={{ maxWidth: 640 }}>
        Ville utilisée pour la carte météo, le panorama du pupitre et le briefing matinal. Les coordonnées
        (latitude/longitude) déterminent le point exact interrogé — cherchez-les sur une carte si le nom de
        ville seul est ambigu.
      </p>
      <form className="row row--wrap" style={{ gap: "var(--sp-3)", alignItems: "flex-end" }} onSubmit={submit}>
        <TextField label="Ville" value={city} onChange={(e) => setCity(e.target.value)} required />
        <TextField
          label="Latitude"
          type="number"
          step="0.0001"
          value={lat}
          onChange={(e) => setLat(e.target.value)}
          required
        />
        <TextField
          label="Longitude"
          type="number"
          step="0.0001"
          value={lon}
          onChange={(e) => setLon(e.target.value)}
          required
        />
        <button type="submit" className="btn btn--primary" disabled={busy || !city.trim()}>
          <Icon name="check" size={16} />
          Enregistrer
        </button>
      </form>
    </section>
  );
}

function ProactiveSection({ proactive, loaded, setProactive }) {
  const [enabled, setEnabled] = useState(true);
  const [diskThreshold, setDiskThreshold] = useState("90");
  const [ramThreshold, setRamThreshold] = useState("90");
  const [bedtime, setBedtime] = useState("23:30");
  const [briefing, setBriefing] = useState("08:00");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  useEffect(() => {
    if (!proactive) return;
    setEnabled(proactive.enabled);
    setDiskThreshold(String(proactive.disk_threshold));
    setRamThreshold(String(proactive.ram_threshold));
    setBedtime(hhmm(proactive.bedtime_hour, proactive.bedtime_minute));
    setBriefing(hhmm(proactive.briefing_hour, proactive.briefing_minute));
  }, [proactive]);

  async function submit(e) {
    e.preventDefault();
    const [bedtimeHour, bedtimeMinute] = bedtime.split(":").map(Number);
    const [briefingHour, briefingMinute] = briefing.split(":").map(Number);
    setBusy(true);
    try {
      await setProactive({
        enabled,
        disk_threshold: Number(diskThreshold),
        ram_threshold: Number(ramThreshold),
        bedtime_hour: bedtimeHour,
        bedtime_minute: bedtimeMinute,
        briefing_hour: briefingHour,
        briefing_minute: briefingMinute,
      });
      toast.success("Proactivité enregistrée.");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!loaded || !proactive) return null;

  return (
    <section className="stack">
      <h2 className="section-label">Proactivité</h2>
      <p className="hint" style={{ maxWidth: 640 }}>
        Alertes disque/RAM, suggestion de coucher, briefing matinal — ce que Jarvis dit sans qu'on le lui
        demande (voir Système → Affichage pour les dernières alertes). Ne change que le comportement du
        brain : le desktop (PC fixe) garde ses propres seuils tant qu'ils ne sont pas alignés à la main.
      </p>
      <form className="stack" onSubmit={submit}>
        <label className="row" style={{ gap: "var(--sp-2)", cursor: "pointer" }}>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          <span>Activée</span>
        </label>

        <div className="row row--wrap" style={{ gap: "var(--sp-3)", alignItems: "flex-end" }}>
          <TextField
            label="Seuil disque (%)"
            type="number"
            min="0"
            max="100"
            value={diskThreshold}
            onChange={(e) => setDiskThreshold(e.target.value)}
          />
          <TextField
            label="Seuil RAM (%)"
            type="number"
            min="0"
            max="100"
            value={ramThreshold}
            onChange={(e) => setRamThreshold(e.target.value)}
          />
        </div>

        <div className="row row--wrap" style={{ gap: "var(--sp-3)", alignItems: "flex-end" }}>
          <TextField label="Heure du coucher" type="time" value={bedtime} onChange={(e) => setBedtime(e.target.value)} />
          <TextField
            label="Heure du briefing"
            type="time"
            value={briefing}
            onChange={(e) => setBriefing(e.target.value)}
          />
        </div>

        <div>
          <button type="submit" className="btn btn--primary" disabled={busy}>
            <Icon name="check" size={16} />
            Enregistrer
          </button>
        </div>
      </form>
    </section>
  );
}

export default function Settings() {
  const { weather, proactive, loaded, setWeather, setProactive } = usePreferences();

  return (
    <>
      <ViewHeader title="Réglages" subtitle="Ce qui était dans .env — sans redémarrer" />
      <div className="view-body">
        <div className="view-main">
          <div className="stack" style={{ gap: "var(--sp-8)", maxWidth: "var(--content-max)" }}>
            <WeatherSection weather={weather} loaded={loaded} setWeather={setWeather} />
            <ProactiveSection proactive={proactive} loaded={loaded} setProactive={setProactive} />
          </div>
        </div>
      </div>
    </>
  );
}

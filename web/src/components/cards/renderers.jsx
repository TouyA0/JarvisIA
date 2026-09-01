import Icon from "../ui/Icon.jsx";

/**
 * Corps des cartes, un rendu par type (voir brain/cards.py pour l'émission
 * et docs/ROADMAP_DISPLAY_INTEGRATIONS.md §2.2 pour la liste prévue).
 *
 * Règle commune : une carte montre ce qui se lit d'un coup d'œil à trois
 * mètres, pas l'intégralité de la donnée. Le détail exhaustif reste dans
 * la réponse écrite/parlée de Jarvis — la carte ne la remplace pas.
 */

const MAX_ROWS = 5;

function Rows({ items, empty, children }) {
  if (!items || items.length === 0) return <p className="card-empty">{empty}</p>;
  return (
    <ul className="card-rows">
      {items.slice(0, MAX_ROWS).map(children)}
      {items.length > MAX_ROWS && (
        <li className="card-more">+ {items.length - MAX_ROWS} de plus</li>
      )}
    </ul>
  );
}

function hourOf(iso) {
  if (!iso) return "—";
  if (!iso.includes("T")) return "journée";
  return iso.slice(11, 16);
}

function Agenda({ data }) {
  return (
    <Rows items={data.events} empty="Rien de prévu. La voie est libre, Monsieur.">
      {(e, i) => (
        <li key={i} className="card-row">
          <span className="card-row-lead">{e.all_day ? "journée" : hourOf(e.start)}</span>
          <span className="card-row-main">
            {e.summary}
            {e.location && <span className="card-row-sub"> · {e.location}</span>}
          </span>
        </li>
      )}
    </Rows>
  );
}

function Mail({ data }) {
  return (
    <Rows items={data.messages} empty="Aucun message.">
      {(m, i) => (
        <li key={i} className="card-row">
          <span className={`dot ${m.unread ? "dot--cyan" : ""}`} aria-hidden="true" />
          <span className="card-row-main">
            <strong>{m.subject || "(sans objet)"}</strong>
            <span className="card-row-sub"> · {m.from}</span>
            {m.snippet && <span className="card-row-snippet">{m.snippet}</span>}
          </span>
        </li>
      )}
    </Rows>
  );
}

function MailDetail({ data }) {
  return (
    <div className="card-prose">
      <p className="card-row-sub">
        {data.from} {data.date && `· ${data.date}`}
      </p>
      <p className="card-text">{data.text}</p>
    </div>
  );
}

function Files({ data }) {
  return (
    <Rows items={data.files} empty="Aucun fichier.">
      {(f, i) => (
        <li key={i} className="card-row">
          <Icon name="copy" size={15} />
          <span className="card-row-main">
            {f.link ? (
              <a href={f.link} target="_blank" rel="noreferrer">
                {f.name}
              </a>
            ) : (
              f.name
            )}
          </span>
        </li>
      )}
    </Rows>
  );
}

function WebResults({ data }) {
  return (
    <Rows items={data.results} empty="Aucun résultat.">
      {(r, i) => (
        <li key={i} className="card-row">
          <Icon name="link" size={15} />
          <span className="card-row-main">
            <a href={r.url} target="_blank" rel="noreferrer">
              <strong>{r.title}</strong>
            </a>
            {r.snippet && <span className="card-row-snippet">{r.snippet}</span>}
          </span>
        </li>
      )}
    </Rows>
  );
}

function DocumentCard({ data }) {
  return (
    <div className="card-prose">
      <p className="card-text">{data.text}</p>
      {data.truncated && <p className="card-more">contenu tronqué</p>}
    </div>
  );
}

function Music({ data }) {
  const pct = data.duration_ms ? Math.min(100, (data.progress_ms / data.duration_ms) * 100) : 0;
  return (
    <div className="card-music">
      {data.cover ? (
        <img className="card-cover" src={data.cover} alt="" />
      ) : (
        <span className="card-cover card-cover--empty" aria-hidden="true">
          <Icon name="play" size={22} />
        </span>
      )}
      <div className="card-music-text">
        <strong>{data.track}</strong>
        <span className="card-row-sub">{data.artists}</span>
        {data.album && <span className="card-row-sub">{data.album}</span>}
        {data.duration_ms > 0 && (
          <span className="meter meter--wide" aria-hidden="true">
            <span className="meter-fill" style={{ width: `${pct}%` }} />
          </span>
        )}
        <span className="card-row-sub">{data.playing ? "en lecture" : "en pause"}</span>
      </div>
    </div>
  );
}

function Screenshot({ data, onZoom }) {
  return (
    <button type="button" className="card-shot" onClick={onZoom} aria-label="Agrandir la capture">
      <img src={`data:${data.media_type || "image/jpeg"};base64,${data.image_b64}`} alt="Capture d'écran" />
    </button>
  );
}

function Transport({ data }) {
  return (
    <Rows items={data.departures} empty="Aucun passage annoncé.">
      {(d, i) => (
        <li key={i} className="card-row">
          <span className="card-row-lead">{d.line || "?"}</span>
          <span className="card-row-main">
            {d.destination || d.stop}
            <span className="card-row-sub"> · {d.waiting ? `dans ${d.waiting}` : d.datetime || ""}</span>
          </span>
        </li>
      )}
    </Rows>
  );
}

function Route({ data }) {
  return (
    <div className="card-metrics">
      <div>
        <span className="card-metric">{data.duration_label}</span>
        <span className="card-row-sub">durée</span>
      </div>
      <div>
        <span className="card-metric">{data.distance_km} km</span>
        <span className="card-row-sub">{data.mode}</span>
      </div>
    </div>
  );
}

function Media({ data }) {
  return (
    <Rows items={data.items} empty="Rien trouvé.">
      {(it, i) => (
        <li key={i} className="card-row">
          <Icon name="play" size={14} />
          <span className="card-row-main">
            {it.series ? `${it.series} — ${it.name}` : it.name}
            {it.year && <span className="card-row-sub"> · {it.year}</span>}
          </span>
        </li>
      )}
    </Rows>
  );
}

function Contacts({ data }) {
  return (
    <Rows items={data.contacts} empty="Aucun contact.">
      {(c, i) => (
        <li key={i} className="card-row">
          <span className="card-row-main">
            <strong>{c.name}</strong>
            <span className="card-row-sub">
              {" "}
              {(c.phones || []).join(", ") || (c.emails || []).join(", ")}
            </span>
          </span>
        </li>
      )}
    </Rows>
  );
}

function Home({ data }) {
  return (
    <Rows items={data.entities} empty="Aucune entité.">
      {(e, i) => (
        <li key={i} className="card-row">
          <span
            className={`dot ${e.state === "on" || e.state === "home" ? "dot--ok" : ""}`}
            aria-hidden="true"
          />
          <span className="card-row-main">
            {e.name}
            <span className="card-row-sub"> · {e.state}</span>
          </span>
        </li>
      )}
    </Rows>
  );
}

function Weather({ data }) {
  return (
    <div className="card-metrics">
      <div>
        <span className="card-metric">{Math.round(data.temp)}°C</span>
        <span className="card-row-sub">{data.city}</span>
      </div>
      <div>
        <span className="card-metric">{data.wind} km/h</span>
        <span className="card-row-sub">vent</span>
      </div>
    </div>
  );
}

function Meter({ label, value }) {
  return (
    <div className="card-row" style={{ alignItems: "center" }}>
      <span className="card-row-lead">{label}</span>
      <span className="meter meter--wide" aria-hidden="true">
        <span className="meter-fill" style={{ width: `${Math.min(100, value)}%` }} />
      </span>
      <span className="card-row-sub">{value}%</span>
    </div>
  );
}

function Diagnostics({ data }) {
  const hasAgentStats = data.local_rate !== null && data.local_rate !== undefined;
  return (
    <div className="card-prose">
      <Meter label="CPU" value={data.cpu} />
      <Meter label="RAM" value={data.mem} />
      <Meter label="Disque" value={data.disk} />
      <p className="card-row-sub" style={{ marginTop: "var(--sp-2)" }}>
        {data.month_calls} appel{data.month_calls > 1 ? "s" : ""} API ce mois-ci ·{" "}
        {(data.month_cost_usd * 0.92).toFixed(2)} €
      </p>
      {hasAgentStats && (
        <p className="card-row-sub">
          Outils : {data.local_calls} en local · {data.claude_calls} via Claude ({data.local_rate}% local)
        </p>
      )}
    </div>
  );
}

function Fallback({ data }) {
  return <pre className="card-text card-raw">{JSON.stringify(data, null, 1)}</pre>;
}

/** Métadonnées d'affichage par type : icône et libellé de la source. */
export const CARD_META = {
  agenda: { icon: "clock", source: "Agenda" },
  mail: { icon: "chat", source: "Messagerie" },
  mail_detail: { icon: "chat", source: "Message" },
  files: { icon: "copy", source: "Drive" },
  document: { icon: "copy", source: "Document" },
  music: { icon: "play", source: "Spotify" },
  media: { icon: "play", source: "Jellyfin" },
  screenshot: { icon: "camera", source: "Écran" },
  transport: { icon: "clock", source: "Transports" },
  route: { icon: "link", source: "Itinéraire" },
  contacts: { icon: "devices", source: "Contacts" },
  home: { icon: "power", source: "Maison" },
  weather: { icon: "sun", source: "Météo" },
  diagnostics: { icon: "system", source: "Système" },
  file_preview: { icon: "copy", source: "Fichier" },
  web_results: { icon: "search", source: "Recherche web" },
};

export const RENDERERS = {
  agenda: Agenda,
  mail: Mail,
  mail_detail: MailDetail,
  files: Files,
  document: DocumentCard,
  music: Music,
  media: Media,
  screenshot: Screenshot,
  transport: Transport,
  route: Route,
  contacts: Contacts,
  home: Home,
  weather: Weather,
  diagnostics: Diagnostics,
  file_preview: DocumentCard,
  web_results: WebResults,
};

export { Fallback };

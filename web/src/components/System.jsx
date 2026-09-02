import { useState } from "react";
import { ViewHeader } from "./AppShell.jsx";
import CardView from "./cards/CardView.jsx";
import Icon from "./ui/Icon.jsx";
import StatusBadge from "./ui/StatusBadge.jsx";
import { useConfirm } from "./ui/Confirm.jsx";
import { useToast } from "./ui/Toast.jsx";
import { reportAuthFailure } from "../lib/consoleAuth.js";
import { subscribeToPush } from "../lib/usePush.js";
import { useCardHistory, useConversationLog, useMemoryFacts, useModes, useUsage } from "../lib/useSystem.js";
import { useTheme } from "../lib/useTheme.js";
import { formatCountdown, useTimers } from "../lib/useTimers.js";

/**
 * Vue Système : ce que Jarvis coûte, ce qu'il retient, dans quel mode il
 * est, et ce qui s'est dit.
 *
 * Écran entièrement nouveau. Ces quatre choses existaient depuis
 * longtemps dans le brain (data/usage.json, memory.json, modes.json,
 * logs/) mais n'étaient visibles que sur le HUD Qt du PC fixe : depuis
 * un téléphone, impossible de savoir ce que Jarvis avait mémorisé sur
 * vous, ni de changer de mode autrement qu'en le disant à voix haute.
 */

// Un tour de conversation coûte souvent moins d'un centime : arrondir à
// deux décimales afficherait « 0.00 $ » pour tout appel isolé, ce qui
// donne l'impression que le suivi ne marche pas.
const cost = (usd) => {
  const value = usd || 0;
  if (value > 0 && value < 0.01) return `${value.toFixed(4)} $`;
  return `${value.toFixed(2)} $`;
};

function formatNumber(n) {
  return new Intl.NumberFormat("fr-FR").format(n);
}

function Stat({ label, value, sub }) {
  return (
    <div className="card" style={{ gap: "var(--sp-1)" }}>
      <span className="section-label">{label}</span>
      <span style={{ fontFamily: "var(--font-display)", fontSize: "var(--text-xl)" }}>{value}</span>
      {sub && <span className="hint">{sub}</span>}
    </div>
  );
}

function UsageSection() {
  const { usage, error, refresh } = useUsage();

  if (error) {
    return (
      <div className="alert alert--danger" role="alert">
        <Icon name="alert" size={16} />
        Consommation indisponible : {error}
      </div>
    );
  }
  if (!usage) return <p className="hint">Chargement…</p>;

  const current = usage.current || {};
  const history = usage.history || [];
  const peak = Math.max(0.01, ...history.map((h) => h.cost_usd || 0), usage.month_cost_usd || 0);

  return (
    <section className="stack">
      <div className="row">
        <h2 className="section-label spacer">Consommation de l'API Claude</h2>
        <button type="button" className="btn btn--ghost btn--sm" onClick={refresh}>
          <Icon name="refresh" size={15} />
          Actualiser
        </button>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))" }}>
        <Stat label="Ce mois-ci" value={cost(usage.month_cost_usd || 0)} sub={usage.month || "—"} />
        <Stat label="Appels" value={formatNumber(usage.month_calls || 0)} sub="depuis le 1er du mois" />
        <Stat
          label="Tokens"
          value={formatNumber(usage.month_tokens || 0)}
          sub={`dont ${formatNumber(current.cache_read_tokens || 0)} relus en cache`}
        />
        <Stat label="Dernier appel" value={cost(usage.last_cost_usd || 0)} sub="coût du tour précédent" />
      </div>

      {history.length > 0 && (
        <div className="card">
          <span className="section-label">Historique mensuel</span>
          <ul className="stack stack--tight" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {history.map((h) => (
              <li key={h.month} className="row" style={{ gap: "var(--sp-3)", fontSize: "var(--text-sm)" }}>
                <span style={{ width: 68, fontFamily: "var(--font-mono)", color: "var(--text-faint)" }}>
                  {h.month}
                </span>
                <span className="meter meter--wide" aria-hidden="true">
                  <span className="meter-fill" style={{ width: `${((h.cost_usd || 0) / peak) * 100}%` }} />
                </span>
                <span style={{ width: 64, textAlign: "right", fontFamily: "var(--font-mono)" }}>
                  {cost(h.cost_usd || 0)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function ModesSection() {
  const { modes, current, loaded, activate } = useModes();
  const toast = useToast();
  const [busy, setBusy] = useState("");

  async function choose(mode) {
    setBusy(mode.id);
    try {
      await activate(mode.id);
      toast.success(`${mode.name} activé.`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy("");
    }
  }

  if (!loaded) return null;

  return (
    <section className="stack">
      <h2 className="section-label">Mode contextuel</h2>
      <p className="hint">
        Le mode change la façon dont Jarvis répond : sa concision, les sujets qu'il privilégie, le niveau
        de notification. Se change aussi d'un clic en bas de la barre latérale, ou à la voix
        (« passe en mode travail »).
      </p>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
        {modes.map((mode) => {
          const active = current?.mode_id === mode.id;
          return (
            <button
              key={mode.id}
              type="button"
              className={`card card--interactive ${active ? "card--active" : ""}`.trim()}
              style={{ textAlign: "left", cursor: "pointer" }}
              onClick={() => !active && choose(mode)}
              aria-pressed={active}
              disabled={busy !== ""}
            >
              <div className="card-head">
                <span className="card-title spacer">{mode.name}</span>
                {active && <StatusBadge tone="cyan">actif</StatusBadge>}
              </div>
              <span className="hint">{mode.description}</span>
              {mode.focus_topics?.length > 0 && (
                <span className="row row--wrap" style={{ gap: "var(--sp-1)" }}>
                  {mode.focus_topics.slice(0, 4).map((t) => (
                    <span key={t} className="chip">
                      {t}
                    </span>
                  ))}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </section>
  );
}

/** Minuteurs & rappels (C1) — jusqu'ici uniquement pilotables à la voix
 * sur le PC fixe (agents/desktop/services/timers.py), invisibles du web.
 * brain/timers.py porte maintenant sa propre liste, commune à toutes les
 * Consoles ; celle du desktop reste séparée et continue de fonctionner
 * sans réseau (voir brain/timers.py, docstring). */
function TimersSection() {
  const { timers, create, cancel } = useTimers();
  const [duration, setDuration] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const toast = useToast();

  async function submit(e) {
    e.preventDefault();
    if (!duration.trim()) return;
    // Geste utilisateur explicite : le bon moment pour demander la
    // permission de notification, pas au chargement de la page.
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      const permission = await Notification.requestPermission();
      // S'abonne aussi au Web Push (C12) : sans ça, un minuteur ne sonne
      // que si l'onglet de la Console est resté ouvert au premier plan.
      if (permission === "granted") subscribeToPush();
    } else if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      subscribeToPush();
    }
    setBusy(true);
    setError("");
    try {
      await create(duration.trim(), label.trim());
      setDuration("");
      setLabel("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel(id) {
    try {
      await cancel(id);
    } catch (err) {
      toast.error(err.message);
    }
  }

  return (
    <section className="stack">
      <h2 className="section-label">Minuteurs & rappels</h2>
      <p className="hint" style={{ maxWidth: 640 }}>
        Se posent aussi à la voix (« minuteur cinq minutes », « rappelle-moi d'appeler maman dans vingt
        minutes ») — depuis n'importe quel appareil, ici comme sur le PC fixe. Le compte à rebours du
        prochain minuteur s'affiche en permanence dans le bandeau du pupitre.
      </p>

      <form className="memory-add" onSubmit={submit}>
        <div className="field">
          <label className="label" htmlFor="timer-duration">
            Durée
          </label>
          <input
            id="timer-duration"
            className="input"
            value={duration}
            placeholder="5 minutes, 1h30…"
            onChange={(e) => setDuration(e.target.value)}
          />
        </div>
        <div className="field spacer">
          <label className="label" htmlFor="timer-label">
            Rappel (facultatif)
          </label>
          <input
            id="timer-label"
            className="input"
            value={label}
            placeholder="appeler maman"
            onChange={(e) => setLabel(e.target.value)}
          />
        </div>
        <button type="submit" className="btn btn--primary" disabled={busy || !duration.trim()}>
          <Icon name="plus" size={16} />
          Lancer
        </button>
      </form>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}

      {timers.length === 0 ? (
        <p className="hint">Aucun minuteur actif.</p>
      ) : (
        <ul className="fact-list">
          {timers.map((t) => (
            <li key={t.id} className="fact">
              <span className="fact-text">
                {t.kind === "reminder" && t.label ? t.label : "Minuteur"}
                <span className="hint" style={{ marginLeft: "var(--sp-2)", fontFamily: "var(--font-mono)" }}>
                  {formatCountdown(t.remaining)}
                </span>
              </span>
              <button
                type="button"
                className="icon-btn icon-btn--sm"
                onClick={() => handleCancel(t.id)}
                aria-label={`Annuler : ${t.label || "minuteur"}`}
                title="Annuler"
              >
                <Icon name="trash" size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// Aperçu de l'accent de chaque thème — mêmes teintes que styles/tokens.css
// (:root[data-theme="…"] { --cyan: … }), dupliquées ici en dur : un swatch
// doit rester visible même pour le thème qui n'est pas actif, donc on ne
// peut pas lire la variable CSS calculée (elle ne vaut que pour le DOM
// actuellement dans cet état).
const THEME_SWATCHES = {
  default: "oklch(0.86 0.13 210)",
  mark42: "oklch(0.78 0.16 40)",
  warmachine: "oklch(0.82 0.025 250)",
  vision: "oklch(0.78 0.15 320)",
};

function ThemeSection() {
  const { theme, setTheme, themes } = useTheme();

  return (
    <section className="stack">
      <h2 className="section-label">Thème</h2>
      <p className="hint">
        L'identité visuelle du pupitre et de la Console. Se change aussi depuis n'importe quel appareil —
        c'est une préférence locale, pas un réglage synchronisé.
      </p>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))" }}>
        {themes.map((t) => {
          const active = theme === t.id;
          return (
            <button
              key={t.id}
              type="button"
              className={`card card--interactive ${active ? "card--active" : ""}`.trim()}
              style={{ textAlign: "left", cursor: "pointer" }}
              onClick={() => !active && setTheme(t.id)}
              aria-pressed={active}
            >
              <div className="card-head">
                <span
                  className="dot"
                  aria-hidden="true"
                  style={{
                    marginTop: 3,
                    background: THEME_SWATCHES[t.id],
                    boxShadow: `0 0 8px ${THEME_SWATCHES[t.id]}`,
                  }}
                />
                <span className="card-title spacer">{t.name}</span>
                {active && <StatusBadge tone="cyan">actif</StatusBadge>}
              </div>
              <span className="hint">{t.description}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

// Limites imposées par le brain (brain/core/memory.py::clean_fact et
// save) : un fait fait au plus 80 caractères, et seuls les 80 derniers
// sont conservés. Écrites ici pour que Monsieur les voie avant de se les
// prendre en pleine figure sous forme d'erreur 400.
const FACT_MAX_LENGTH = 80;
const FACT_MAX_COUNT = 80;

/** Une ligne de mémoire, éditable sur place. Corriger une faute de frappe
 * imposait auparavant de supprimer le fait puis de le retaper de tête. */
function FactRow({ fact, index, onUpdate, onForget }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(fact);
  const [busy, setBusy] = useState(false);

  async function save(e) {
    e.preventDefault();
    const value = draft.trim();
    if (!value || value === fact) {
      setEditing(false);
      setDraft(fact);
      return;
    }
    setBusy(true);
    try {
      await onUpdate(index, value);
      setEditing(false);
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return (
      <li className="fact fact--editing">
        <form className="row" onSubmit={save} style={{ width: "100%" }}>
          <label className="sr-only" htmlFor={`fact-${index}`}>
            Modifier ce fait
          </label>
          <input
            id={`fact-${index}`}
            className="input"
            autoFocus
            maxLength={FACT_MAX_LENGTH}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setEditing(false);
                setDraft(fact);
              }
            }}
          />
          <button type="submit" className="btn btn--primary btn--sm" disabled={busy}>
            Enregistrer
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => {
              setEditing(false);
              setDraft(fact);
            }}
          >
            Annuler
          </button>
        </form>
      </li>
    );
  }

  return (
    <li className="fact">
      <span className="fact-text">{fact}</span>
      <button
        type="button"
        className="icon-btn icon-btn--sm"
        onClick={() => setEditing(true)}
        aria-label={`Modifier : ${fact}`}
        title="Modifier"
      >
        <Icon name="pencil" size={14} />
      </button>
      <button
        type="button"
        className="icon-btn icon-btn--sm"
        onClick={() => onForget(fact, index)}
        aria-label={`Oublier : ${fact}`}
        title="Oublier"
      >
        <Icon name="trash" size={14} />
      </button>
    </li>
  );
}

function MemorySection() {
  const { facts, lastUpdated, loaded, add, update, remove } = useMemoryFacts();
  const confirm = useConfirm();
  const toast = useToast();
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // `last_updated` est un timestamp Unix stocké en chaîne par
  // brain/core/memory.py — pas une date ISO, d'où la conversion.
  const seconds = Number.parseFloat(lastUpdated);
  const updatedAt = Number.isFinite(seconds)
    ? new Date(seconds * 1000).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })
    : "";

  async function submit(e) {
    e.preventDefault();
    const fact = draft.trim();
    if (!fact) return;
    setBusy(true);
    setError("");
    try {
      const data = await add(fact);
      toast.success(data.added ? "Fait mémorisé." : "Ce fait était déjà connu.");
      setDraft("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdate(index, fact) {
    try {
      await update(index, fact);
      toast.success("Fait corrigé.");
    } catch (err) {
      toast.error(err.message);
    }
  }

  async function forget(fact, index) {
    const ok = await confirm({
      title: "Oublier ce fait ?",
      message: `« ${fact} » sera retiré de la mémoire longue durée de Jarvis, et ne sera plus pris en compte dans ses réponses.`,
      confirmLabel: "Oublier",
    });
    if (!ok) return;
    await remove(index);
    toast.success("Fait oublié.");
  }

  // L'index d'origine doit voyager avec le fait : c'est lui que l'API
  // attend, et il ne correspond plus à la position affichée dès qu'un
  // filtre est saisi.
  const entries = facts.map((fact, index) => ({ fact, index }));
  const needle = query.trim().toLowerCase();
  const shown = needle ? entries.filter((e) => e.fact.toLowerCase().includes(needle)) : entries;
  const remaining = FACT_MAX_LENGTH - draft.length;

  return (
    <section className="stack">
      <div className="row">
        <h2 className="section-label spacer">Mémoire longue durée</h2>
        <StatusBadge tone={facts.length >= FACT_MAX_COUNT ? "warn" : "neutral"}>
          {facts.length} / {FACT_MAX_COUNT}
        </StatusBadge>
      </div>

      <p className="hint" style={{ maxWidth: 640 }}>
        Ce que Jarvis retient de vous entre deux conversations, et rappelle à chacune de ses réponses. Les
        faits s'ajoutent d'eux-mêmes au fil des échanges, ou à la demande (« mémorise que… »).
        {updatedAt && ` Dernière modification le ${updatedAt}.`}
      </p>

      <form className="memory-add" onSubmit={submit}>
        <div className="field spacer">
          <label className="label" htmlFor="fact-input">
            Ajouter un fait
          </label>
          <input
            id="fact-input"
            className="input"
            value={draft}
            maxLength={FACT_MAX_LENGTH}
            placeholder="préfère les réponses courtes"
            onChange={(e) => setDraft(e.target.value)}
            aria-describedby="fact-counter"
          />
          <span className="hint" id="fact-counter">
            {remaining} caractère{remaining > 1 ? "s" : ""} restant{remaining > 1 ? "s" : ""} · une phrase
            courte et durable, pas une consigne ponctuelle
          </span>
        </div>
        <button type="submit" className="btn btn--primary" disabled={busy || !draft.trim()}>
          <Icon name="plus" size={16} />
          Mémoriser
        </button>
      </form>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}

      {facts.length > 6 && (
        <div className="field">
          <label className="sr-only" htmlFor="fact-search">
            Filtrer les faits
          </label>
          <input
            id="fact-search"
            className="input"
            type="search"
            value={query}
            placeholder="Filtrer…"
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      )}

      {loaded && facts.length === 0 ? (
        <p className="hint">
          Rien en mémoire pour l'instant. Jarvis vous répondra sans rien savoir de vos habitudes.
        </p>
      ) : shown.length === 0 ? (
        <p className="hint">Aucun fait ne correspond à « {query} ».</p>
      ) : (
        <ul className="fact-list">
          {shown.map(({ fact, index }) => (
            <FactRow
              key={`${index}-${fact}`}
              fact={fact}
              index={index}
              onUpdate={handleUpdate}
              onForget={forget}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

/** Champs de recherche (C8) partagés entre le journal de conversation et
 * l'historique des affichages — mot-clé + période, chacun facultatif.
 * `onSearch` reçoit {query, since, until} ; un formulaire vide équivaut à
 * `onReset` (retour à la liste brute, ordre chronologique habituel). */
function SearchFields({ onSearch, onReset, placeholder }) {
  const [query, setQuery] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");

  function submit(e) {
    e.preventDefault();
    if (!query.trim() && !since && !until) {
      onReset();
      return;
    }
    onSearch({ query: query.trim(), since, until });
  }

  function reset() {
    setQuery("");
    setSince("");
    setUntil("");
    onReset();
  }

  return (
    <form className="row row--wrap" style={{ gap: "var(--sp-2)" }} onSubmit={submit}>
      <input
        className="input"
        type="search"
        value={query}
        placeholder={placeholder}
        onChange={(e) => setQuery(e.target.value)}
        style={{ flex: "1 1 200px" }}
      />
      <input
        className="input"
        type="date"
        value={since}
        onChange={(e) => setSince(e.target.value)}
        aria-label="Depuis"
        style={{ flex: "0 1 150px" }}
      />
      <input
        className="input"
        type="date"
        value={until}
        onChange={(e) => setUntil(e.target.value)}
        aria-label="Jusqu'au"
        style={{ flex: "0 1 150px" }}
      />
      <button type="submit" className="btn btn--sm">
        <Icon name="search" size={15} />
        Chercher
      </button>
      {(query || since || until) && (
        <button type="button" className="btn btn--ghost btn--sm" onClick={reset}>
          Réinitialiser
        </button>
      )}
    </form>
  );
}

function LogSection() {
  const { entries, loaded, refresh, search } = useConversationLog(60);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);

  async function runSearch(params) {
    await search(params);
    setSearching(true);
    setOpen(true);
  }

  async function reset() {
    setSearching(false);
    await refresh();
  }

  // search() renvoie déjà le plus récent d'abord (pertinent pour des
  // résultats de recherche) ; refresh() renvoie le plus ancien d'abord
  // (pour reconstruire un fil) — d'où l'inversion conditionnelle ici.
  const shown = searching ? entries : [...entries].reverse();

  return (
    <section className="stack">
      <div className="row">
        <h2 className="section-label spacer">Journal des conversations</h2>
        <button type="button" className="btn btn--ghost btn--sm" onClick={reset} disabled={!loaded}>
          <Icon name="refresh" size={15} />
          Actualiser
        </button>
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          {open ? "Masquer" : `Afficher (${entries.length})`}
        </button>
      </div>

      {open && (
        <>
          <SearchFields onSearch={runSearch} onReset={reset} placeholder="Chercher dans les échanges…" />

          {shown.length === 0 ? (
            <p className="hint">{searching ? "Aucun résultat." : "Aucun échange journalisé."}</p>
          ) : (
            <ul className="stack stack--tight" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {shown.map((e, i) => (
                <li key={i} className="card" style={{ gap: "var(--sp-2)" }}>
                  <span className="hint" style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}>
                    {e.at?.replace("T", " ") || ""}
                    {e.source ? ` · ${e.source}` : ""}
                  </span>
                  <span style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>{e.question}</span>
                  <span style={{ fontSize: "var(--text-sm)" }}>{e.answer}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

/** Historique des cartes, au-delà des 30 dernières que le pupitre garde en
 * mémoire vive — lecture seule (pas de bouton écarter, ni d'actions : ce
 * sont des instantanés passés, agir dessus n'aurait pas de sens). */
function CardHistorySection() {
  const { entries, loaded, refresh, search } = useCardHistory(100);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);

  async function runSearch(params) {
    await search(params);
    setSearching(true);
    setOpen(true);
  }

  async function reset() {
    setSearching(false);
    await refresh();
  }

  const shown = searching ? entries : [...entries].reverse();

  return (
    <section className="stack">
      <div className="row">
        <h2 className="section-label spacer">Historique des affichages</h2>
        <button type="button" className="btn btn--ghost btn--sm" onClick={reset} disabled={!loaded}>
          <Icon name="refresh" size={15} />
          Actualiser
        </button>
        <button type="button" className="btn btn--sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? "Masquer" : `Afficher (${entries.length})`}
        </button>
      </div>
      <p className="hint" style={{ maxWidth: 640 }}>
        Les cartes (agenda, mails, capture d'écran…) que Jarvis a affichées, au-delà des 30 dernières
        conservées en mémoire. Les captures d'écran y perdent leur image — jamais écrite sur disque.
      </p>

      {open && (
        <>
          <SearchFields onSearch={runSearch} onReset={reset} placeholder="Chercher par titre, sous-titre, type…" />

          {shown.length === 0 ? (
            <p className="hint">{searching ? "Aucun résultat." : "Aucune carte journalisée."}</p>
          ) : (
            <div className="hud-deck-grid">
              {shown.map((card) => (
                <CardView key={card.id} card={card} readOnly />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}

export default function System() {
  const confirm = useConfirm();

  async function logout() {
    const ok = await confirm({
      title: "Se déconnecter de la Console ?",
      message: "Le mot de passe sera oublié sur cet appareil et vous devrez le ressaisir.",
      confirmLabel: "Se déconnecter",
    });
    if (ok) reportAuthFailure();
  }

  return (
    <>
      <ViewHeader title="Système" subtitle="Coûts, mémoire, mode et journal" />
      <div className="view-body">
        <div className="view-main">
          <div className="stack" style={{ gap: "var(--sp-8)", maxWidth: "var(--content-max)" }}>
            <UsageSection />
            <TimersSection />
            <ThemeSection />
            <ModesSection />
            <MemorySection />
            <LogSection />
            <CardHistorySection />

            <section className="stack">
              <h2 className="section-label">Session</h2>
              <div className="row">
                <p className="hint spacer">
                  Le mot de passe de la Console est conservé dans ce navigateur pour éviter de le ressaisir à
                  chaque visite.
                </p>
                <button type="button" className="btn btn--danger btn--sm" onClick={logout}>
                  <Icon name="power" size={15} />
                  Se déconnecter
                </button>
              </div>
            </section>
          </div>
        </div>
      </div>
    </>
  );
}

import { useMemo, useState } from "react";
import { ViewHeader } from "./AppShell.jsx";
import Icon from "./ui/Icon.jsx";
import { useNotes } from "../lib/useSystem.js";

/**
 * Vue Notes (C2) — le carnet de « prends note que… », jusqu'ici écrit
 * uniquement à la voix sur le PC fixe (agents/desktop/services/notes.py)
 * et jamais relisible ailleurs : ni vue, ni recherche, aucune route côté
 * brain. brain/notes.py lit/écrit les mêmes fichiers Markdown
 * (data/notes/notes-AAAA-MM-JJ.md) — une note prise ici apparaît donc
 * aussi dans le carnet du PC fixe, et réciproquement.
 */

function dateLabel(iso) {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

/** Regroupe la liste (déjà la plus récente d'abord) par jour, sans casser
 * l'ordre — chaque note garde sa place dans son groupe. */
function groupByDate(notes) {
  const groups = [];
  let current = null;
  for (const note of notes) {
    if (!current || current.date !== note.date) {
      current = { date: note.date, entries: [] };
      groups.push(current);
    }
    current.entries.push(note);
  }
  return groups;
}

export default function Notes() {
  const { notes, loaded, add } = useNotes();
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setBusy(true);
    setError("");
    try {
      await add(text);
      setDraft("");
    } catch (err) {
      setError(err.message || "échec de l'enregistrement");
    } finally {
      setBusy(false);
    }
  }

  const needle = query.trim().toLowerCase();
  const shown = useMemo(
    () => (needle ? notes.filter((n) => n.text.toLowerCase().includes(needle)) : notes),
    [notes, needle],
  );
  const groups = useMemo(() => groupByDate(shown), [shown]);

  return (
    <>
      <ViewHeader title="Notes" subtitle="« Prends note que… », consultable partout" />
      <div className="view-body">
        <div className="view-main">
          <div className="stack" style={{ gap: "var(--sp-6)", maxWidth: "var(--content-max)" }}>
            <form className="memory-add" onSubmit={submit}>
              <div className="field spacer">
                <label className="label" htmlFor="note-input">
                  Nouvelle note
                </label>
                <input
                  id="note-input"
                  className="input"
                  value={draft}
                  placeholder="acheter du café, rappeler le plombier…"
                  onChange={(e) => setDraft(e.target.value)}
                />
              </div>
              <button type="submit" className="btn btn--primary" disabled={busy || !draft.trim()}>
                <Icon name="plus" size={16} />
                Noter
              </button>
            </form>
            {error && (
              <p className="field-error" role="alert">
                {error}
              </p>
            )}

            {notes.length > 6 && (
              <div className="field">
                <label className="sr-only" htmlFor="note-search">
                  Chercher dans les notes
                </label>
                <input
                  id="note-search"
                  className="input"
                  type="search"
                  value={query}
                  placeholder="Chercher…"
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
            )}

            {loaded && notes.length === 0 ? (
              <p className="hint">Aucune note pour l'instant. Dites « Jarvis, prends note que… ».</p>
            ) : shown.length === 0 ? (
              <p className="hint">Aucune note ne correspond à « {query} ».</p>
            ) : (
              <div className="stack" style={{ gap: "var(--sp-5)" }}>
                {groups.map((group) => (
                  <section key={group.date} className="stack stack--tight">
                    <h2 className="section-label">{dateLabel(group.date)}</h2>
                    <ul className="fact-list">
                      {group.entries.map((n, i) => (
                        <li key={`${group.date}-${i}`} className="fact">
                          <span
                            className="hint"
                            style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", flex: "none" }}
                          >
                            {n.time}
                          </span>
                          <span className="fact-text">{n.text}</span>
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

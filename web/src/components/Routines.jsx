import { useState } from "react";
import { ViewHeader } from "./AppShell.jsx";
import EmptyState from "./ui/EmptyState.jsx";
import Icon from "./ui/Icon.jsx";
import Modal from "./ui/Modal.jsx";
import StatusBadge from "./ui/StatusBadge.jsx";
import { SelectField, TextField } from "./ui/Field.jsx";
import { useConfirm } from "./ui/Confirm.jsx";
import { useToast } from "./ui/Toast.jsx";
import { useDevices } from "../lib/useDevices.js";
import { useRoutines } from "../lib/useRoutines.js";

// Set volontairement restreint et curaté (pas de console PowerShell libre
// dans le builder) — même logique de prudence que Focus.jsx : une routine
// s'exécute d'un clic, sans confirmation étape par étape, donc pas de
// commande arbitraire ici.
const STEP_KINDS = [
  { id: "capture", label: "Capturer l'écran", tool: "take_screenshot", icon: "camera" },
  {
    id: "lock",
    label: "Verrouiller la session",
    tool: "run_powershell",
    icon: "lock",
    args: { command: "rundll32.exe user32.dll,LockWorkStation" },
  },
  { id: "open_url", label: "Ouvrir une page web", tool: "open_url", icon: "link", needsUrl: true },
];

/** Une étape enregistrée ne garde que `tool` + `args` : on retrouve son
 * libellé lisible ici, sinon les cartes affichent « run_powershell ». */
function stepLabel(step) {
  if (step.tool === "open_url") return `Ouvrir ${step.args?.url || "une page"}`;
  const kind = STEP_KINDS.find((k) => k.tool === step.tool);
  return kind ? kind.label : step.tool;
}

// 0 = lundi, comme time.localtime().tm_wday côté brain (routines.py) — pas
// dimanche-premier, pour ne pas avoir à traduire dans les deux sens.
const DAYS = [
  { v: 0, label: "Lu" },
  { v: 1, label: "Ma" },
  { v: 2, label: "Me" },
  { v: 3, label: "Je" },
  { v: 4, label: "Ve" },
  { v: 5, label: "Sa" },
  { v: 6, label: "Di" },
];

function scheduleSummary(schedule) {
  if (!schedule) return "Déclenchement manuel";
  const days = schedule.days;
  if (!days || days.length === 0 || days.length === 7) return `Tous les jours à ${schedule.time}`;
  return `${days.map((d) => DAYS.find((x) => x.v === d)?.label).join(" ")} à ${schedule.time}`;
}

/** Éditeur de programmation (C4) : une case à cocher, une heure, des jours
 * — partagé entre le formulaire de création et l'édition sur une routine
 * déjà enregistrée, seul le bouton d'enregistrement change autour de lui. */
function ScheduleFields({ enabled, onToggleEnabled, time, onTime, days, onToggleDay }) {
  return (
    <section className="stack stack--tight">
      <label className="row" style={{ gap: "var(--sp-2)", cursor: "pointer" }}>
        <input type="checkbox" checked={enabled} onChange={(e) => onToggleEnabled(e.target.checked)} />
        <span>Déclenchement automatique</span>
      </label>
      {enabled && (
        <>
          <TextField
            label="Heure"
            type="time"
            value={time}
            onChange={(e) => onTime(e.target.value)}
            required
          />
          <div className="row row--wrap" style={{ gap: "var(--sp-1)" }}>
            {DAYS.map((d) => (
              <button
                key={d.v}
                type="button"
                className={`chip ${days.includes(d.v) ? "chip--active" : ""}`.trim()}
                aria-pressed={days.includes(d.v)}
                onClick={() => onToggleDay(d.v)}
              >
                {d.label}
              </button>
            ))}
          </div>
          <p className="hint">Aucun jour coché = tous les jours.</p>
        </>
      )}
    </section>
  );
}

/** Programmation d'une routine déjà enregistrée — repliée par défaut, pour
 * ne pas alourdir chaque carte quand la routine reste manuelle (le cas
 * courant aujourd'hui). */
function ScheduleEditor({ routine, onSave }) {
  const [open, setOpen] = useState(false);
  const [enabled, setEnabled] = useState(Boolean(routine.schedule));
  const [time, setTime] = useState(routine.schedule?.time || "08:00");
  const [days, setDays] = useState(routine.schedule?.days || []);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  function toggleDay(v) {
    setDays((prev) => (prev.includes(v) ? prev.filter((d) => d !== v) : [...prev, v].sort()));
  }

  async function save() {
    setBusy(true);
    try {
      await onSave(enabled ? { time, days } : null);
      toast.success(enabled ? "Programmation enregistrée." : "Retour au déclenchement manuel.");
      setOpen(false);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className="btn btn--ghost btn--sm" onClick={() => setOpen(true)}>
        <Icon name="clock" size={15} />
        {scheduleSummary(routine.schedule)}
      </button>
    );
  }

  return (
    <div
      className="stack stack--tight"
      style={{ padding: "var(--sp-3)", border: "1px dashed var(--line-strong)", borderRadius: "var(--r-md)" }}
    >
      <ScheduleFields
        enabled={enabled}
        onToggleEnabled={setEnabled}
        time={time}
        onTime={setTime}
        days={days}
        onToggleDay={toggleDay}
      />
      <div className="row" style={{ gap: "var(--sp-2)" }}>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setOpen(false)} disabled={busy}>
          Annuler
        </button>
        <button
          type="button"
          className="btn btn--primary btn--sm"
          onClick={save}
          disabled={busy || (enabled && !time)}
        >
          Enregistrer
        </button>
      </div>
    </div>
  );
}

function RoutineCard({ routine, devices, onRun, onDelete, onSchedule }) {
  const run = routine.run_status;
  const running = run?.status === "running";
  const failed = run?.status === "error";
  const deviceName = (id) => devices.find((d) => d.device_id === id)?.name || "appareil inconnu";

  return (
    <div className={`card ${running ? "card--active" : ""}`.trim()}>
      <div className="card-head">
        <div className="spacer">
          <h2 className="card-title">{routine.name}</h2>
          <span className="card-sub">
            {routine.steps.length} étape{routine.steps.length > 1 ? "s" : ""}
          </span>
        </div>
        {running && (
          <StatusBadge tone="cyan" pulse>
            étape {run.step_index + 1} / {run.total}
          </StatusBadge>
        )}
        {failed && <StatusBadge tone="danger">échec</StatusBadge>}
        {run?.status === "done" && !running && <StatusBadge tone="ok">terminée</StatusBadge>}
      </div>

      {failed && (
        <div className="alert alert--danger" role="alert">
          <Icon name="alert" size={16} />
          {run.error || "une étape a échoué"}
        </div>
      )}

      <ol className="stack stack--tight" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {routine.steps.map((step, i) => (
          <li key={i} className="row" style={{ gap: "var(--sp-2)", fontSize: "var(--text-sm)" }}>
            <span className="chip" style={{ minWidth: 26, justifyContent: "center" }}>
              {i + 1}
            </span>
            <span className="spacer">
              {stepLabel(step)} <span className="hint">· {deviceName(step.device_id)}</span>
            </span>
          </li>
        ))}
      </ol>

      <ScheduleEditor routine={routine} onSave={(schedule) => onSchedule(routine, schedule)} />

      <div className="card-actions">
        <button type="button" className="btn btn--danger btn--sm" onClick={() => onDelete(routine)}>
          <Icon name="trash" size={15} />
          Supprimer
        </button>
        <button type="button" className="btn btn--accent btn--sm" onClick={() => onRun(routine)} disabled={running}>
          <Icon name="play" size={15} />
          {running ? "En cours…" : "Lancer"}
        </button>
      </div>
    </div>
  );
}

function BuilderDialog({ open, onClose, devices, onCreate }) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [steps, setSteps] = useState([]);
  const [kind, setKind] = useState(STEP_KINDS[0].id);
  const [deviceId, setDeviceId] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [scheduleTime, setScheduleTime] = useState("08:00");
  const [scheduleDays, setScheduleDays] = useState([]);

  const currentKind = STEP_KINDS.find((k) => k.id === kind);

  function toggleScheduleDay(v) {
    setScheduleDays((prev) => (prev.includes(v) ? prev.filter((d) => d !== v) : [...prev, v].sort()));
  }

  function reset() {
    setName("");
    setSteps([]);
    setKind(STEP_KINDS[0].id);
    setDeviceId("");
    setUrl("");
    setError("");
    setScheduleEnabled(false);
    setScheduleTime("08:00");
    setScheduleDays([]);
  }

  function addStep() {
    if (!deviceId) {
      setError("Choisissez l'appareil qui exécutera cette étape.");
      return;
    }
    if (currentKind.needsUrl && !url.trim()) {
      setError("Indiquez l'adresse de la page à ouvrir.");
      return;
    }
    setError("");
    setSteps((prev) => [
      ...prev,
      {
        device_id: deviceId,
        tool: currentKind.tool,
        args: currentKind.needsUrl ? { url: url.trim() } : currentKind.args || {},
      },
    ]);
    setUrl("");
  }

  function move(index, delta) {
    setSteps((prev) => {
      const next = [...prev];
      const target = index + delta;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      const schedule = scheduleEnabled ? { time: scheduleTime, days: scheduleDays } : null;
      await onCreate(name.trim(), steps, schedule);
      toast.success(`Routine « ${name.trim()} » enregistrée.`);
      reset();
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const deviceName = (id) => devices.find((d) => d.device_id === id)?.name || id;

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title="Nouvelle routine"
      description="Une suite d'actions déclenchées d'un seul clic, éventuellement sur plusieurs appareils."
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Annuler
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={save}
            disabled={busy || !name.trim() || steps.length === 0}
          >
            {busy && <span className="spinner" aria-hidden="true" />}
            Enregistrer
          </button>
        </>
      }
    >
      {devices.length === 0 && (
        <div className="alert alert--warn">
          <Icon name="alert" size={16} />
          Aucun appareil appairé : une routine a besoin d'au moins un appareil pour s'exécuter.
        </div>
      )}

      <TextField
        label="Nom de la routine"
        placeholder="Fin de journée"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />

      <section className="stack stack--tight">
        <h3 className="section-label">Étapes</h3>
        {steps.length === 0 ? (
          <p className="hint">Aucune étape pour l'instant. Ajoutez-en au moins une ci-dessous.</p>
        ) : (
          <ol className="stack stack--tight" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {steps.map((s, i) => (
              <li
                key={i}
                className="row"
                style={{
                  gap: "var(--sp-2)",
                  padding: "var(--sp-2) var(--sp-3)",
                  border: "1px solid var(--line)",
                  borderRadius: "var(--r-md)",
                  background: "var(--surface-2)",
                }}
              >
                <span className="chip" style={{ minWidth: 26, justifyContent: "center" }}>
                  {i + 1}
                </span>
                <span className="spacer" style={{ fontSize: "var(--text-sm)" }}>
                  {stepLabel(s)} <span className="hint">· {deviceName(s.device_id)}</span>
                </span>
                <button
                  type="button"
                  className="icon-btn icon-btn--sm"
                  onClick={() => move(i, -1)}
                  disabled={i === 0}
                  aria-label={`Monter l'étape ${i + 1}`}
                >
                  <Icon name="chevron" size={14} strokeWidth={2} className="rot-up" />
                </button>
                <button
                  type="button"
                  className="icon-btn icon-btn--sm"
                  onClick={() => move(i, 1)}
                  disabled={i === steps.length - 1}
                  aria-label={`Descendre l'étape ${i + 1}`}
                >
                  <Icon name="chevron" size={14} strokeWidth={2} className="rot-down" />
                </button>
                <button
                  type="button"
                  className="icon-btn icon-btn--sm"
                  onClick={() => setSteps((prev) => prev.filter((_, idx) => idx !== i))}
                  aria-label={`Retirer l'étape ${i + 1}`}
                >
                  <Icon name="x" size={14} />
                </button>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section
        className="stack stack--tight"
        style={{
          padding: "var(--sp-4)",
          border: "1px dashed var(--line-strong)",
          borderRadius: "var(--r-md)",
        }}
      >
        <h3 className="section-label">Ajouter une étape</h3>
        <SelectField label="Appareil" value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
          <option value="">Choisir…</option>
          {devices.map((d) => (
            <option key={d.device_id} value={d.device_id}>
              {d.name}
              {d.status === "online" ? "" : " (hors ligne)"}
            </option>
          ))}
        </SelectField>
        <SelectField label="Action" value={kind} onChange={(e) => setKind(e.target.value)}>
          {STEP_KINDS.map((k) => (
            <option key={k.id} value={k.id}>
              {k.label}
            </option>
          ))}
        </SelectField>
        {currentKind?.needsUrl && (
          <TextField label="Adresse" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
        )}
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
        <button type="button" className="btn" onClick={addStep} disabled={devices.length === 0}>
          <Icon name="plus" size={16} />
          Ajouter cette étape
        </button>
      </section>

      <ScheduleFields
        enabled={scheduleEnabled}
        onToggleEnabled={setScheduleEnabled}
        time={scheduleTime}
        onTime={setScheduleTime}
        days={scheduleDays}
        onToggleDay={toggleScheduleDay}
      />
    </Modal>
  );
}

export default function Routines() {
  const { routines, create, remove, run, setSchedule } = useRoutines();
  const { devices } = useDevices();
  const confirm = useConfirm();
  const toast = useToast();
  const [builderOpen, setBuilderOpen] = useState(false);

  async function handleDelete(routine) {
    const ok = await confirm({
      title: `Supprimer « ${routine.name} » ?`,
      message: "La routine et ses étapes seront perdues. Cette action est définitive.",
      confirmLabel: "Supprimer",
    });
    if (!ok) return;
    await remove(routine.id);
    toast.success("Routine supprimée.");
  }

  async function handleRun(routine) {
    await run(routine.id);
    toast.info(`« ${routine.name} » lancée.`);
  }

  async function handleSchedule(routine, schedule) {
    await setSchedule(routine.id, schedule);
  }

  return (
    <>
      <ViewHeader
        title="Routines"
        subtitle={
          routines.length === 0
            ? "Enchaînements d'actions sur vos appareils"
            : `${routines.length} routine${routines.length > 1 ? "s" : ""}`
        }
        actions={
          <button type="button" className="btn btn--primary btn--sm" onClick={() => setBuilderOpen(true)}>
            <Icon name="plus" size={16} />
            Nouvelle routine
          </button>
        }
      />

      <div className="view-body">
        <div className="view-main">
          {routines.length === 0 ? (
            <EmptyState
              icon="routines"
              title="Aucune routine"
              text="Une routine enchaîne plusieurs actions d'un seul clic — par exemple : capturer l'écran du PC fixe, puis verrouiller le portable."
              action={
                <button type="button" className="btn btn--primary" onClick={() => setBuilderOpen(true)}>
                  <Icon name="plus" size={16} />
                  Créer une routine
                </button>
              }
            />
          ) : (
            <div className="grid">
              {routines.map((r) => (
                <RoutineCard
                  key={r.id}
                  routine={r}
                  devices={devices}
                  onRun={handleRun}
                  onDelete={handleDelete}
                  onSchedule={handleSchedule}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      <BuilderDialog
        open={builderOpen}
        onClose={() => setBuilderOpen(false)}
        devices={devices}
        onCreate={create}
      />
    </>
  );
}

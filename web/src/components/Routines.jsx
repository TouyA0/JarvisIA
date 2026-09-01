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

function RoutineCard({ routine, devices, onRun, onDelete }) {
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

  const currentKind = STEP_KINDS.find((k) => k.id === kind);

  function reset() {
    setName("");
    setSteps([]);
    setKind(STEP_KINDS[0].id);
    setDeviceId("");
    setUrl("");
    setError("");
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
      await onCreate(name.trim(), steps);
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
    </Modal>
  );
}

export default function Routines() {
  const { routines, create, remove, run } = useRoutines();
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
                <RoutineCard key={r.id} routine={r} devices={devices} onRun={handleRun} onDelete={handleDelete} />
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

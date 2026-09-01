import Icon from "./ui/Icon.jsx";
import Modal from "./ui/Modal.jsx";
import { useConfirmations } from "../lib/useConfirmations.js";

// Montée au niveau App.jsx (pas dans un panneau précis) : une confirmation
// d'écriture Drive peut arriver pendant que Monsieur regarde n'importe
// quelle vue de la Console, elle doit rester visible partout. Miroir web de
// la bulle Qt bloquante du HUD desktop (agents/desktop/ui/dialogs.py) —
// voir brain/integrations/confirm.py pour le mécanisme côté brain.
//
// Rendu via le Modal existant (focus déplacé/piégé, Échap, aria-modal) —
// le canal de polling/résolution reste séparé côté brain, seul le rendu
// change. On n'affiche que la première confirmation en attente ; les
// suivantes de la file apparaissent une fois celle-ci résolue. Échap ou
// clic sur le voile équivaut à Refuser, comme le bouton de fermeture.
export default function ConfirmationBanner() {
  const { pending, resolve } = useConfirmations();

  if (pending.length === 0) return null;

  const current = pending[0];

  return (
    <Modal
      open
      onClose={() => resolve(current.id, false)}
      title="Confirmation requise"
      footer={
        <>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => resolve(current.id, false)}>
            <Icon name="x" size={15} />
            Refuser
          </button>
          <button type="button" className="btn btn--primary btn--sm" onClick={() => resolve(current.id, true)}>
            <Icon name="check" size={15} />
            Confirmer
          </button>
        </>
      }
    >
      <p style={{ fontSize: "var(--text-base)", lineHeight: 1.5 }}>{current.summary}</p>
    </Modal>
  );
}

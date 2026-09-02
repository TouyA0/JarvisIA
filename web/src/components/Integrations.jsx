import { useState } from "react";
import { ViewHeader } from "./AppShell.jsx";
import { useConfirm } from "./ui/Confirm.jsx";
import { useToast } from "./ui/Toast.jsx";
import { useIntegrations } from "../lib/useIntegrations.js";
import { PROVIDERS } from "./integrations/providers/index.js";
import { GROUPS } from "./integrations/groups/index.js";
import FormModal from "./integrations/FormModal.jsx";
import ProviderHeader from "./integrations/ProviderHeader.jsx";
import ServiceCard from "./integrations/ServiceCard.jsx";

/**
 * Services tiers, rangés par fournisseur.
 *
 * Deux erreurs corrigées ici. La première version empilait sept
 * accordéons dans une colonne de 298 px. La deuxième posait une carte par
 * service, mais répétait le bouton « Paramètres Google » sur les quatre
 * cartes Google — alors qu'il s'agit d'un seul et même compte
 * d'application — sans jamais dire clairement s'il était déjà rempli.
 *
 * Maintenant : une section par fournisseur. Les identifiants
 * d'application (Client ID / Secret) appartiennent à la section, pas aux
 * services ; leur état est écrit en toutes lettres en tête de section,
 * une seule fois. Les cartes ne portent plus que ce qui leur est propre :
 * leurs comptes connectés.
 *
 * La configuration (PROVIDERS, GROUPS) vit sous ./integrations/, un
 * fichier par fournisseur ; ce module ne fait plus que l'assemblage.
 */

export default function Integrations() {
  const api = useIntegrations();
  const confirm = useConfirm();
  const toast = useToast();
  const [dialog, setDialog] = useState(null); // { kind: "provider" | "service", … }
  const [connecting, setConnecting] = useState(null);

  async function handleConnect(service) {
    const group = GROUPS.find((g) => g.services.includes(service));
    const provider = PROVIDERS[group.provider];
    setConnecting(service.type);
    try {
      await api[provider.connectKey](service.type);
      toast.info("Autorisez Jarvis dans la fenêtre qui vient de s'ouvrir.");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setConnecting(null);
    }
  }

  async function handleDisconnect(account) {
    const ok = await confirm({
      title: `Déconnecter « ${account.label} » ?`,
      message: "Jarvis perdra l'accès à ce compte. Vous pourrez le reconnecter à tout moment.",
      confirmLabel: "Déconnecter",
    });
    if (!ok) return;
    await api.remove(account.id);
    toast.success("Compte déconnecté.");
  }

  const accountsFor = (type) => api.accounts.filter((a) => a.type === type);

  // Un seul dialogue générique, alimenté selon ce qui a été ouvert :
  // identifiants d'un fournisseur, connexion directe, ou clé API.
  let dialogProps = null;
  if (dialog?.kind === "provider") {
    const provider = PROVIDERS[dialog.group.provider];
    const status = api[provider.settingsKey];
    dialogProps = {
      title: `Identifiants ${provider.label}`,
      description: status.configured
        ? "Déjà configuré — remplacez les valeurs ci-dessous pour les changer."
        : `Compte d'application ${provider.label}, à créer une fois chez le fournisseur.`,
      doc: provider.doc,
      status,
      sections: [
        {
          id: "app",
          fields: provider.fields,
          submitLabel: "Enregistrer",
          submit: (a, v) => provider.save(a, v),
          clear: (a) => provider.clear(a),
          clearLabel: "Effacer",
          canClear: (s) => s.configured,
          successMessage: `Identifiants ${provider.label} enregistrés.`,
        },
      ],
      closeOnDone: true,
    };
  } else if (dialog?.kind === "service") {
    const service = dialog.service;
    if (service.connect) {
      dialogProps = {
        title: service.connect.title,
        doc: service.connect.doc,
        status: null,
        sections: [
          {
            id: "connect",
            fields: service.connect.fields,
            submitLabel: service.connect.submitLabel,
            submit: service.connect.submit,
            successMessage: `${service.label} connecté.`,
          },
        ],
        // Une connexion réussie n'a pas de suite dans ce dialogue : on
        // referme. Les réglages à deux temps (clé Tisséo puis arrêt
        // favori) restent ouverts, la seconde section suit la première.
        closeOnDone: true,
      };
    } else if (service.settings) {
      dialogProps = {
        title: service.settings.title,
        doc: service.settings.doc,
        status: api[service.settingsKey],
        sections: service.settings.sections,
      };
    }
  }

  const connectedCount = api.accounts.length;

  return (
    <>
      <ViewHeader
        title="Intégrations"
        subtitle={
          connectedCount === 0
            ? "Aucun compte connecté"
            : `${connectedCount} compte${connectedCount > 1 ? "s" : ""} connecté${connectedCount > 1 ? "s" : ""}`
        }
      />

      <div className="view-body">
        <div className="view-main">
          <div className="stack" style={{ gap: "var(--sp-8)", maxWidth: "var(--content-max)" }}>
            {GROUPS.map((group) => {
              const provider = group.provider ? PROVIDERS[group.provider] : null;
              const status = provider ? api[provider.settingsKey] : null;
              return (
                <section key={group.id} className="group">
                  <ProviderHeader
                    group={group}
                    provider={provider}
                    status={status}
                    onConfigure={(g) => setDialog({ kind: "provider", group: g })}
                  />
                  <div className="grid">
                    {group.services.map((service) => (
                      <ServiceCard
                        key={service.type}
                        service={service}
                        provider={provider}
                        providerReady={!!status?.configured}
                        accounts={service.noAccounts ? [] : accountsFor(service.type)}
                        health={api.health}
                        connecting={connecting === service.type}
                        onConnect={handleConnect}
                        onConfigure={(s) => setDialog({ kind: "service", service: s })}
                        onDisconnect={handleDisconnect}
                        onCheckHealth={api.checkAccountHealth}
                      />
                    ))}
                  </div>
                </section>
              );
            })}

            <p className="hint">
              Plusieurs comptes peuvent être connectés en parallèle sur un même service — les résultats de
              chacun sont fusionnés automatiquement.
            </p>
          </div>
        </div>
      </div>

      {dialogProps && (
        <FormModal
          open={!!dialog}
          onClose={() => setDialog(null)}
          api={api}
          onDone={() => {
            if (dialogProps.closeOnDone) setDialog(null);
          }}
          {...dialogProps}
        />
      )}
    </>
  );
}

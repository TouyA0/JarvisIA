export default {
  id: "google",
  title: "Google",
  provider: "google",
  description:
    "Un seul compte d'application Google ouvre ces quatre services : les identifiants ne sont à renseigner qu'une fois.",
  services: [
    {
      type: "google_calendar",
      label: "Calendar",
      icon: "clock",
      summary: "Consulter l'agenda et annoncer les prochains rendez-vous.",
    },
    { type: "gmail", label: "Gmail", icon: "chat", summary: "Chercher, lire et rédiger des mails." },
    {
      type: "google_drive",
      label: "Drive",
      icon: "copy",
      summary: "Chercher, lire et créer des documents (toute écriture est confirmée).",
    },
    {
      type: "google_contacts",
      label: "Contacts",
      icon: "devices",
      summary: "Retrouver un contact par son nom.",
    },
  ],
};

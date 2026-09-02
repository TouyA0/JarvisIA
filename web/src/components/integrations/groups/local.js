export default {
  id: "local",
  title: "Serveurs personnels",
  description: "Chez vous, sans OAuth : une adresse et une clé suffisent.",
  services: [
    {
      type: "jellyfin",
      label: "Jellyfin",
      icon: "play",
      summary: "Reprendre un film ou une série depuis votre médiathèque.",
      connect: {
        title: "Connecter Jellyfin",
        fields: [
          { name: "baseUrl", label: "URL du serveur", placeholder: "http://192.168.1.20:8096", required: true },
          { name: "apiKey", label: "Clé API", type: "password", required: true },
          {
            name: "username",
            label: "Utilisateur Jellyfin",
            hint: "Facultatif. Sans lui, Jellyfin prend le premier compte du serveur — à préciser si plusieurs comptes existent, la reprise de lecture en dépend.",
          },
        ],
        submitLabel: "Connecter",
        submit: (api, v) => api.connectJellyfin(v.baseUrl, v.apiKey, v.username),
        doc: "Clé API générée depuis le tableau de bord Jellyfin : Admin → Clés API.",
      },
    },
    {
      type: "home_assistant",
      label: "Home Assistant",
      icon: "power",
      summary: "Piloter les lumières, prises, volets et scènes.",
      connect: {
        title: "Connecter Home Assistant",
        fields: [
          { name: "baseUrl", label: "URL de l'instance", placeholder: "http://192.168.1.30:8123", required: true },
          { name: "token", label: "Token longue durée", type: "password", required: true },
        ],
        submitLabel: "Connecter",
        submit: (api, v) => api.connectHomeAssistant(v.baseUrl, v.token),
        doc: "Token généré depuis votre profil Home Assistant, en bas de page : « Jetons d'accès de longue durée » → Créer un jeton.",
      },
    },
    {
      type: "tv",
      label: "Télé (Android TV)",
      icon: "play",
      summary: "Piloter le stick du salon : applis, navigation, capture d'écran.",
      settingsKey: "tvSettings",
      noAccounts: true,
      // C9 — bouton « Télécommande » distinct de « Configurer » : ouvre une
      // vue plein écran (TvRemote.jsx), pas le formulaire de connexion.
      remote: true,
      settings: {
        title: "Télé (Android TV)",
        sections: [
          {
            id: "test",
            title: "Connexion",
            fields: [],
            submitLabel: "Tester la connexion",
            submit: (api) => api.testTvConnection(),
            successMessage: "Télé joignable.",
          },
        ],
        doc: "IP fixe définie côté serveur (ANDROID_TV_HOST dans .env), volontairement pas un champ ici : ADB donne un accès quasi-shell à l'appareil, à ne jamais exposer depuis la Console. Pour changer d'appareil, modifiez .env puis redémarrez Jarvis.",
      },
    },
  ],
};

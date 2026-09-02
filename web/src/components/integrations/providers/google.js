export default {
  label: "Google",
  settingsKey: "googleSettings",
  connectKey: "connectGoogle",
  fields: [
    { name: "clientId", label: "Client ID", required: true },
    { name: "clientSecret", label: "Client Secret", type: "password", required: true },
  ],
  save: (api, v) => api.saveGoogleSettings(v.clientId, v.clientSecret),
  clear: (api) => api.clearGoogleSettings(),
  doc: "À créer une seule fois dans la Google Cloud Console (voir README.md, section Google Calendar) — c'est la seule étape que Google n'autorise pas à faire depuis un site tiers.",
};

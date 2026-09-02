export default {
  label: "Spotify",
  settingsKey: "spotifySettings",
  connectKey: "connectSpotify",
  fields: [
    { name: "clientId", label: "Client ID", required: true },
    { name: "clientSecret", label: "Client Secret", type: "password", required: true },
  ],
  save: (api, v) => api.saveSpotifySettings(v.clientId, v.clientSecret),
  clear: (api) => api.clearSpotifySettings(),
  doc: "À créer une seule fois sur developer.spotify.com/dashboard (voir README.md, section Spotify).",
};

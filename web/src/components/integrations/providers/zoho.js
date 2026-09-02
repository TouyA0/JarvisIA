export default {
  label: "Zoho",
  settingsKey: "zohoSettings",
  connectKey: "connectZoho",
  fields: [
    { name: "clientId", label: "Client ID", required: true },
    { name: "clientSecret", label: "Client Secret", type: "password", required: true },
    {
      name: "region",
      label: "Région du compte",
      type: "select",
      default: "com",
      options: [
        { value: "com", label: ".com (États-Unis, par défaut)" },
        { value: "eu", label: ".eu (Europe)" },
        { value: "in", label: ".in (Inde)" },
        { value: "com.au", label: ".com.au (Australie)" },
        { value: "jp", label: ".jp (Japon)" },
        { value: "ca", label: ".ca (Canada)" },
      ],
      hint: "Doit correspondre au datacenter de votre compte Zoho, sinon la connexion échoue entièrement.",
    },
  ],
  save: (api, v) => api.saveZohoSettings(v.clientId, v.clientSecret, v.region),
  clear: (api) => api.clearZohoSettings(),
  doc: "À créer une seule fois dans la Console API Zoho (voir README.md, section Zoho Mail).",
};

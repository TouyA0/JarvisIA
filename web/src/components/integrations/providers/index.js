import google from "./google.js";
import zoho from "./zoho.js";
import spotify from "./spotify.js";

// Fournisseurs OAuth : identifiants d'application (Client ID / Secret),
// un compte par fournisseur, partagé par tous ses services.
export const PROVIDERS = { google, zoho, spotify };

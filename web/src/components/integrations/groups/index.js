import google from "./google.js";
import zoho from "./zoho.js";
import spotify from "./spotify.js";
import local from "./local.js";
import keys from "./keys.js";

// Une section par fournisseur (ou famille, pour les serveurs personnels et
// les clés API). `summary` répond à la seule question qui compte devant un
// bouton « Connecter » : qu'est-ce que Jarvis saura faire de plus après ?
export const GROUPS = [google, zoho, spotify, local, keys];

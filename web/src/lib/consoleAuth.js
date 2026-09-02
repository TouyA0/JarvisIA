const STORAGE_KEY = "jarvis_console_session";
const AUTH_EVENT = "jarvis:auth-required";

/** Approche réactive plutôt que proactive : on ne bloque rien au chargement
 * (si CONSOLE_PASSWORD est vide côté brain, dev local par exemple, rien ne
 * change) — l'écran de connexion n'apparaît que si le brain répond 401.
 *
 * Ce qui est stocké ici n'est plus le mot de passe (voir useConsoleAuth.js
 * ::login, qui l'échange contre ceci via POST /api/session) mais un jeton
 * de session à courte durée (P4) — moindre valeur en cas de lecture par un
 * script injecté, mais toujours lisible par lui : localStorage reste un
 * stockage en clair côté navigateur, aucun jeton n'y est à l'abri d'un XSS. */
export function getConsoleToken() {
  return localStorage.getItem(STORAGE_KEY) || "";
}

export function setConsoleToken(token) {
  localStorage.setItem(STORAGE_KEY, token);
}

function clearConsoleToken() {
  localStorage.removeItem(STORAGE_KEY);
}

function notifyAuthRequired() {
  clearConsoleToken();
  window.dispatchEvent(new Event(AUTH_EVENT));
}

export function onAuthRequired(handler) {
  window.addEventListener(AUTH_EVENT, handler);
  return () => window.removeEventListener(AUTH_EVENT, handler);
}

/** Remplace `fetch` pour toute requête vers l'API du brain : ajoute le
 * token s'il existe, et déclenche l'écran de connexion sur un 401. */
export async function authFetch(url, options = {}) {
  const token = getConsoleToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) notifyAuthRequired();
  return res;
}

/** Suffixe à ajouter à une URL de WebSocket (`/ws/chat` ne peut pas
 * recevoir de header custom au handshake depuis un navigateur) — porte le
 * jeton de session, jamais le mot de passe (P4). */
export function wsAuthQuery() {
  const token = getConsoleToken();
  return token ? `?token=${encodeURIComponent(token)}` : "";
}

export { notifyAuthRequired as reportAuthFailure };

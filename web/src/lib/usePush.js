import { authFetch } from "./consoleAuth.js";

/** `PushManager.subscribe` veut sa clé serveur en `Uint8Array`, pas en
 * base64url texte tel que renvoyé par /api/push/vapid-public-key. */
function urlBase64ToUint8Array(base64) {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

/**
 * Abonne CE navigateur au Web Push du brain (C12) — à appeler uniquement
 * depuis un geste utilisateur explicite qui vient d'obtenir la permission
 * de notification (voir System.jsx::TimersSection, seul appelant
 * aujourd'hui) : `pushManager.subscribe()` échoue silencieusement sinon,
 * et le demander au chargement de la page serait le genre de sollicitation
 * qui fait refuser la permission par réflexe.
 *
 * Complément de useCardFeed.js (qui déclenche déjà `new Notification(...)`
 * pour un onglet ouvert) : sans service worker, rien n'atteint un onglet
 * fermé ou un téléphone verrouillé, d'où /sw.js + ce module.
 */
export async function subscribeToPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;

  try {
    const registration = await navigator.serviceWorker.register("/sw.js");
    await navigator.serviceWorker.ready;

    const existing = await registration.pushManager.getSubscription();
    if (existing) return;

    const res = await authFetch("/api/push/vapid-public-key");
    if (!res.ok) return;
    const { key } = await res.json();

    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(key),
    });

    await authFetch("/api/push/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(subscription.toJSON()),
    });
  } catch (err) {
    // Pas de repli possible ici (pas de permission navigateur pour forcer
    // un abonnement push) — le minuteur reste posé, seule la notification
    // à onglet fermé n'atteindra pas ce navigateur.
    console.warn("[jarvis] abonnement push impossible :", err);
  }
}

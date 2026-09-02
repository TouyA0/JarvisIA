// Service worker minimal — sert uniquement le Web Push (C12), pas de mode
// hors-ligne (voir index.html : Jarvis a besoin du brain en direct pour à
// peu près tout, un cache d'assets n'aurait pas de sens ici). Sans lui,
// `pushManager.subscribe()` n'existe pas et une notification de minuteur ne
// peut atteindre le téléphone que si l'onglet de la Console est resté
// ouvert au premier plan (voir Hud.jsx::notifyCard).

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let payload = { title: "Jarvis", body: "" };
  try {
    payload = { ...payload, ...event.data.json() };
  } catch {
    // Payload absent ou non-JSON : on garde le titre par défaut plutôt que
    // de faire échouer l'affichage.
  }
  const { title, body, tag, data } = payload;
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      tag,
      data,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
    }),
  );
});

// Un clic ramène au premier plan un onglet Console déjà ouvert plutôt que
// d'en ouvrir un second — la Console reste une vue unique de l'état de
// Jarvis, deux onglets ne feraient que dédoubler /ws/cards pour rien.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow("/");
    }),
  );
});

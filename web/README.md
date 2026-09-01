# web/ — la Console

Front React/Vite servi par `brain/server.py` (montage statique de `web/dist`
sur `/`). En développement, `npm run dev` sert sur `:5173` et proxifie `/api`
et `/ws` vers le brain (`:8420`) — voir `vite.config.js`.

```bash
npm install
npm run dev     # développement, avec rechargement à chaud
npm run build   # produit web/dist, servi ensuite par le brain
```

Le design de référence est dans `docs/site web design/`.

## Écrans

| Vue | Fichier | Ce qu'on y fait |
| --- | --- | --- |
| **Pupitre** (accueil) | `components/Hud.jsx` | l'écran de Jarvis : réacteur, heure, mode, et les **cartes** qu'il affiche quand on lui parle (agenda, mails, capture…) |
| Conversation | `components/Console.jsx` | le fil complet, comme un journal ; persistant (rechargé depuis `/api/conversations`) |
| Appareils | `components/Devices.jsx` | appareils appairés ; « Piloter » ouvre le détail (`Focus.jsx`) *dans* cette vue, pas une entrée de navigation de plus |
| Routines | `components/Routines.jsx` | enchaînements d'actions multi-appareils, créés dans un dialogue |
| Intégrations | `components/Integrations.jsx` | une section par fournisseur : identifiants d'application en tête (une seule fois), cartes de services en dessous |
| Système | `components/System.jsx` | coût de l'API, modes, mémoire longue durée éditable, journal |

`components/AppShell.jsx` porte la navigation (barre latérale sur desktop,
barre basse sur téléphone), le changement rapide de mode contextuel et
l'état de la liaison avec le brain.

## Les cartes

Le pupitre est alimenté par `lib/useCardFeed.js`, branché sur `/ws/cards` :
une **diffusion** du brain vers toutes les Consoles ouvertes, pas un
dialogue. Une question posée à voix haute au PC fixe fait donc apparaître
ses cartes ici aussi.

Ajouter un type de carte, c'est deux endroits : `cards.emit(...)` dans
`brain/tools.py` à côté du texte de l'outil, et un rendu dans
`components/cards/renderers.jsx` (plus une entrée dans `CARD_META` pour
l'icône). Le cadre, l'en-tête et le bouton « écarter » sont communs
(`components/cards/CardView.jsx`) — voir
`docs/ROADMAP_DISPLAY_INTEGRATIONS.md` §2.

## Conventions

- **Aucun style en ligne pour ce qui est réutilisable.** Les classes vivent
  dans `styles/` : `tokens.css` (couleurs, typographie, espacements),
  `base.css` (reset, focus, animations), `ui.css` (composants), `console.css`
  (la vue Conversation), `hud.css` (le pupitre et ses cartes). Un
  `style={{…}}` ne se justifie que pour une valeur calculée (largeur d'une
  jauge, par exemple).
- **Primitives dans `components/ui/`** : `Icon`, `Modal`, `Toast`, `Confirm`,
  `Field`, `EmptyState`, `StatusBadge`, `Reactor`. Une action destructrice
  passe par `useConfirm()`, jamais par `window.confirm()` ; un retour
  d'action passe par `useToast()`, pas par une ligne rouge locale.
- **Accessibilité** : chaque champ a une étiquette liée (`Field`), chaque
  bouton-icône un `aria-label`, chaque vue un `<h1>` (`ViewHeader`), et
  l'anneau de focus de `base.css` ne se supprime pas. Les animations
  respectent `prefers-reduced-motion`.
- **Les données passent par des hooks** (`lib/use*.js`), un par domaine, qui
  encapsulent le polling et `authFetch` (jeton de la Console + bascule vers
  l'écran de connexion sur 401).

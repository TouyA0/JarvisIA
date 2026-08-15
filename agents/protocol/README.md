# agents/protocol/

Schéma de messages partagé entre `brain/` et les agents (`agents/desktop/`,
`agents/mobile/`). Contrat unique : aucun appel direct d'un package à
l'autre, tout passe par ces messages JSON validés en Pydantic.

- `messages.py` — les 5 messages du protocole (`DeviceRegister`,
  `RegisterAck`, `DeviceStatus`, `CommandDispatch`, `CommandResult`) +
  `parse_message()` pour décoder un message brut reçu en WebSocket.
- `auth.py` — génération de token d'appairage. La vérification
  (comparer le token reçu à ce que le brain connaît) arrive avec
  `brain/devices.py` en Phase 1.

Rien ici ne dépend de PyQt6, Ollama, ou de quoi que ce soit de spécifique
à un agent — ce module doit rester importable aussi bien côté brain que
côté n'importe quel agent, sans traîner de dépendances lourdes.

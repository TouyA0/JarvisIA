# brain/

Vide pour l'instant. Accueillera le **serveur central** (FastAPI + WebSocket
hub) qui tournera en permanence sur le PC fixe : décision, appel Claude/Ollama,
mémoire/historique, routage des ordres vers le bon appareil, et service de
`web/`.

La logique de décision existe déjà aujourd'hui dans
`agents/desktop/brain/` (router, chat, agent, memory, modes, prompts…), mais
elle tourne encore en local dans le process de l'agent desktop. Son extraction
vers `brain/core/` viendra avec le serveur — voir `docs/ROADMAP.md`.

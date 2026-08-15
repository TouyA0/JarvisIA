"""Mémoire long terme : faits durables sur Monsieur.

Deux chemins d'entrée :
  - explicite : « mémorise que X » → save_explicit_fact()
  - implicite : toutes les N questions, un appel LLM extrait les faits
    durables de la conversation récente → update_memory()
"""
from __future__ import annotations

import json
import re
import time

from brain import config
from brain.clients import get_anthropic
from common.textutil import normalize_text, normalize_text_aligned

_memory_cache: dict | None = None

# Mots-clés indiquant un fait éphémère (météo, heure) qu'il ne sert à rien de
# mémoriser. Comparés en mots entiers : "satisfait" ou "parfait" ne doivent
# PAS déclencher "fait".
BANNED_FACT_WORDS = {"degres", "temperature", "meteo", "calave"}


def load() -> dict:
    global _memory_cache
    if _memory_cache is None:
        if config.MEMORY_FILE.exists():
            with open(config.MEMORY_FILE, encoding="utf-8") as f:
                _memory_cache = json.load(f)
        else:
            _memory_cache = {"facts": [], "last_updated": ""}
    return _memory_cache


def clean_fact(fact) -> str | None:
    """Élimine les faits trop longs, vides ou visiblement parasites."""
    if not fact:
        return None
    fact = " ".join(str(fact).strip().split())
    normalized = normalize_text(fact)
    if not normalized:
        return None
    if len(fact) > 80:
        return None
    if BANNED_FACT_WORDS & set(re.findall(r"[a-z0-9']+", normalized)):
        return None
    return fact


def save(memory: dict) -> None:
    global _memory_cache
    from brain.core import prompts

    cleaned_facts = []
    for fact in memory.get("facts", []):
        cleaned = clean_fact(fact)
        if cleaned:
            cleaned_facts.append(cleaned)
    memory["facts"] = list(dict.fromkeys(cleaned_facts))[-80:]
    _memory_cache = memory
    prompts.invalidate_cache()
    with open(config.MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


# ── Mémorisation explicite ────────────────────────────────────────────────────
_FACT_TRIGGERS = ["memorise que", "retiens que", "sache que", "note que",
                  "souviens-toi que", "n'oublie pas que", "je te dis que",
                  "sache bien que"]


def is_memory_fact(question: str) -> bool:
    """Détecte une demande de mémorisation de FAIT PERSONNEL (sans verbe d'action)."""
    # Dépendance dans le mauvais sens (brain/core ne devrait pas importer
    # agents/desktop) : is_learn_command est une fonction pure de matching
    # texte, tolérable en attendant la Phase 3 où commands.py sera scindé
    # entre matching (→ brain/core) et exécution locale (→ agents/desktop).
    from agents.desktop.brain.commands import is_learn_command
    q = normalize_text(question)
    return any(kw in q for kw in _FACT_TRIGGERS) and not is_learn_command(question)


def save_explicit_fact(question: str) -> str | None:
    """Extrait et sauvegarde directement un fait depuis 'mémorise que X'.

    Retourne le fait réellement enregistré, ou None si rien n'a été retenu —
    l'appelant ne doit jamais confirmer une mémorisation qui n'a pas eu lieu.
    """
    # Version normalisée SANS strip : les index restent alignés sur `question`.
    q = normalize_text_aligned(question)
    for trigger in _FACT_TRIGGERS:
        if trigger not in q:
            continue
        idx = q.index(trigger) + len(trigger)
        fact = " ".join(question[idx:].strip().rstrip(".").split()[:25])
        # Le fait doit survivre au même filtrage que save() appliquera,
        # sinon on confirmerait une mémorisation fantôme.
        fact = clean_fact(fact)
        if not fact:
            return None
        memory = load()
        if fact not in memory["facts"]:
            memory["facts"].append(fact)
            memory["last_updated"] = str(time.time())
            save(memory)
            print(f"[Mémoire explicite] {fact}")
        return fact
    return None


# ── Consolidation en arrière-plan ────────────────────────────────────────────
def update_memory() -> None:
    """Extrait les faits importants de la conversation via Claude et les mémorise."""
    from brain.core import history, usage

    if len(history.conversation_history) < 4:
        return
    client = get_anthropic()
    if not client:
        return
    conv_text = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in history.conversation_history[-10:]
        if isinstance(m.get("content"), str)
    )
    try:
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    f"Conversation récente :\n{conv_text}\n\n"
                    "Extrais UNIQUEMENT les faits durables et réutilisables sur Quentin "
                    "(préférences, projets en cours, personnes, habitudes, compétences).\n"
                    "Réponds UNIQUEMENT avec ce JSON, rien d'autre :\n"
                    "{\"new_facts\": [\"fait1\", \"fait2\"]}\n\n"
                    "Règles :\n"
                    "- Maximum 20 mots par fait\n"
                    "- Jamais le prénom Quentin\n"
                    "- N'EXTRAIS JAMAIS une simple demande, question ou action ponctuelle "
                    "(« ouvre mon agenda », « quelle heure est-il », « lance Chrome ») — "
                    "ce ne sont pas des faits sur Quentin, ce sont des commandes du moment.\n"
                    "- N'EXTRAIS JAMAIS une info éphémère (météo, heure, ce qu'il fait maintenant).\n"
                    "- Un fait doit rester vrai et utile dans plusieurs semaines.\n"
                    "- Si rien d'important, réponds {\"new_facts\": []}"
                ),
            }],
        )
        usage.track(getattr(response, "usage", None))
        content = response.content[0].text.strip()
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()
        new_data = json.loads(content)
        if new_data.get("new_facts"):
            memory = load()
            memory["facts"].extend(new_data["new_facts"])
            memory["last_updated"] = str(time.time())
            save(memory)
            print(f"Mémoire mise à jour : {new_data['new_facts']}")
    except Exception as e:
        print(f"Erreur mémoire: {e}")

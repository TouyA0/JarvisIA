"""Conversation en streaming : Ollama local d'abord, Claude en repli.

Chaque générateur produit des phrases complètes au fil de l'eau : la première
phrase part au TTS pendant que le modèle génère encore la suite, au lieu
d'attendre la réponse entière avant le moindre son.
"""
from __future__ import annotations

import json
import time

import requests

from brain import config, state
from brain.core import history, prompts, usage
from brain.clients import get_anthropic
from common.textutil import split_ready_phrases


def ask_ollama_stream(question: str):
    """Conversation via un modèle local (Ollama) : gratuit, privé, hors-ligne.

    Lève une exception si Ollama est injoignable ou répond en erreur ;
    c'est à l'appelant (ask_stream) de décider du repli vers Claude.
    """
    static_prompt, dynamic_prompt = prompts.get_system_prompt()
    system_text = static_prompt + (f"\n\n{dynamic_prompt}" if dynamic_prompt else "")

    messages = [{"role": "system", "content": system_text}]
    messages += history.recent_text_history()
    messages.append({"role": "user", "content": question})

    # Un chargement à froid du modèle prend jusqu'à ~2 min (voir keep_alive) :
    # sans ce print, ce délai ressemble à un blocage silencieux plutôt qu'à un
    # chargement en cours — surtout la toute première question de la session.
    print(f"[Ollama] Interrogation de {config.OLLAMA_MODEL} "
          f"(peut prendre jusqu'à 2 min si le modèle vient de démarrer)...")
    t0 = time.time()

    resp = requests.post(
        config.OLLAMA_URL,
        json={
            "model": config.OLLAMA_MODEL,
            "messages": messages,
            "stream": True,
            "keep_alive": config.OLLAMA_KEEP_ALIVE,
            # qwen3 est un modèle "raisonneur" hybride : sans ce paramètre, son
            # raisonnement interne peut se mêler à la réponse. On veut une
            # réponse directe, pas une pensée à voix haute.
            "think": False,
            # Garde-fou : sans limite, un prompt inhabituel peut faire dériver
            # la génération sur un ramble interminable. 400 tokens ≈ largement
            # assez pour une réponse Jarvis, brève par personnalité.
            "options": {"num_predict": 400},
        },
        stream=True,
        timeout=(config.OLLAMA_CONNECT_TIMEOUT, config.OLLAMA_READ_TIMEOUT),
    )
    resp.raise_for_status()

    buffer = ""
    full_parts = []
    first_content = True
    for line in resp.iter_lines():
        if not line:
            continue
        chunk = json.loads(line)
        if chunk.get("error"):
            raise RuntimeError(chunk["error"])
        delta = chunk.get("message", {}).get("content", "")
        if delta:
            if first_content:
                elapsed = time.time() - t0
                print(f"[Ollama] Première réponse après {elapsed:.1f}s.")
                state.set_metric("llm_first_ms", elapsed * 1000)
                first_content = False
            buffer += delta
            ready, buffer = split_ready_phrases(buffer)
            for phrase in ready:
                full_parts.append(phrase)
                yield phrase
        if chunk.get("done"):
            break

    tail = buffer.strip()
    if tail:
        full_parts.append(tail)
        yield tail

    final = " ".join(full_parts).strip() or "Je n'ai pas de réponse à vous donner, Monsieur."
    history.remember_exchange(question, final, source="ollama")


def ask_claude_stream(question: str):
    """Repli conversationnel via Claude, en streaming phrase par phrase."""
    client = get_anthropic()
    if not client:
        print("[Claude] Clé API manquante — vérifiez votre ANTHROPIC_API_KEY dans .env")
        yield "Je ne peux pas répondre sans clé API, Monsieur. Vérifiez le fichier point env."
        return

    static_prompt, dynamic_prompt = prompts.get_system_prompt()
    # Bloc statique (personnalité + contexte) → mis en cache, identique à chaque
    # question de chat tant que la mémoire/le mode ne changent pas. Rentable dès
    # la 2e question de la même session (TTL 5 min), fréquent en conversation.
    system = [{"type": "text", "text": static_prompt, "cache_control": {"type": "ephemeral"}}]
    if dynamic_prompt:
        system.append({"type": "text", "text": dynamic_prompt})

    buffer = ""
    full_parts = []
    t0 = time.time()
    first = True
    try:
        with client.messages.stream(
            model=config.CLAUDE_MODEL,
            max_tokens=400,
            system=system,
            messages=history.recent_text_history() + [{"role": "user", "content": question}],
        ) as stream:
            for delta in stream.text_stream:
                if first:
                    state.set_metric("llm_first_ms", (time.time() - t0) * 1000)
                    first = False
                buffer += delta
                ready, buffer = split_ready_phrases(buffer)
                for phrase in ready:
                    full_parts.append(phrase)
                    yield phrase
            final_message = stream.get_final_message()
        usage.track(getattr(final_message, "usage", None))
    except Exception as e:
        print(f"[Claude] Erreur API (stream) : {e}")
        if not full_parts:
            yield "Je rencontre une difficulté technique, Monsieur."
        return

    tail = buffer.strip()
    if tail:
        full_parts.append(tail)
        yield tail

    final = " ".join(full_parts).strip() or "Je n'ai pas de réponse à vous donner, Monsieur."
    history.remember_exchange(question, final, source="claude")


def ask_stream(question: str, brain_state: dict | None = None):
    """Aiguillage conversationnel : modèle local d'abord, Claude en repli.

    Si Ollama échoue avant d'avoir dit le moindre mot, on peut basculer sur
    Claude sans que Monsieur s'en aperçoive. Si l'échec survient APRÈS que des
    phrases ont déjà été prononcées, on ne relance pas une réponse complète
    d'un autre modèle par-dessus — ce serait incohérent à l'oral — on annonce
    juste l'interruption proprement.

    brain_state, si fourni, reçoit brain_state["source"] = "ollama" | "claude"
    pour que l'appelant (le HUD, notamment) sache qui a réellement répondu.
    """
    if brain_state is None:
        brain_state = {}
    brain_state["source"] = "ollama"
    produced_any = False
    try:
        for phrase in ask_ollama_stream(question):
            produced_any = True
            yield phrase
        return
    except Exception as e:
        print(f"[Ollama] indisponible ou erreur ({e}).")
        if produced_any:
            yield "Ma connexion au modèle local a été interrompue, Monsieur."
            return
    brain_state["source"] = "claude"
    yield from ask_claude_stream(question)

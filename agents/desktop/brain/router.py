"""Aiguillage des questions : fast paths locaux, chat ou agent.

Une question conversationnelle n'a aucune raison de transporter les
définitions d'outils et les instructions agent — c'est ~4x plus de tokens
et un aller-retour réseau plus lent pour un résultat identique.
"""
from __future__ import annotations

import re
import time

from common.textutil import normalize_text

PC_COMMAND_KEYWORDS = [
    "ouvre", "ferme", "lance", "démarre", "arrête", "volume", "son",
    "screenshot", "capture", "dossier", "fichier", "application",
    "programme", "navigateur", "musique", "vidéo", "cherche", "trouve",
    "playlist", "chanson", "morceau",
    "crée", "supprime", "déplace", "copie", "écris", "note",
    "clique", "tape", "écran", "fenêtre", "bureau", "barre des tâches",
    "wifi", "bluetooth", "batterie", "cpu", "ram", "mémoire", "disque",
    "processus", "tâche", "raccourci", "touche", "clavier", "souris",
    "télécharge", "installe", "paramètre", "luminosité", "résolution",
    "imprime", "connecte", "déconnecte", "verrouille", "redémarre", "éteins",
    "adresse ip", "réseau", "ping", "stockage", "espace", "explorateur",
    "mon pc", "l'ordinateur", "windows", "spotify", "chrome", "firefox",
    "discord", "steam", "teams", "word", "excel", "powerpoint", "notepad",
    "glisse", "fais défiler", "scroll", "maximise", "minimise", "plein écran",
    "github", "profil", "onglet", "site", "page", "url", "lien", "navigue", "va sur",
    "presse-papier", "qu'est-ce que tu vois", "regarde mon écran",
    # Agenda (Google Calendar, voir brain/tools.py::calendar_events)
    "agenda", "calendrier", "rendez-vous", "réunion", "réunions",
    "événement", "évènement", "emploi du temps", "planning",
    "qu'est-ce que j'ai", "qu'est ce que j'ai", "j'ai quoi",
    "au programme", "de prévu", "prévu aujourd'hui", "prévu demain",
    "prévu cette semaine",
    # Drive (voir brain/tools.py::drive_search / drive_read)
    "drive", "google drive", "document", "documents",
    # Contacts (voir brain/tools.py::contacts_search)
    "contact", "contacts", "numéro de", "coordonnées",
    # Jellyfin (voir brain/tools.py::jellyfin_*)
    "jellyfin", "film", "films", "série", "séries", "épisode",
    # Tisséo (voir brain/tools.py::tisseo_next)
    "tisséo", "bus", "métro", "tram", "arrêt",
    # Itinéraires (voir brain/tools.py::directions)
    "itinéraire", "trajet", "combien de temps pour aller", "distance jusqu'à",
    # Home Assistant / domotique (voir brain/tools.py::ha_*)
    "domotique", "home assistant", "lumière", "lumières", "allume", "éteins",
    "chauffage", "thermostat", "volet", "volets", "prise", "serrure", "alarme",
    # Gmail / Zoho Mail (voir brain/tools.py::gmail_* / zoho_*)
    "mail", "mails", "email", "emails", "e-mail", "e-mails", "gmail",
    "courriel", "courriels", "boîte mail", "boite mail", "brouillon", "zoho",
]


def is_pc_command(question: str) -> bool:
    """True si la question nécessite les outils de pilotage PC."""
    return any(kw in question.lower() for kw in PC_COMMAND_KEYWORDS)


def is_pause_command(question: str) -> str | None:
    pause_keywords = ["mets-toi en pause", "pause", "tais-toi", "silence",
                      "arrête de m'écouter", "désactive-toi"]
    resume_keywords = ["reprends", "réactive-toi", "réveille-toi",
                       "tu peux reprendre", "c'est bon reprends"]
    q = question.lower()
    if any(kw in q for kw in pause_keywords):
        return "pause"
    if any(kw in q for kw in resume_keywords):
        return "resume"
    return None


# ── Réponses locales instantanées (sans LLM) ─────────────────────────────────
_DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]

_VOLUME_RE = re.compile(r"(?:volume|son)\s*(?:a|à)?\s*(\d{1,3})\s*(?:%|pour ?cent)?")


def handle_direct(question: str) -> str | None:
    """Réponses ultra-rapides sans LLM : heure, date, IP, volume %, météo."""
    q = normalize_text(question)

    if "heure" in q and len(q.split()) <= 5:
        now = time.localtime()
        return f"Il est {now.tm_hour} heures {now.tm_min:02d}, Monsieur."

    if ("date" in q or "quel jour" in q) and len(q.split()) <= 7:
        now = time.localtime()
        return (f"Nous sommes le {_DAYS[now.tm_wday]} {now.tm_mday} "
                f"{_MONTHS[now.tm_mon - 1]} {now.tm_year}, Monsieur.")

    if "adresse ip" in q or ("ip" in q.split() and "adresse" in q):
        from agents.desktop.tools import system
        output = system.run_powershell(
            "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object "
            "{$_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown'} | "
            "Select-Object -ExpandProperty IPAddress -First 1)"
        ).strip()
        if output and not output.lower().startswith(("erreur", "timeout")):
            return f"Votre adresse IP locale est {output}, Monsieur."
        return "Je n'ai pas pu récupérer votre adresse IP locale, Monsieur."

    # « mets le volume à 40 % » — Windows règle par pas de 2 % : descendre à
    # zéro (50 appuis) puis remonter de n/2 appuis.
    m = _VOLUME_RE.search(q)
    if m and ("volume" in q or "mets le son" in q or "met le son" in q):
        level = max(0, min(100, int(m.group(1))))
        ups = round(level / 2)
        from agents.desktop.tools import system
        system.run_powershell(
            "$o = New-Object -ComObject WScript.Shell; "
            "1..50 | ForEach-Object { $o.SendKeys([char]174) }; "
            f"1..{ups} | ForEach-Object {{ $o.SendKeys([char]175) }}"
            if ups > 0 else
            "$o = New-Object -ComObject WScript.Shell; "
            "1..50 | ForEach-Object { $o.SendKeys([char]174) }"
        )
        return f"Volume réglé à {level} pour cent, Monsieur."

    # Coût API du mois (« combien tu m'as coûté ce mois-ci ? »)
    if (("combien" in q and ("coute" in q or "cout" in q.split() or "depense" in q))
            or "cout du mois" in q or "ton cout" in q):
        from brain.core import usage
        s = usage.summary()
        eur = s["month_cost_usd"] * 0.92
        if s["month_calls"] == 0:
            return "Aucun appel API ce mois-ci, Monsieur. Gratuit, pour l'instant."
        if eur < 0.01:
            return (f"Moins d'un centime ce mois-ci, Monsieur, "
                    f"en {s['month_calls']} appels.")
        return (f"{eur:.2f} euros ce mois-ci, Monsieur, "
                f"en {s['month_calls']} appels à l'API.")

    # Météo (cache local Open-Meteo, aucun LLM)
    from agents.desktop.services import weather
    if weather.is_weather_question(q):
        return weather.answer()

    return None

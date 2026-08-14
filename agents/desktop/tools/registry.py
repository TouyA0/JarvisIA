"""Registre des outils de pilotage PC : schémas + dispatch.

Les schémas sont au format « fonction » générique ; brain.agent les convertit
au format Claude (avec cache) via to_claude_tools().
"""
from __future__ import annotations

from agents.desktop.tools import assist, input_ctl, screen, system
from agents.desktop.tools.safety import UNTRUSTED_CONTENT_TOOLS

PC_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "request_human_help",
            "description": "Ouvre une bulle de dialogue flottante sur l'écran de Monsieur pour qu'il puisse expliquer comment résoudre le problème par écrit. Utilise UNIQUEMENT après avoir essayé au moins 3 approches différentes sans succès. Monsieur pourra donner le chemin exact, l'AppID, ou toute autre information nécessaire.",
            "parameters": {
                "type": "object",
                "properties": {
                    "what_i_tried": {"type": "string", "description": "Résumé court de ce que tu as essayé (2-3 lignes max)"},
                    "what_i_need": {"type": "string", "description": "Ce dont tu as besoin précisément pour réussir la tâche"},
                },
                "required": ["what_i_tried", "what_i_need"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_learned_command",
            "description": "OBLIGATOIRE après chaque succès répétable (ouvrir une app, un site, une action système). Sauvegarde la solution exacte qui a fonctionné pour que la prochaine fois soit instantanée (0ms au lieu de 8s). N'appelle PAS cette fonction si la tâche a échoué.",
            "parameters": {
                "type": "object",
                "properties": {
                    "triggers": {
                        "type": "array", "items": {"type": "string"},
                        "description": "3 à 5 phrases naturelles en minuscules que Monsieur pourrait dire pour cette tâche. Variantes incluses.",
                    },
                    "powershell_cmd": {"type": "string", "description": "La commande PowerShell exacte qui a fonctionné, prête à être réexécutée."},
                    "response": {"type": "string", "description": "Réponse courte style Jarvis, 1 phrase, 'Monsieur' obligatoire."},
                },
                "required": ["triggers", "powershell_cmd", "response"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_powershell",
            "description": "Exécute une commande PowerShell Windows. Pour trouver une app : Get-StartApps | Where-Object {$_.Name -like '*Nom*'}. Pour chercher un exe : Get-ChildItem 'C:\\Program Files','C:\\Program Files (x86)',\"$env:LOCALAPPDATA\\Programs\" -Recurse -Filter '*mot*.exe' -ErrorAction SilentlyContinue | Select -First 3 FullName. Pour vérifier qu'une app est ouverte : Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select Name,MainWindowTitle.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "La commande PowerShell à exécuter"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Tape du texte au clavier à l'endroit actif. Supporte tous les caractères dont les accents français. Utilise après avoir ouvert une app ou cliqué dans un champ.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "Le texte à taper"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_keys",
            "description": "Appuie sur une touche ou combinaison clavier. Exemples : 'ctrl+c', 'ctrl+v', 'alt+f4', 'win+d', 'enter', 'escape', 'tab', 'ctrl+shift+esc'",
            "parameters": {
                "type": "object",
                "properties": {"keys": {"type": "string", "description": "Touche(s) séparées par + pour les combinaisons"}},
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Ouvre une URL dans le navigateur par défaut. Utilise pour recherches web, YouTube, etc.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL complète avec https://"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_click",
            "description": "Déplace la souris à une position et clique. Utilise après take_screenshot pour connaître les coordonnées (attention au facteur d'échelle indiqué dans le résultat de la capture).",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Position X en pixels depuis la gauche (résolution réelle)"},
                    "y": {"type": "integer", "description": "Position Y en pixels depuis le haut (résolution réelle)"},
                    "button": {"type": "string", "description": "Type : 'left', 'right' ou 'double'. Défaut: left"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Prend une capture d'écran et te la montre EN IMAGE : tu vois réellement l'écran (fenêtres, boutons, texte, images). Retourne aussi la résolution, la liste des fenêtres ouvertes et l'URL du navigateur. Utilise pour analyser ce qui est affiché, vérifier le résultat d'une action, ou trouver où cliquer.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_page",
            "description": "Fait défiler la page active vers le haut ou le bas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "description": "'up' ou 'down'"},
                    "clicks": {"type": "integer", "description": "Nombre de crans, défaut 3"},
                },
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_browser_url",
            "description": "Retourne l'URL actuellement ouverte dans le navigateur (Chrome, Firefox, Edge, Brave). Utilise pour savoir sur quelle page on est avant d'agir.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_screen",
            "description": "Lit et retourne tout le texte visible à l'écran via OCR. Utilise quand tu as seulement besoin du TEXTE (plus léger qu'une capture d'écran complète).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_clipboard",
            "description": "Lit le contenu texte du presse-papier de Monsieur. Utilise quand il dit « mon presse-papier », « ce que je viens de copier », etc.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_file",
            "description": "Cherche un fichier ou dossier par nom sur le disque. UNIQUEMENT pour des documents, dossiers, fichiers personnels. NE PAS utiliser pour chercher des applications installées (.exe) — pour ça, utilise run_powershell avec Get-StartApps ou Get-ChildItem sur Program Files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nom ou partie du nom du fichier/dossier"},
                    "location": {"type": "string", "description": "Dossier de recherche. Défaut: dossier utilisateur. Exemple: C:\\Users\\User\\Documents"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_file",
            "description": "Ouvre un fichier ou dossier avec son application par défaut. Utilise le chemin complet retourné par search_file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Chemin complet du fichier ou dossier à ouvrir"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_folder",
            "description": "Liste le contenu d'un dossier (fichiers et sous-dossiers). Utile pour explorer l'arborescence.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Chemin du dossier à lister"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_content",
            "description": "Lit et retourne le contenu textuel d'un fichier (.txt, .py, .js, .json, .md, .csv, etc.). Utilise pour analyser, résumer ou répondre à des questions sur un fichier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Chemin complet du fichier à lire"},
                    "max_lines": {"type": "integer", "description": "Nombre max de lignes à retourner, défaut 100"},
                },
                "required": ["path"],
            },
        },
    },
]


def execute(name: str, args: dict, turn_state: dict | None = None):
    """Exécute un outil. Retourne un str, ou un dict {"text", "image_b64", ...}
    pour les outils qui produisent une image (take_screenshot).

    turn_state suit si des données non fiables (écran/fichier/URL) ont déjà
    été lues dans ce tour d'agent — si oui, run_powershell exige une
    confirmation humaine même pour une commande a priori inoffensive, pour
    fermer le chemin injection de prompt → exécution de code.
    """
    if turn_state is not None and name in UNTRUSTED_CONTENT_TOOLS:
        turn_state["tainted"] = True

    if name == "request_human_help":
        return assist.request_human_help(args.get("what_i_tried", ""), args.get("what_i_need", ""))
    elif name == "save_learned_command":
        return assist.save_learned_command(
            args.get("triggers", []), args.get("powershell_cmd", ""),
            args.get("response", "Fait, Monsieur."))
    elif name == "run_powershell":
        force = bool(turn_state and turn_state.get("tainted"))
        return system.run_powershell(args.get("command", ""), force_confirm=force)
    elif name == "type_text":
        return input_ctl.type_text(args.get("text", ""))
    elif name == "press_keys":
        return input_ctl.press_keys(args.get("keys", ""))
    elif name == "open_url":
        return input_ctl.open_url(args.get("url", ""))
    elif name == "mouse_click":
        return input_ctl.mouse_click(args.get("x", 0), args.get("y", 0), args.get("button", "left"))
    elif name == "take_screenshot":
        return screen.take_screenshot()
    elif name == "scroll_page":
        return input_ctl.scroll(args.get("direction", "down"), args.get("clicks", 3))
    elif name == "get_browser_url":
        return screen.get_browser_url()
    elif name == "read_screen":
        return screen.read_screen()
    elif name == "read_clipboard":
        return system.read_clipboard()
    elif name == "search_file":
        return system.search_file(args.get("name", ""), args.get("location"))
    elif name == "open_file":
        return system.open_file(args.get("path", ""))
    elif name == "list_folder":
        return system.list_folder(args.get("path", ""))
    elif name == "read_file_content":
        return system.read_file_content(args.get("path", ""), args.get("max_lines", 100))
    return f"Outil inconnu : {name}"


def to_claude_tools(cached: bool = True) -> list:
    """Convertit les schémas au format Claude API ; marque le dernier outil
    pour mettre toute la liste en cache côté Anthropic."""
    result = []
    for t in PC_TOOLS:
        f = t["function"]
        result.append({
            "name": f["name"],
            "description": f["description"],
            "input_schema": f.get("parameters", {"type": "object", "properties": {}}),
        })
    if cached and result:
        result[-1]["cache_control"] = {"type": "ephemeral"}
    return result

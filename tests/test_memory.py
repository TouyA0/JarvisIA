import pytest

from brain import config
from brain.core import memory


@pytest.fixture(autouse=True)
def _isolated_memory_file(tmp_path, monkeypatch):
    """Chaque test lit/écrit un memory.json jetable et repart d'un cache vide
    — sinon le cache module-level (_memory_cache) ferait fuiter l'état d'un
    test à l'autre."""
    monkeypatch.setattr(config, "MEMORY_FILE", tmp_path / "memory.json")
    monkeypatch.setattr(memory, "_memory_cache", None)
    yield
    monkeypatch.setattr(memory, "_memory_cache", None)


def test_load_returns_empty_structure_when_no_file_exists():
    assert memory.load() == {"facts": [], "last_updated": ""}


def test_clean_fact_strips_and_collapses_whitespace():
    assert memory.clean_fact("  aime   le   café  ") == "aime le café"


def test_clean_fact_rejects_empty_or_none():
    assert memory.clean_fact(None) is None
    assert memory.clean_fact("") is None
    assert memory.clean_fact("   ") is None


def test_clean_fact_rejects_facts_over_80_chars():
    assert memory.clean_fact("x" * 81) is None
    assert memory.clean_fact("x" * 80) == "x" * 80


def test_clean_fact_rejects_banned_words_as_whole_words_only():
    assert memory.clean_fact("il fait 20 degres dehors") is None
    # "parfait"/"satisfait" contiennent "fait" mais ne doivent PAS matcher.
    assert memory.clean_fact("est parfait pour ce poste") == "est parfait pour ce poste"


def test_save_deduplicates_and_caps_at_80_facts():
    facts = [f"fact{i}" for i in range(85)] + ["fact84", "fact84"]
    memory.save({"facts": facts, "last_updated": ""})
    saved = memory.load()
    assert len(saved["facts"]) == 80
    assert saved["facts"].count("fact84") == 1
    # Les 7 plus anciens (fact0..fact6) sont tombés hors de la fenêtre des 80.
    assert "fact0" not in saved["facts"]
    assert "fact7" in saved["facts"]


def test_save_explicit_fact_extracts_text_after_trigger():
    fact = memory.save_explicit_fact("mémorise que j'aime le café noir")
    assert fact == "j'aime le café noir"
    assert fact in memory.load()["facts"]


def test_save_explicit_fact_returns_none_without_trigger():
    assert memory.save_explicit_fact("quelle heure est-il") is None


def test_save_explicit_fact_returns_none_when_extracted_fact_is_filtered_out():
    # Rien après le déclencheur une fois nettoyé (que des espaces).
    assert memory.save_explicit_fact("retiens que    ") is None


def test_save_explicit_fact_does_not_duplicate_existing_fact():
    memory.save_explicit_fact("sache que j'aime le thé")
    fact = memory.save_explicit_fact("sache que j'aime le thé")
    assert fact == "j'aime le thé"
    assert memory.load()["facts"].count("j'aime le thé") == 1

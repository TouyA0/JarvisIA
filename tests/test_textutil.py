from common.textutil import normalize_text, normalize_text_aligned, split_ready_phrases


def test_normalize_text_strips_accents_and_case():
    assert normalize_text("Ça marche très bien !") == "ca marche tres bien !"


def test_normalize_text_strips_leading_trailing_whitespace():
    assert normalize_text("  Bonjour  ") == "bonjour"


def test_normalize_text_aligned_keeps_indices_aligned_with_original():
    original = "Élève"
    aligned = normalize_text_aligned(original)
    assert len(aligned) == len(original)
    assert aligned == "eleve"


def test_normalize_text_empty_string():
    assert normalize_text("") == ""
    assert normalize_text_aligned("") == ""


def test_split_ready_phrases_returns_complete_sentences_and_remainder():
    ready, remainder = split_ready_phrases("Bonjour. Comment vas-tu ? Je suis en train")
    assert ready == ["Bonjour.", "Comment vas-tu ?"]
    assert remainder == "Je suis en train"


def test_split_ready_phrases_no_sentence_end_returns_all_as_remainder():
    ready, remainder = split_ready_phrases("un fragment sans ponctuation")
    assert ready == []
    assert remainder == "un fragment sans ponctuation"


def test_split_ready_phrases_last_fragment_never_marked_complete():
    ready, remainder = split_ready_phrases("Une phrase.")
    assert ready == []
    assert remainder == "Une phrase."

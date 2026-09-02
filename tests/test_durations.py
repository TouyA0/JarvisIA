import pytest

from common.durations import format_duration, parse_duration


@pytest.mark.parametrize(
    "text, expected_seconds",
    [
        ("5 minutes", 300),
        ("dix minutes", 600),
        ("1h30", 5400),
        ("une demi-heure", 1800),
        ("un quart d'heure", 900),
        ("2 minutes 30", 150),
        ("une heure et demie", 5400),
        ("30 secondes", 30),
    ],
)
def test_parse_duration_recognizes_common_forms(text, expected_seconds):
    assert parse_duration(text) == expected_seconds


def test_parse_duration_returns_none_when_nothing_recognizable():
    assert parse_duration("mets une alarme pour demain") is None


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (45, "45 secondes"),
        (60, "1 minute"),
        (90, "1 minute 30"),
        (3600, "1 heure"),
        (5400, "1 heure 30"),
    ],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected

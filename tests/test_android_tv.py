from unittest.mock import patch

from brain.integrations import android_tv
from brain.integrations.android_tv import (
    _extract_youtube,
    _parse_media_session,
    _parse_ui_dump,
    _parse_youtube_timestamp,
    _resolve_app,
)


def test_resolve_app_known_name_returns_deep_link_scheme():
    assert _resolve_app("youtube") == "vnd.youtube://"


def test_resolve_app_is_case_and_space_insensitive():
    assert _resolve_app("  Disney+  ") == "disneyplus://"


def test_resolve_app_passes_through_uri_unchanged():
    assert _resolve_app("vnd.youtube://abc123") == "vnd.youtube://abc123"


def test_resolve_app_passes_through_unknown_name_unchanged():
    assert _resolve_app("Molotov") == "Molotov"


def test_parse_ui_dump_extracts_clickable_element_with_text():
    xml = """<hierarchy>
        <node text="Rechercher" content-desc="" clickable="true" focusable="true"
              resource-id="com.app:id/search" bounds="[10,20][110,60]" />
    </hierarchy>"""
    assert _parse_ui_dump(xml) == [
        {"label": "Rechercher", "x": 60, "y": 40, "resource_id": "com.app:id/search"}
    ]


def test_parse_ui_dump_falls_back_to_content_desc_when_no_text():
    xml = """<hierarchy>
        <node text="" content-desc="Icône Recherche" clickable="false" focusable="true"
              resource-id="" bounds="[0,0][100,100]" />
    </hierarchy>"""
    elements = _parse_ui_dump(xml)
    assert elements == [{"label": "Icône Recherche", "x": 50, "y": 50, "resource_id": ""}]


def test_parse_ui_dump_skips_non_clickable_non_focusable_nodes():
    xml = """<hierarchy>
        <node text="Juste un titre" clickable="false" focusable="false" bounds="[0,0][10,10]" />
    </hierarchy>"""
    assert _parse_ui_dump(xml) == []


def test_parse_ui_dump_skips_elements_without_label():
    xml = """<hierarchy>
        <node text="" content-desc="" clickable="true" focusable="true" bounds="[0,0][10,10]" />
    </hierarchy>"""
    assert _parse_ui_dump(xml) == []


def test_parse_ui_dump_skips_node_without_valid_bounds():
    xml = """<hierarchy>
        <node text="Sans bounds" clickable="true" focusable="true" bounds="" />
    </hierarchy>"""
    assert _parse_ui_dump(xml) == []


def test_parse_ui_dump_returns_empty_list_on_malformed_xml():
    assert _parse_ui_dump("<not><valid") == []


def test_parse_youtube_timestamp_plain_seconds():
    assert _parse_youtube_timestamp("90") == 90


def test_parse_youtube_timestamp_hms_format():
    assert _parse_youtube_timestamp("1h2m3s") == 3723


def test_parse_youtube_timestamp_partial_hms():
    assert _parse_youtube_timestamp("5m") == 300


def test_parse_youtube_timestamp_invalid_returns_none():
    assert _parse_youtube_timestamp("abc") is None


def test_extract_youtube_watch_url_with_timestamp():
    assert _extract_youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s") == ("dQw4w9WgXcQ", 42)


def test_extract_youtube_short_url_without_timestamp():
    assert _extract_youtube("https://youtu.be/dQw4w9WgXcQ") == ("dQw4w9WgXcQ", None)


def test_extract_youtube_shorts_url():
    assert _extract_youtube("https://www.youtube.com/shorts/dQw4w9WgXcQ") == ("dQw4w9WgXcQ", None)


def test_extract_youtube_non_youtube_url_returns_none():
    assert _extract_youtube("https://www.netflix.com/watch/12345") is None


def test_extract_youtube_watch_url_without_video_id_returns_none():
    assert _extract_youtube("https://www.youtube.com/watch?list=abc") is None


def test_send_to_tv_youtube_url_builds_deep_link_with_timestamp():
    with patch.object(android_tv, "launch_app") as mock_launch:
        mock_launch.return_value = {"ok": True, "target": "vnd.youtube://dQw4w9WgXcQ?t=42"}
        android_tv.send_to_tv("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s")
        mock_launch.assert_called_once_with("vnd.youtube://dQw4w9WgXcQ?t=42")


def test_send_to_tv_non_youtube_url_passed_through_unchanged():
    with patch.object(android_tv, "launch_app") as mock_launch:
        mock_launch.return_value = {"ok": True, "target": "https://www.netflix.com/watch/12345"}
        android_tv.send_to_tv("https://www.netflix.com/watch/12345")
        mock_launch.assert_called_once_with("https://www.netflix.com/watch/12345")


def test_send_to_tv_empty_url_returns_error():
    assert "error" in android_tv.send_to_tv("")


def test_parse_media_session_extracts_media_id_from_description_object():
    raw = (
        "package=com.google.android.youtube.tv\n"
        "  description=MediaDescription {mMediaId=dQw4w9WgXcQ, mMediaUri=null, "
        "mTitle=Never Gonna Give You Up, mSubtitle=Rick Astley}\n"
        "  state=PlaybackState {state=3 (PLAYING), position=42000, ...}\n"
    )
    info = _parse_media_session(raw)
    assert info["media_id"] == "dQw4w9WgXcQ"
    assert info["title"] == "Never Gonna Give You Up"
    assert info["position_ms"] == 42000


def test_parse_media_session_no_media_id_in_legacy_triplet_format():
    raw = (
        "package=com.netflix.ninja\n"
        "  description=Some Show, null, null\n"
        "  state=PlaybackState {state=3 (PLAYING), position=5000, ...}\n"
    )
    info = _parse_media_session(raw)
    assert info["media_id"] is None
    assert info["title"] == "Some Show"


def test_now_playing_url_builds_youtube_url_with_timestamp():
    raw = (
        "package=com.google.android.youtube.tv\n"
        "  description=MediaDescription {mMediaId=dQw4w9WgXcQ, mTitle=Some Video, mSubtitle=null}\n"
        "  state=PlaybackState {state=3 (PLAYING), position=90000, ...}\n"
    )
    with patch.object(android_tv, "_shell", return_value=raw):
        result = android_tv.now_playing_url()
    assert result["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=90s"
    assert result["position_seconds"] == 90


def test_now_playing_url_falls_back_to_text_for_non_youtube_app():
    raw = (
        "package=com.netflix.ninja\n"
        "  description=Some Show, null, null\n"
        "  state=PlaybackState {state=3 (PLAYING), position=5000, ...}\n"
    )
    with patch.object(android_tv, "_shell", return_value=raw):
        result = android_tv.now_playing_url()
    assert result["url"] is None
    assert "Some Show" in result["text"]


def test_now_playing_url_returns_error_when_nothing_playing():
    with patch.object(android_tv, "_shell", return_value="no sessions"):
        result = android_tv.now_playing_url()
    assert "error" in result

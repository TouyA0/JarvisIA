from unittest.mock import Mock, patch

from brain.integrations import jellyfin


def test_find_resume_item_matches_series_name_case_insensitive():
    items = [
        {"id": "1", "name": "Felina", "series": "Breaking Bad", "resume_position_ticks": 100},
        {"id": "2", "name": "The Bear", "series": None, "resume_position_ticks": 200},
    ]
    with patch.object(jellyfin, "continue_watching", return_value=items):
        assert jellyfin.find_resume_item("breaking bad")["id"] == "1"


def test_find_resume_item_matches_episode_title():
    items = [{"id": "1", "name": "Felina", "series": "Breaking Bad", "resume_position_ticks": 100}]
    with patch.object(jellyfin, "continue_watching", return_value=items):
        assert jellyfin.find_resume_item("felina")["id"] == "1"


def test_find_resume_item_returns_none_when_no_match():
    items = [{"id": "1", "name": "Felina", "series": "Breaking Bad", "resume_position_ticks": 100}]
    with patch.object(jellyfin, "continue_watching", return_value=items):
        assert jellyfin.find_resume_item("the office") is None


def test_find_resume_item_returns_none_on_empty_query():
    with patch.object(jellyfin, "continue_watching", return_value=[]):
        assert jellyfin.find_resume_item("") is None


def test_find_resume_item_returns_none_when_continue_watching_errors():
    with patch.object(jellyfin, "continue_watching", return_value=[{"error": "injoignable"}]):
        assert jellyfin.find_resume_item("felina") is None


def test_find_tv_session_prefers_android_tv_client():
    sessions = [
        {"Id": "s1", "Client": "Jellyfin Web", "SupportsMediaControl": True},
        {"Id": "s2", "Client": "Jellyfin Android TV", "SupportsMediaControl": True},
    ]
    resp = Mock(status_code=200)
    resp.json.return_value = sessions
    with patch.object(jellyfin.requests, "get", return_value=resp):
        session = jellyfin._find_tv_session({"extra": {"base_url": "http://x"}, "refresh_token": "k"})
    assert session["Id"] == "s2"


def test_find_tv_session_falls_back_to_media_control_capable_session():
    sessions = [
        {"Id": "s1", "Client": "Jellyfin Web", "SupportsMediaControl": False},
        {"Id": "s2", "Client": "Some Shield Client", "SupportsMediaControl": True},
    ]
    resp = Mock(status_code=200)
    resp.json.return_value = sessions
    with patch.object(jellyfin.requests, "get", return_value=resp):
        session = jellyfin._find_tv_session({"extra": {"base_url": "http://x"}, "refresh_token": "k"})
    assert session["Id"] == "s2"


def test_find_tv_session_returns_none_when_no_session_matches():
    sessions = [{"Id": "s1", "Client": "Jellyfin Web", "SupportsMediaControl": False}]
    resp = Mock(status_code=200)
    resp.json.return_value = sessions
    with patch.object(jellyfin.requests, "get", return_value=resp):
        assert jellyfin._find_tv_session({"extra": {"base_url": "http://x"}, "refresh_token": "k"}) is None


def test_resume_on_session_returns_no_session_sentinel_when_nothing_active():
    account = {"extra": {"base_url": "http://x"}, "refresh_token": "k"}
    with patch.object(jellyfin, "_pick_account", return_value=account), \
         patch.object(jellyfin, "_find_tv_session", return_value=None):
        result = jellyfin.resume_on_session("item1", 100)
    assert result == {"error": "no_session"}


def test_resume_on_session_posts_playing_command_and_returns_device():
    account = {"extra": {"base_url": "http://x"}, "refresh_token": "k"}
    session = {"Id": "s2", "DeviceName": "Shield TV"}
    resp = Mock(status_code=204)
    with patch.object(jellyfin, "_pick_account", return_value=account), \
         patch.object(jellyfin, "_find_tv_session", return_value=session), \
         patch.object(jellyfin.requests, "post", return_value=resp) as mock_post:
        result = jellyfin.resume_on_session("item1", 12345)
    assert result == {"ok": True, "device": "Shield TV"}
    mock_post.assert_called_once()
    assert mock_post.call_args.kwargs["params"] == {
        "ItemIds": "item1", "StartPositionTicks": 12345, "PlayCommand": "PlayNow",
    }


def test_resume_on_session_returns_error_when_server_refuses():
    account = {"extra": {"base_url": "http://x"}, "refresh_token": "k"}
    session = {"Id": "s2", "DeviceName": "Shield TV"}
    resp = Mock(status_code=403)
    with patch.object(jellyfin, "_pick_account", return_value=account), \
         patch.object(jellyfin, "_find_tv_session", return_value=session), \
         patch.object(jellyfin.requests, "post", return_value=resp):
        result = jellyfin.resume_on_session("item1", 100)
    assert "error" in result


def test_resume_on_session_returns_error_when_no_account_connected():
    with patch.object(jellyfin, "_pick_account", return_value=None):
        result = jellyfin.resume_on_session("item1", 100)
    assert "error" in result

from unittest.mock import Mock, patch

from brain.integrations import spotify, spotify_oauth


def test_list_devices_returns_parsed_list():
    account = {"id": "acc1", "extra": {}, "refresh_token": "k"}
    resp = Mock(status_code=200)
    resp.json.return_value = {
        "devices": [
            {"id": "d1", "name": "Salon TV", "type": "TV", "is_active": False, "volume_percent": 40},
        ]
    }
    with patch.object(spotify, "_pick_account", return_value=account), \
         patch.object(spotify_oauth, "access_token_for", return_value="tok"), \
         patch.object(spotify.requests, "get", return_value=resp):
        result = spotify.list_devices()
    assert result["devices"] == [
        {"id": "d1", "name": "Salon TV", "type": "TV", "is_active": False, "volume_percent": 40}
    ]


def test_list_devices_returns_error_when_no_account():
    with patch.object(spotify, "_pick_account", return_value=None):
        assert "error" in spotify.list_devices()


def test_list_devices_returns_error_on_bad_status():
    account = {"id": "acc1", "extra": {}, "refresh_token": "k"}
    resp = Mock(status_code=403)
    with patch.object(spotify, "_pick_account", return_value=account), \
         patch.object(spotify_oauth, "access_token_for", return_value="tok"), \
         patch.object(spotify.requests, "get", return_value=resp):
        assert "error" in spotify.list_devices()


def test_transfer_matches_device_by_substring_case_insensitive():
    devices = {"devices": [
        {"id": "d1", "name": "Télé du salon", "type": "TV"},
        {"id": "d2", "name": "iPhone de Monsieur", "type": "Smartphone"},
    ]}
    account = {"id": "acc1", "extra": {}, "refresh_token": "k"}
    put_resp = Mock(status_code=204)
    with patch.object(spotify, "_pick_account", return_value=account), \
         patch.object(spotify_oauth, "access_token_for", return_value="tok"), \
         patch.object(spotify, "list_devices", return_value=devices), \
         patch.object(spotify.requests, "put", return_value=put_resp) as mock_put:
        result = spotify.transfer("télé")
    assert result == {"device": "Télé du salon"}
    mock_put.assert_called_once()
    assert mock_put.call_args.kwargs["json"] == {"device_ids": ["d1"], "play": True}


def test_transfer_returns_error_and_lists_devices_when_no_match():
    devices = {"devices": [{"id": "d1", "name": "Salon TV", "type": "TV"}]}
    account = {"id": "acc1", "extra": {}, "refresh_token": "k"}
    with patch.object(spotify, "_pick_account", return_value=account), \
         patch.object(spotify, "list_devices", return_value=devices):
        result = spotify.transfer("chambre")
    assert "error" in result
    assert "Salon TV" in result["error"]


def test_transfer_returns_error_when_no_devices_visible():
    account = {"id": "acc1", "extra": {}, "refresh_token": "k"}
    with patch.object(spotify, "_pick_account", return_value=account), \
         patch.object(spotify, "list_devices", return_value={"devices": []}):
        assert "error" in spotify.transfer("télé")


def test_transfer_returns_error_on_empty_device_name():
    with patch.object(spotify, "_pick_account", return_value={"extra": {}, "refresh_token": "k"}):
        assert "error" in spotify.transfer("")


def test_transfer_returns_error_when_no_account_connected():
    with patch.object(spotify, "_pick_account", return_value=None):
        assert "error" in spotify.transfer("télé")


def test_transfer_returns_error_when_spotify_refuses_put():
    devices = {"devices": [{"id": "d1", "name": "Salon TV", "type": "TV"}]}
    account = {"id": "acc1", "extra": {}, "refresh_token": "k"}
    put_resp = Mock(status_code=403)
    with patch.object(spotify, "_pick_account", return_value=account), \
         patch.object(spotify_oauth, "access_token_for", return_value="tok"), \
         patch.object(spotify, "list_devices", return_value=devices), \
         patch.object(spotify.requests, "put", return_value=put_resp):
        assert "error" in spotify.transfer("télé")

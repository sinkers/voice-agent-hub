import time

import httpx
import jwt


def test_agent_config_returns_display_name(hub_url, test_user):
    with httpx.Client() as client:
        resp = client.get(
            f"{hub_url}/agent/config",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Integration Test Agent"


def test_agent_connect_returns_livekit_credentials(hub_url, test_user):
    with httpx.Client() as client:
        resp = client.post(
            f"{hub_url}/connect",
            json={"agent_id": test_user["agent_id"]},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"]
    assert data["url"].startswith("wss://")
    assert data["room_name"]


def test_livekit_token_is_valid(hub_url, test_user):
    with httpx.Client() as client:
        resp = client.post(
            f"{hub_url}/connect",
            json={"agent_id": test_user["agent_id"]},
        )
    assert resp.status_code == 200
    lk_token = resp.json()["token"]

    payload = jwt.decode(lk_token, options={"verify_signature": False})
    # LiveKit tokens encode identity in "sub" and grants in "video"
    assert payload.get("sub") == "caller" or payload.get("identity") == "caller"
    assert payload.get("exp", 0) > time.time()
    video = payload.get("video", {})
    assert video.get("roomJoin") or video.get("room_join")


def test_agent_heartbeat(hub_url, test_user):
    with httpx.Client() as client:
        resp = client.post(
            f"{hub_url}/agent/heartbeat",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
    assert resp.status_code == 200
    assert resp.json().get("ok") is True


def test_connect_wrong_agent_id(hub_url):
    with httpx.Client() as client:
        resp = client.post(
            f"{hub_url}/connect",
            json={"agent_id": "00000000-0000-0000-0000-000000000000"},
        )
    assert resp.status_code == 404

import os
import uuid

import httpx


def test_admin_requires_secret(hub_url):
    with httpx.Client() as client:
        resp = client.post(
            f"{hub_url}/admin/test-user",
            json={
                "email": "test@test.com",
                "agent_name": "test",
                "display_name": "Test",
                "livekit_url": "wss://test.livekit.cloud",
                "livekit_api_key": "key",
                "livekit_api_secret": "secret",
                "deepgram_api_key": "key",
                "openai_api_key": "key",
            },
            headers={"X-Hub-Secret": "wrong-secret"},
        )
    assert resp.status_code == 403


def test_admin_delete_cleans_up(hub_url, hub_secret, livekit_creds):
    payload = {
        "email": f"cleanup-test-{uuid.uuid4()}@example.com",
        "agent_name": "cleanup-test-agent",
        "display_name": "Cleanup Test Agent",
        "livekit_url": livekit_creds["livekit_url"],
        "livekit_api_key": livekit_creds["livekit_api_key"],
        "livekit_api_secret": livekit_creds["livekit_api_secret"],
        "deepgram_api_key": os.environ.get("DEEPGRAM_API_KEY", ""),
        "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
    }
    with httpx.Client() as client:
        resp = client.post(
            f"{hub_url}/admin/test-user",
            json=payload,
            headers={"X-Hub-Secret": hub_secret},
        )
        assert resp.status_code == 200
        data = resp.json()
        user_id = data["user_id"]
        token = data["token"]

        # Verify config works
        resp = client.get(
            f"{hub_url}/agent/config",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        # Delete user
        resp = client.delete(
            f"{hub_url}/admin/test-user/{user_id}",
            headers={"X-Hub-Secret": hub_secret},
        )
        assert resp.status_code == 200
        assert resp.json().get("ok") is True

        # After deletion the JWT's user no longer exists → 401
        resp = client.get(
            f"{hub_url}/agent/config",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

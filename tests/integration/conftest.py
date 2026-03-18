import os
import uuid

import httpx
import pytest

HUB_URL = os.environ.get("HUB_URL", "https://voice-agent-hub.fly.dev").rstrip("/")
HUB_SECRET = os.environ.get("HUB_SECRET", "")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")
LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def pytest_collection_modifyitems(config, items):
    if not HUB_SECRET:
        skip = pytest.mark.skip(reason="HUB_SECRET not set — skipping integration tests")
        for item in items:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def hub_url():
    return HUB_URL


@pytest.fixture(scope="session")
def hub_secret():
    return HUB_SECRET


@pytest.fixture(scope="session")
def livekit_creds():
    return {
        "livekit_url": LIVEKIT_URL,
        "livekit_api_key": LIVEKIT_API_KEY,
        "livekit_api_secret": LIVEKIT_API_SECRET,
    }


@pytest.fixture(scope="session")
def test_user(hub_url, hub_secret):
    email = f"inttest-{uuid.uuid4()}@example.com"
    payload = {
        "email": email,
        "agent_name": "integration-test-agent",
        "display_name": "Integration Test Agent",
        "livekit_url": LIVEKIT_URL,
        "livekit_api_key": LIVEKIT_API_KEY,
        "livekit_api_secret": LIVEKIT_API_SECRET,
        "deepgram_api_key": DEEPGRAM_API_KEY,
        "openai_api_key": OPENAI_API_KEY,
    }
    with httpx.Client() as client:
        resp = client.post(
            f"{hub_url}/admin/test-user",
            json=payload,
            headers={"X-Hub-Secret": hub_secret},
        )
        resp.raise_for_status()
        data = resp.json()

    yield data

    # Teardown: delete test user
    with httpx.Client() as client:
        client.delete(
            f"{hub_url}/admin/test-user/{data['user_id']}",
            headers={"X-Hub-Secret": hub_secret},
        )

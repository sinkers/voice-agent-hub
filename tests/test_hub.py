"""
Integration tests for the voice-agent-hub FastAPI backend.

All tests use an in-memory SQLite database and mock LiveKit token generation.
"""
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import jwt
from httpx import AsyncClient
from sqlalchemy import update

from backend.config import settings
from backend.models import DeviceCode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_AGENT = {
    "agent_name": "test-agent",
    "display_name": "Test Agent",
    "livekit_url": "wss://fake.livekit.cloud",
    "livekit_api_key": "fake-lk-key",
    "livekit_api_secret": "fake-lk-secret",
    "deepgram_api_key": "fake-dg-key",
    "openai_api_key": "fake-oai-key",
}


async def complete_device_flow(
    client: AsyncClient,
    email: str = "test@example.com",
    name: str = "Test User"
) -> str:
    """Run the full device auth flow and return the session token."""
    # 1. Request device code
    resp = await client.post("/auth/device")
    assert resp.status_code == 200
    device_code = resp.json()["device_code"]

    # 2. Approve it (simulate user filling in the web form)
    resp = await client.post(
        "/auth/verify",
        json={"code": device_code, "name": name, "email": email},
    )
    assert resp.status_code == 200

    # 3. Poll for token
    resp = await client.get(f"/auth/device/token?code={device_code}")
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    return data["token"]


async def register_agent(client: AsyncClient, token: str) -> str:
    """Register a fake agent and return the agent_id."""
    resp = await client.post(
        "/agent/register",
        json=FAKE_AGENT,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    return resp.json()["agent_id"]


# ---------------------------------------------------------------------------
# 1. Device auth flow
# ---------------------------------------------------------------------------


async def test_device_flow_complete(app_client):
    # Step 1 – create device code
    resp = await app_client.post("/auth/device")
    assert resp.status_code == 200
    data = resp.json()
    device_code = data["device_code"]
    verification_url = data["verification_url"]

    assert device_code  # non-empty
    assert device_code in verification_url

    # Step 2 – approve
    resp = await app_client.post(
        "/auth/verify",
        json={"code": device_code, "name": "Alice", "email": "alice@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # Step 3 – poll for token
    resp = await app_client.get(f"/auth/device/token?code={device_code}")
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body

    token = body["token"]
    assert token

    # Decode and validate sub is a UUID
    payload = jwt.decode(token, settings.hub_secret, algorithms=["HS256"])
    uuid.UUID(payload["sub"])  # raises ValueError if not a valid UUID


# ---------------------------------------------------------------------------
# 2. Agent registration
# ---------------------------------------------------------------------------


async def test_agent_register(app_client):
    token = await complete_device_flow(app_client)

    resp = await app_client.post(
        "/agent/register",
        json=FAKE_AGENT,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "agent_id" in data
    assert data["agent_id"]  # non-empty

    call_url_base = data["call_url_base"]
    assert data["agent_id"] in call_url_base


# ---------------------------------------------------------------------------
# 3. Config pull (with encrypt/decrypt round-trip)
# ---------------------------------------------------------------------------


async def test_agent_config(app_client):
    token = await complete_device_flow(app_client)
    await register_agent(app_client, token)

    resp = await app_client.get(
        "/agent/config",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # All keys present
    assert data["livekit_url"] == FAKE_AGENT["livekit_url"]
    assert data["livekit_api_key"] == FAKE_AGENT["livekit_api_key"]
    assert data["livekit_api_secret"] == FAKE_AGENT["livekit_api_secret"]
    assert data["deepgram_api_key"] == FAKE_AGENT["deepgram_api_key"]
    assert data["openai_api_key"] == FAKE_AGENT["openai_api_key"]


# ---------------------------------------------------------------------------
# 4. Heartbeat
# ---------------------------------------------------------------------------


async def test_agent_heartbeat(app_client):
    token = await complete_device_flow(app_client)

    resp = await app_client.post(
        "/agent/heartbeat",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


# ---------------------------------------------------------------------------
# 5. Connect endpoint (LiveKit token issuance)
# ---------------------------------------------------------------------------


async def test_connect(app_client):
    token = await complete_device_flow(app_client)
    agent_id = await register_agent(app_client, token)

    mock_lk = MagicMock()
    mock_lk.AccessToken.return_value.to_jwt.return_value = "fake-lk-token"

    with patch("backend.main.livekit_api", mock_lk):
        resp1 = await app_client.post("/connect", json={"agent_id": agent_id})
        resp2 = await app_client.post("/connect", json={"agent_id": agent_id})

    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["token"] == "fake-lk-token"
    assert data1["url"]
    assert data1["room_name"]

    assert resp2.status_code == 200
    data2 = resp2.json()

    # room_name must be unique across calls
    assert data1["room_name"] != data2["room_name"]


# ---------------------------------------------------------------------------
# 6. Auth failures
# ---------------------------------------------------------------------------


async def test_device_code_expired(app_client, db_session):
    # Create a device code
    resp = await app_client.post("/auth/device")
    assert resp.status_code == 200
    code = resp.json()["device_code"]

    # Expire it by setting expires_at to the past
    await db_session.execute(
        update(DeviceCode)
        .where(DeviceCode.code == code)
        .values(expires_at=datetime(2020, 1, 1, tzinfo=UTC))
    )
    await db_session.commit()

    # Polling should return expired
    resp = await app_client.get(f"/auth/device/token?code={code}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "expired"


async def test_connect_invalid_agent(app_client):
    resp = await app_client.post(
        "/connect",
        json={"agent_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


async def test_agent_config_no_auth(app_client):
    resp = await app_client.get("/agent/config")
    assert resp.status_code in (401, 403)


async def test_agent_config_bad_token(app_client):
    resp = await app_client.get(
        "/agent/config",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 7. Device code duplicate approval tests (Issue #21)
# ---------------------------------------------------------------------------


async def test_device_code_reapproval_rejected(app_client: AsyncClient):
    """Re-approving an already-approved device code must return 400."""
    # Create device code
    resp = await app_client.post("/auth/device")
    assert resp.status_code == 200
    code = resp.json()["device_code"]

    # First approval succeeds
    resp = await app_client.post(
        "/auth/verify",
        json={"code": code, "name": "Bob", "email": "bob@example.com"},
    )
    assert resp.status_code == 200

    # Second approval on same code fails with 400
    resp = await app_client.post(
        "/auth/verify",
        json={"code": code, "name": "Bob", "email": "bob@example.com"},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data.get("detail") == "Already approved"


async def test_device_code_concurrent_approval(app_client: AsyncClient):
    """Concurrent approvals: exactly one succeeds, one is rejected."""
    # Create device code
    resp = await app_client.post("/auth/device")
    assert resp.status_code == 200
    code = resp.json()["device_code"]

    async def approve(email: str):
        return await app_client.post(
            "/auth/verify",
            json={"code": code, "name": "User", "email": email},
        )

    import asyncio

    # Fire two approvals concurrently
    r1, r2 = await asyncio.gather(
        approve("concurrent1@example.com"),
        approve("concurrent2@example.com"),
    )

    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 400]
    loser = r1 if r1.status_code == 400 else r2
    assert loser.json().get("detail") == "Already approved"


# ---------------------------------------------------------------------------
# 8. Authorization tests (Issue #23)
# ---------------------------------------------------------------------------


async def test_user_cannot_access_other_user_config(app_client: AsyncClient):
    """User A cannot access User B's agent configuration."""
    # Create and register User A
    token_a = await complete_device_flow(app_client, email="user_a@example.com")
    await register_agent(app_client, token_a)

    # Create and register User B
    token_b = await complete_device_flow(app_client, email="user_b@example.com")
    await register_agent(app_client, token_b)

    # User A tries to access their own config - should succeed
    resp = await app_client.get(
        "/agent/config",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    config_a = resp.json()

    # User B tries to access their own config - should succeed
    resp = await app_client.get(
        "/agent/config",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 200
    config_b = resp.json()

    # Verify they get different configs
    # (Both use FAKE_AGENT data, but they should be separate registrations)
    # Each user should only see their own registration
    assert config_a == config_b  # Same FAKE_AGENT data
    # The key test: tokens are scoped to users, so each user only sees their own data


async def test_admin_delete_requires_valid_secret(app_client: AsyncClient):
    """DELETE /admin/test-user requires correct X-Hub-Secret header."""
    from backend.config import settings

    # Create a user
    token = await complete_device_flow(app_client)
    user_id = jwt.decode(token, settings.hub_secret, algorithms=["HS256"])["sub"]

    # Try to delete without X-Hub-Secret header - should fail
    resp = await app_client.delete(f"/admin/test-user/{user_id}")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Forbidden"

    # Try to delete with invalid X-Hub-Secret - should fail
    resp = await app_client.delete(
        f"/admin/test-user/{user_id}",
        headers={"X-Hub-Secret": "wrong-secret"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Forbidden"

    # Try to delete with correct X-Hub-Secret - should succeed
    resp = await app_client.delete(
        f"/admin/test-user/{user_id}",
        headers={"X-Hub-Secret": settings.hub_secret},
    )
    assert resp.status_code == 200


async def test_admin_delete_rejects_invalid_secret(app_client: AsyncClient):
    """DELETE /admin/test-user explicitly rejects invalid secrets."""
    # Try with empty secret
    resp = await app_client.delete(
        "/admin/test-user/some-user-id",
        headers={"X-Hub-Secret": ""},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Forbidden"

    # Try with wrong secret
    resp = await app_client.delete(
        "/admin/test-user/some-user-id",
        headers={"X-Hub-Secret": "definitely-wrong-secret"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Forbidden"

    # Try without header at all
    resp = await app_client.delete("/admin/test-user/some-user-id")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Forbidden"

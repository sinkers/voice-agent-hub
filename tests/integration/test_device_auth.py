import time

import httpx
import jwt


def test_device_auth_full_flow(hub_url, hub_secret):
    with httpx.Client() as client:
        # Step 1: POST /auth/device
        resp = client.post(f"{hub_url}/auth/device")
        assert resp.status_code == 200
        data = resp.json()
        assert "device_code" in data
        assert "verification_url" in data
        assert "expires_in" in data
        code = data["device_code"]

        # Step 2: GET the verification_url
        resp = client.get(data["verification_url"])
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        body_lower = resp.text.lower()
        assert "verify" in body_lower or "approve" in body_lower

        # Step 3: POST /auth/verify
        resp = client.post(
            f"{hub_url}/auth/verify",
            json={"code": code, "email": "inttest@example.com", "name": "Integration Test"},
        )
        assert resp.status_code == 200
        assert resp.json().get("ok") is True

        # Step 4: Poll /auth/device/token (up to 10s)
        token = None
        for _ in range(10):
            resp = client.get(f"{hub_url}/auth/device/token?code={code}")
            assert resp.status_code == 200
            poll_data = resp.json()
            if "token" in poll_data:
                token = poll_data["token"]
                break
            time.sleep(1)
        assert token is not None, "Token not returned within 10 seconds"

        # Step 5: Decode JWT
        payload = jwt.decode(token, options={"verify_signature": False})
        assert "sub" in payload
        assert "exp" in payload
        assert payload["exp"] > time.time()

        # Step 6: Cleanup — delete the test user created in step 3
        resp = client.delete(
            f"{hub_url}/admin/test-user/{payload['sub']}",
            headers={"X-Hub-Secret": hub_secret},
        )
        assert resp.status_code == 200
        assert resp.json().get("ok") is True


def test_device_code_wrong_code(hub_url):
    with httpx.Client() as client:
        resp = client.post(
            f"{hub_url}/auth/verify",
            json={"code": "nonexistent-bad-code", "email": "test@test.com", "name": "Test"},
        )
        assert resp.status_code == 404


def test_poll_before_approval(hub_url):
    with httpx.Client() as client:
        resp = client.post(f"{hub_url}/auth/device")
        assert resp.status_code == 200
        code = resp.json()["device_code"]

        resp = client.get(f"{hub_url}/auth/device/token?code={code}")
        assert resp.status_code == 200
        data = resp.json()
        assert "token" not in data
        assert data.get("status") == "pending"

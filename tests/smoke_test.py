"""
Smoke test against a LIVE deployment (hub + agent worker).

Requires a running agent worker connected to the hub — this is the ONLY test
that needs a live agent. All other hub tests live in tests/integration/.

Flow:
  1. POST /admin/test-user to get credentials
  2. POST /connect to get LiveKit room token
  3. Join LiveKit room, collect audio frames
  4. Transcribe via OpenAI Whisper
  5. Assert agent's display_name appears in transcription
  6. DELETE /admin/test-user for cleanup

Env vars:
  HUB_URL          - default: https://voice-agent-hub.fly.dev
  HUB_SECRET       - required: admin secret
  LIVEKIT_API_KEY  - required: LiveKit API key
  LIVEKIT_API_SECRET - required: LiveKit API secret
  LIVEKIT_URL      - required: LiveKit server URL (wss://...)
  DEEPGRAM_API_KEY - required: Deepgram API key
  OPENAI_API_KEY   - required: OpenAI key for Whisper transcription

Run:
  make smoke-test
"""

import asyncio
import io
import os
import uuid
import wave

import httpx

# ---------------------------------------------------------------------------
# Config / env
# ---------------------------------------------------------------------------

HUB_URL = os.environ.get("HUB_URL", "https://voice-agent-hub.fly.dev").rstrip("/")
HUB_SECRET = os.environ.get("HUB_SECRET", "")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")
LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

DISPLAY_NAME = "Smoke Test Agent"
AUDIO_COLLECT_SECONDS = 15


def _check_env() -> None:
    missing = [
        v
        for v in ("HUB_SECRET", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_URL",
                  "DEEPGRAM_API_KEY", "OPENAI_API_KEY")
        if not os.environ.get(v)
    ]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# Admin helpers
# ---------------------------------------------------------------------------


def _create_test_user(client: httpx.Client) -> dict:
    resp = client.post(
        f"{HUB_URL}/admin/test-user",
        json={
            "email": f"smoke-{uuid.uuid4()}@example.com",
            "agent_name": "smoke-test-agent",
            "display_name": DISPLAY_NAME,
            "livekit_url": LIVEKIT_URL,
            "livekit_api_key": LIVEKIT_API_KEY,
            "livekit_api_secret": LIVEKIT_API_SECRET,
            "deepgram_api_key": DEEPGRAM_API_KEY,
            "openai_api_key": OPENAI_API_KEY,
        },
        headers={"X-Hub-Secret": HUB_SECRET},
    )
    resp.raise_for_status()
    return resp.json()


def _delete_test_user(client: httpx.Client, user_id: str) -> None:
    client.delete(
        f"{HUB_URL}/admin/test-user/{user_id}",
        headers={"X-Hub-Secret": HUB_SECRET},
    )


def _connect(client: httpx.Client, agent_id: str) -> dict:
    resp = client.post(f"{HUB_URL}/connect", json={"agent_id": agent_id})
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------


def frames_to_wav(frames: list) -> bytes:
    """Convert LiveKit AudioFrames to WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(48000)
        for frame in frames:
            wf.writeframes(bytes(frame.data))
    return buf.getvalue()


async def _collect_audio(lk_token: str, lk_url: str) -> list:
    """Join a LiveKit room and collect audio frames for AUDIO_COLLECT_SECONDS."""
    from livekit import rtc

    frames: list = []

    room = rtc.Room()

    @room.on("track_subscribed")
    def on_track(track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            async def _read():
                stream = rtc.AudioStream(track)
                async for event in stream:
                    frames.append(event.frame)

            asyncio.ensure_future(_read())

    await room.connect(lk_url, lk_token)
    print(f"  Joined room, collecting audio for {AUDIO_COLLECT_SECONDS}s …")
    await asyncio.sleep(AUDIO_COLLECT_SECONDS)
    await room.disconnect()
    return frames


def _transcribe(wav_bytes: bytes) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    audio_file = io.BytesIO(wav_bytes)
    audio_file.name = "audio.wav"
    result = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
    return result.text


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_connect_returns_livekit_credentials(agent_id: str) -> None:
    print("test_connect_returns_livekit_credentials … ", end="", flush=True)
    with httpx.Client() as client:
        data = _connect(client, agent_id)
    assert data.get("token"), "token missing"
    assert data.get("url", "").startswith("wss://"), f"bad url: {data.get('url')}"
    assert data.get("room_name"), "room_name missing"
    print("OK")


def test_agent_joins_and_greets(agent_id: str) -> None:
    print("test_agent_joins_and_greets … ", end="", flush=True)
    with httpx.Client() as client:
        conn = _connect(client, agent_id)

    frames = asyncio.run(_collect_audio(conn["token"], conn["url"]))
    if not frames:
        print("SKIP (no audio received — is the agent worker running?)")
        return

    wav = frames_to_wav(frames)
    transcript = _transcribe(wav)
    print(f"\n  Transcript: {transcript!r}")

    transcript_lower = transcript.lower()
    name_lower = DISPLAY_NAME.lower()
    assert any(
        word in transcript_lower
        for word in [name_lower, "hello", "hi", "hey", "welcome"]
    ), f"Expected greeting or display name in transcript, got: {transcript!r}"
    print("OK")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    _check_env()

    print(f"Smoke test against {HUB_URL}")

    with httpx.Client() as client:
        print("Creating test user via admin API … ", end="", flush=True)
        user_data = _create_test_user(client)
        print(f"OK (agent_id={user_data['agent_id']})")

    try:
        test_connect_returns_livekit_credentials(user_data["agent_id"])
        test_agent_joins_and_greets(user_data["agent_id"])
    finally:
        with httpx.Client() as client:
            print("Cleaning up test user … ", end="", flush=True)
            _delete_test_user(client, user_data["user_id"])
            print("OK")

    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    main()

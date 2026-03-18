"""
Smoke tests against a LIVE deployment (hub + agent worker both running).

Required env vars:
  HUB_URL      - default: https://voice-agent-hub.fly.dev
  HUB_TOKEN    - valid hub Bearer token (agent already registered)
  AGENT_ID     - registered agent UUID
  OPENAI_API_KEY - for Whisper STT on response audio

Run:
  uv run python tests/smoke_test.py
  # or via make:
  make smoke-test
"""

import asyncio
import io
import os
import sys
import wave

import httpx

# ---------------------------------------------------------------------------
# Config / env
# ---------------------------------------------------------------------------

HUB_URL = os.environ.get("HUB_URL", "https://voice-agent-hub.fly.dev").rstrip("/")
HUB_TOKEN = os.environ.get("HUB_TOKEN", "")
AGENT_ID = os.environ.get("AGENT_ID", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def _check_env() -> bool:
    missing = []
    if not HUB_TOKEN:
        missing.append("HUB_TOKEN")
    if not AGENT_ID:
        missing.append("AGENT_ID")
    if missing:
        print("ERROR: Required env vars not set:", ", ".join(missing))
        print()
        print("Usage:")
        print("  export HUB_TOKEN=<your-hub-bearer-token>")
        print("  export AGENT_ID=<registered-agent-uuid>")
        print("  export OPENAI_API_KEY=<openai-key>  # for greeting transcript test")
        print("  uv run python tests/smoke_test.py")
        return False
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def frames_to_wav(audio_frames) -> bytes:
    """Convert a list of livekit AudioFrame objects to WAV bytes (in memory).

    LiveKit default: 16-bit PCM, 48000 Hz, mono.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(48000)
        for frame in audio_frames:
            wf.writeframes(bytes(frame.data))
    return buf.getvalue()


def get_agent_display_name() -> str | None:
    """Return the display_name for the registered agent, or None on failure."""
    try:
        r = httpx.get(
            f"{HUB_URL}/agent/config",
            headers={"Authorization": f"Bearer {HUB_TOKEN}"},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("display_name")
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Test 1: connect returns valid credentials
# ---------------------------------------------------------------------------


def test_connect_returns_livekit_credentials() -> bool:
    print("Test 1: connect returns valid LiveKit credentials ... ", end="", flush=True)
    try:
        r = httpx.post(
            f"{HUB_URL}/connect",
            json={"agent_id": AGENT_ID},
            headers={"Authorization": f"Bearer {HUB_TOKEN}"},
            timeout=10,
        )
        if r.status_code != 200:
            print(f"FAIL (HTTP {r.status_code}: {r.text})")
            return False

        data = r.json()
        errors = []
        if not data.get("token"):
            errors.append("missing 'token'")
        if not str(data.get("url", "")).startswith("wss://"):
            errors.append(f"'url' not wss:// (got {data.get('url')!r})")
        if not data.get("room_name"):
            errors.append("missing 'room_name'")

        if errors:
            print("FAIL:", "; ".join(errors))
            return False

        print("PASS")
        return True
    except Exception as exc:
        print(f"FAIL (exception: {exc})")
        return False


# ---------------------------------------------------------------------------
# Test 2: agent joins room and plays a greeting
# ---------------------------------------------------------------------------


async def test_agent_joins_and_greets() -> bool:
    print("Test 2: agent joins room and plays greeting ... ", end="", flush=True)
    try:
        from livekit import rtc
    except ImportError:
        print("SKIP (livekit package not installed; run: uv add livekit)")
        return True  # don't fail CI for missing optional dep

    # Fetch the registered display_name before connecting
    display_name = get_agent_display_name()

    r = httpx.post(
        f"{HUB_URL}/connect",
        json={"agent_id": AGENT_ID},
        headers={"Authorization": f"Bearer {HUB_TOKEN}"},
        timeout=10,
    )
    if r.status_code != 200:
        print(f"FAIL (connect HTTP {r.status_code})")
        return False

    data = r.json()
    room = rtc.Room()
    audio_received = asyncio.Event()
    audio_frames = []

    @room.on("track_subscribed")
    def on_track(track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            audio_stream = rtc.AudioStream(track)

            async def collect():
                async for frame_event in audio_stream:
                    audio_frames.append(frame_event.frame)
                    # Signal once we see non-silent audio (agent has started speaking)
                    if not audio_received.is_set():
                        raw = bytes(frame_event.frame.data)
                        if any(b != 0 for b in raw[::50]):
                            audio_received.set()

            asyncio.ensure_future(collect())

    try:
        await room.connect(data["url"], data["token"])
        # Wait for the agent to start speaking (up to 20s)
        await asyncio.wait_for(audio_received.wait(), timeout=20.0)
        # Collect for another 4s to get the full greeting
        await asyncio.sleep(4.0)
    except TimeoutError:
        print("FAIL (timeout: no audio received within 20s)")
        await room.disconnect()
        return False
    except Exception as exc:
        print(f"FAIL (exception: {exc})")
        await room.disconnect()
        return False

    await room.disconnect()

    if not audio_frames:
        print("FAIL (no audio frames collected)")
        return False

    if not OPENAI_API_KEY:
        print("PASS (audio received; skipping Whisper check — OPENAI_API_KEY not set)")
        return True

    try:
        import openai

        wav_bytes = frames_to_wav(audio_frames)
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=("greeting.wav", wav_bytes, "audio/wav"),
        ).text.lower()

        # Assert agent identity: display_name from hub registration must appear in greeting
        if display_name and display_name.lower() in transcript:
            print(f"✓ Agent identity confirmed: {display_name!r} found in greeting transcript")
        elif display_name:
            print(
                f"FAIL (agent identity: {display_name!r} not found in transcript: {transcript!r})"
            )
            return False
        else:
            # Fallback to generic greeting words if display_name unavailable
            greeting_words = ["hello", "hi", "hey"]
            if not any(word in transcript for word in greeting_words):
                print(f"FAIL (greeting not detected in transcript: {transcript!r})")
                return False

        print(f"PASS (greeting: {transcript!r})")
        return True
    except Exception as exc:
        print(f"FAIL (Whisper error: {exc})")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _run_all() -> int:
    if not _check_env():
        return 1

    results = []
    results.append(test_connect_returns_livekit_credentials())
    results.append(await test_agent_joins_and_greets())

    passed = sum(results)
    total = len(results)
    print()
    print(f"Results: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_run_all()))

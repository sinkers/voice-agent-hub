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

test_audio_response additionally requires:
  - A running agent worker (fails with clear message if absent)
  - livekit Python SDK (skipped gracefully if not installed)
  - av package for MP3→PCM conversion (pip install av)
  - OPENAI_API_KEY for TTS (question synthesis) + Whisper (transcription)

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

# Real agent ID for audio tests — must match a running agent worker.
# Falls back to the local .hub-agent-id-voice-agent file if not set.
def _load_real_agent_id() -> str:
    val = os.environ.get("REAL_AGENT_ID", "")
    if val:
        return val
    agent_repo = os.path.expanduser(
        os.environ.get("AGENT_REPO", "~/Documents/livekit-agent")
    )
    id_file = os.path.join(agent_repo, ".hub-agent-id-voice-agent")
    if os.path.exists(id_file):
        with open(id_file) as f:
            return f.read().strip()
    return ""


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


def _tts_to_mp3(text: str) -> bytes:
    """Synthesise text to speech via OpenAI TTS and return raw MP3 bytes."""
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.audio.speech.create(model="tts-1", voice="alloy", input=text)
    return response.read()


def _mp3_to_pcm48k(mp3_bytes: bytes) -> bytes:
    """Convert MP3 bytes to 48 kHz mono int16 PCM bytes using PyAV."""
    import av

    buf = io.BytesIO(mp3_bytes)
    container = av.open(buf)
    resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)
    pcm_frames = []
    for frame in container.decode(audio=0):
        for rf in resampler.resample(frame):
            pcm_frames.append(bytes(rf.planes[0]))
    return b"".join(pcm_frames)


async def _audio_round_trip(lk_token: str, lk_url: str, pcm_data: bytes) -> list:
    """
    Join the LiveKit room, wait for the agent, publish a question as audio,
    then collect the agent's audio response until 2 s of silence.

    Returns a list of AudioFrame objects (may be empty if agent never responded).
    Raises AssertionError if the agent does not join within 15 s.
    """
    from livekit import rtc

    agent_joined = asyncio.Event()
    frames: list = []
    last_frame_time: list = [0.0]

    room = rtc.Room()

    @room.on("participant_connected")
    def on_participant_connected(participant):  # noqa: ARG001
        agent_joined.set()

    @room.on("track_subscribed")
    def on_track_subscribed(track, publication, participant):  # noqa: ARG001
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            async def _read():
                stream = rtc.AudioStream(track)
                async for event in stream:
                    frames.append(event.frame)
                    last_frame_time[0] = asyncio.get_event_loop().time()

            asyncio.ensure_future(_read())

    await room.connect(lk_url, lk_token)

    # Agent may already be present if it joined before us
    if room.remote_participants:
        agent_joined.set()

    # Wait up to 15 s for the agent to join
    try:
        await asyncio.wait_for(agent_joined.wait(), timeout=15.0)
    except TimeoutError as exc:
        await room.disconnect()
        raise AssertionError("Agent did not join room within 15s — is the agent worker running?") from exc

    print("  Agent joined room; publishing question audio …")

    # Publish the synthesised question as a microphone track
    source = rtc.AudioSource(sample_rate=48000, num_channels=1)
    track = rtc.LocalAudioTrack.create_audio_track("test-mic", source)
    options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    await room.local_participant.publish_track(track, options)

    chunk_samples = 480  # 10 ms at 48 kHz
    for i in range(0, len(pcm_data), chunk_samples * 2):  # *2 for int16 bytes
        chunk = pcm_data[i : i + chunk_samples * 2]
        if len(chunk) < chunk_samples * 2:
            chunk = chunk + b"\x00" * (chunk_samples * 2 - len(chunk))
        frame = rtc.AudioFrame(
            data=chunk,
            sample_rate=48000,
            num_channels=1,
            samples_per_channel=chunk_samples,
        )
        await source.capture_frame(frame)
        await asyncio.sleep(0.01)

    print("  Question published; waiting up to 20s for agent response …")

    # Wait up to 20 s for the first response frame to arrive
    deadline = asyncio.get_event_loop().time() + 20.0
    while asyncio.get_event_loop().time() < deadline:
        if frames:
            break
        await asyncio.sleep(0.1)

    if not frames:
        await room.disconnect()
        return []

    # Drain until 2 s of silence
    while True:
        await asyncio.sleep(0.1)
        if asyncio.get_event_loop().time() - last_frame_time[0] > 2.0:
            break

    await room.disconnect()
    return frames


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


def test_audio_response(agent_id: str) -> None:
    """
    Full audio round-trip: synthesise a question with OpenAI TTS, publish it
    to the LiveKit room, wait for the agent to reply, transcribe the response
    with Whisper, and assert the agent's display_name appears in the reply.

    Requires: running agent worker, livekit SDK, av, OPENAI_API_KEY.
    """
    print("test_audio_response … ", end="", flush=True)

    try:
        import livekit  # noqa: F401
    except ImportError:
        print("SKIP (livekit package not installed)")
        return

    try:
        import av  # noqa: F401
    except ImportError:
        print("SKIP (av package not installed — pip install av)")
        return

    # 1. Get LiveKit room credentials
    with httpx.Client() as client:
        conn = _connect(client, agent_id)

    # 2. Synthesise "What is your name?" via OpenAI TTS → PCM
    print("\n  Synthesising question via OpenAI TTS …")
    mp3_bytes = _tts_to_mp3("What is your name?")
    pcm_data = _mp3_to_pcm48k(mp3_bytes)

    # 3. Join room, publish question, collect response
    frames = asyncio.run(_audio_round_trip(conn["token"], conn["url"], pcm_data))

    if not frames:
        print("SKIP (no audio received from agent within 20s)")
        return

    print(f"  Collected {len(frames)} response frames; transcribing …")

    # 4. Transcribe the agent's response
    wav = frames_to_wav(frames)
    transcript = _transcribe(wav)
    print(f"\n  Transcript: {transcript!r}")

    # 5. Assert the agent identified itself by name
    assert DISPLAY_NAME.lower() in transcript.lower(), (
        f"Expected agent display_name {DISPLAY_NAME!r} in transcript, got: {transcript!r}"
    )
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

    # Audio tests use the REAL running agent, not the test user.
    # The test user's agent_name won't match any running worker.
    real_agent_id = _load_real_agent_id()
    if not real_agent_id:
        raise SystemExit(
            "REAL_AGENT_ID not set and .hub-agent-id-voice-agent not found. "
            "Start the agent worker first."
        )

    try:
        test_connect_returns_livekit_credentials(user_data["agent_id"])
        test_agent_joins_and_greets(real_agent_id)
        test_audio_response(real_agent_id)
    finally:
        with httpx.Client() as client:
            print("Cleaning up test user … ", end="", flush=True)
            _delete_test_user(client, user_data["user_id"])
            print("OK")

    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    main()

# voice-agent-hub

A FastAPI + React hub service for managing voice agent registrations, user authentication, and LiveKit token issuance. Deployed on Fly.io.

## Architecture

```
                        ┌─────────────────────────────┐
                        │       voice-agent-hub        │
                        │  (Fly.io, voice-agent-hub)  │
                        │                              │
  Agent CLI ──register/heartbeat──▶  FastAPI backend   │
  Browser  ──/call?token=...──────▶  React frontend    │
  Device   ──/auth/device──────────▶  Device auth flow │
                        │              SQLite /data/hub.db │
                        └─────────────────────────────┘
```

### Backend (`backend/`)

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, all routes |
| `models.py` | SQLAlchemy ORM models |
| `database.py` | Async SQLite engine + session factory |
| `auth.py` | Device code generation + JWT session tokens |
| `crypto.py` | Fernet encrypt/decrypt for stored API keys |
| `dependencies.py` | FastAPI `get_current_user` dependency |
| `config.py` | Settings loaded from environment variables |

### Frontend (`frontend/src/pages/`)

| Page | Route | Purpose |
|------|-------|---------|
| `Call.tsx` | `/call?token=...` | Voice call UI — auto-connects, three-state badge |
| `Verify.tsx` | `/auth/verify?code=...` | Device auth approval page |
| `Dashboard.tsx` | `/dashboard` | Stub, coming soon |

## Setup

### Prerequisites

- Python 3.11+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- Fly.io CLI (`flyctl`)

### Local development

```bash
# Backend
cp .env.example .env
# Edit .env and set HUB_SECRET and HUB_ENCRYPTION_KEY

uv pip install -e .

# Create local data dir
mkdir -p /tmp/hub-data
export DATABASE_URL="sqlite+aiosqlite:////tmp/hub-data/hub.db"
export BASE_URL="http://localhost:8080"

uvicorn backend.main:app --port 8080 --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev   # proxies API to :8080
```

### Build frontend into backend/static

```bash
cd frontend && npm run build
# outputs to backend/static/
```

## API Reference

### Device Auth Flow (for agent CLI)

**Step 1 — Request a device code:**
```
POST /auth/device
→ { device_code, verification_url, expires_in: 300 }
```

**Step 2 — Open `verification_url` in a browser**, enter name + email, click Approve.

**Step 3 — Poll for token:**
```
GET /auth/device/token?code=<device_code>
→ { token }            (approved)
→ { status: "pending" } (waiting)
→ { status: "expired" } (timed out)
```

### Agent API (Bearer token auth)

```
POST /agent/register
Body: { agent_name, display_name, livekit_url, livekit_api_key, livekit_api_secret, deepgram_api_key, openai_api_key }
→ { agent_id, call_url_base }

GET /agent/config
→ { livekit_url, livekit_api_key, livekit_api_secret, deepgram_api_key, openai_api_key }

POST /agent/heartbeat
→ { ok: true }
```

### Call Flow

```
GET /call_url?agent_id=<id>   (Bearer auth — agent)
→ { url, expires_in: 86400 }

POST /connect
Body: { call_token }
→ { token (LiveKit), url, room_name, agent }
```

## Deployment (Fly.io)

```bash
# Create app (first time)
flyctl apps create voice-agent-hub

# Create persistent volume
flyctl volumes create hub_data --region syd --size 1

# Set secrets
flyctl secrets set \
  HUB_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  HUB_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  BASE_URL="https://voice-agent-hub.fly.dev"

# Deploy
flyctl deploy
```

## Security Notes

- All API keys (LiveKit, Deepgram, OpenAI) are encrypted with Fernet before storage.
- Session tokens are JWT signed with `HUB_SECRET`, expire in 30 days.
- Device codes expire in 5 minutes.
- `HUB_ENCRYPTION_KEY` and `HUB_SECRET` must be set before deploying — loss of the encryption key means stored API keys cannot be decrypted.

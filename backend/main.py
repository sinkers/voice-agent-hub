import asyncio
import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt as _jwt
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from livekit import api as livekit_api
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import (
    DEVICE_CODE_EXPIRES,
    create_session_token,
    device_code_expiry,
    generate_device_code,
)
from backend.config import settings
from backend.crypto import decrypt, encrypt
from backend.database import get_db, init_db
from backend.dependencies import get_current_user
from backend.models import AgentRegistration, CallLog, DeviceCode, User

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown (if needed in future)


app = FastAPI(title="Voice Agent Hub", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Device auth flow
# ---------------------------------------------------------------------------


class DeviceAuthResponse(BaseModel):
    device_code: str
    verification_url: str
    expires_in: int = int(DEVICE_CODE_EXPIRES.total_seconds())


@app.post("/auth/device", response_model=DeviceAuthResponse)
async def create_device_code(db: AsyncSession = Depends(get_db)):
    code = generate_device_code()
    device = DeviceCode(
        code=code,
        expires_at=device_code_expiry(),
        approved=False,
    )
    db.add(device)
    await db.commit()
    return DeviceAuthResponse(
        device_code=code,
        verification_url=f"{settings.base_url}/auth/verify?code={code}",
        expires_in=int(DEVICE_CODE_EXPIRES.total_seconds()),
    )


@app.get("/auth/device/token")
async def poll_device_token(code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DeviceCode).where(DeviceCode.code == code))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Device code not found")

    now = datetime.now(UTC)
    if device.expires_at.replace(tzinfo=UTC) < now:
        return {"status": "expired"}

    if not device.approved or device.token is None:
        return {"status": "pending"}

    return {"token": device.token}


@app.get("/auth/verify", response_class=HTMLResponse)
async def verify_page(code: str, request: Request):
    import json
    from html import escape

    # Escape for HTML context
    code_html = escape(code)
    # Escape for JavaScript context
    code_js = json.dumps(code)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Connect Voice Agent</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 480px; margin: 80px auto; padding: 0 20px; }}
    h1 {{ font-size: 1.5rem; }}
    .code {{ font-size: 2rem; font-weight: bold; letter-spacing: 0.2em; background: #f0f0f0;
             padding: 12px 24px; border-radius: 8px; display: inline-block; margin: 16px 0; }}
    input {{ width: 100%; padding: 10px; margin: 8px 0; font-size: 1rem; box-sizing: border-box;
             border: 1px solid #ccc; border-radius: 6px; }}
    button {{ width: 100%; padding: 12px; background: #2563eb; color: white; font-size: 1rem;
              border: none; border-radius: 6px; cursor: pointer; margin-top: 8px; }}
    button:hover {{ background: #1d4ed8; }}
    #msg {{ margin-top: 16px; color: green; font-weight: bold; }}
    #err {{ margin-top: 16px; color: red; }}
  </style>
</head>
<body>
  <h1>Connect Voice Agent</h1>
  <p>Your device code:</p>
  <div class="code">{code_html}</div>
  <p>Enter your details to approve this connection:</p>
  <form id="form">
    <input type="text" id="name" placeholder="Your name" required />
    <input type="email" id="email" placeholder="Email address" required />
    <button type="submit">Approve Connection</button>
  </form>
  <div id="msg"></div>
  <div id="err"></div>
  <script>
    document.getElementById('form').addEventListener('submit', async (e) => {{
      e.preventDefault();
      const res = await fetch('/auth/verify', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          code: {code_js},
          name: document.getElementById('name').value,
          email: document.getElementById('email').value,
        }})
      }});
      if (res.ok) {{
        document.getElementById('form').style.display = 'none';
        document.getElementById('msg').textContent = 'You are now connected. You can close this tab.';
      }} else {{
        const data = await res.json();
        document.getElementById('err').textContent = data.detail || 'Error approving code.';
      }}
    }});
  </script>
</body>
</html>"""
    return HTMLResponse(html)


class VerifyBody(BaseModel):
    code: str = Field(..., pattern=r"^[0-9a-f]{32}$", description="32-character hex device code")
    email: EmailStr = Field(..., description="Valid email address")
    name: str = Field(..., min_length=1, max_length=255, description="User's display name")

    @field_validator("name")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


@app.post("/auth/verify")
async def verify_device(body: VerifyBody, db: AsyncSession = Depends(get_db)):
    logger.info(f"Device verification attempt for code {body.code[:8]}... by {body.email}")
    result = await db.execute(select(DeviceCode).where(DeviceCode.code == body.code))
    device = result.scalar_one_or_none()
    if device is None:
        logger.warning(f"Device code not found: {body.code[:8]}...")
        raise HTTPException(status_code=404, detail="Device code not found")

    now = datetime.now(UTC)
    if device.expires_at.replace(tzinfo=UTC) < now:
        logger.warning(f"Device code expired: {body.code[:8]}...")
        raise HTTPException(status_code=400, detail="Device code expired")

    if device.approved:
        logger.warning(f"Device code already approved: {body.code[:8]}...")
        raise HTTPException(status_code=400, detail="Already approved")

    # Find or create user
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(id=str(uuid.uuid4()), email=body.email, name=body.name)
        db.add(user)
        await db.flush()
        logger.info(f"Created new user: {body.email}")
    elif not user.name and body.name:
        user.name = body.name

    token = create_session_token(user.id)
    device.user_id = user.id
    device.approved = True
    device.token = token

    await db.commit()
    logger.info(f"Device verification successful for {body.email}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Agent API
# ---------------------------------------------------------------------------


class RegisterBody(BaseModel):
    agent_name: str
    display_name: str
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    deepgram_api_key: str
    openai_api_key: str


@app.post("/agent/register")
async def register_agent(
    body: RegisterBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"Agent registration attempt: {body.agent_name} by user {current_user.email}")
    result = await db.execute(
        select(AgentRegistration).where(
            AgentRegistration.user_id == current_user.id,
            AgentRegistration.agent_name == body.agent_name,
        )
    )
    reg = result.scalar_one_or_none()

    if reg is None:
        logger.info(f"Creating new agent registration: {body.agent_name}")
        reg = AgentRegistration(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            agent_name=body.agent_name,
            display_name=body.display_name,
            livekit_url=body.livekit_url,
            livekit_api_key=encrypt(body.livekit_api_key),
            livekit_api_secret=encrypt(body.livekit_api_secret),
            deepgram_api_key=encrypt(body.deepgram_api_key),
            openai_api_key=encrypt(body.openai_api_key),
        )
        db.add(reg)
    else:
        logger.info(f"Updating existing agent registration: {body.agent_name}")
        reg.display_name = body.display_name
        reg.livekit_url = body.livekit_url
        reg.livekit_api_key = encrypt(body.livekit_api_key)
        reg.livekit_api_secret = encrypt(body.livekit_api_secret)
        reg.deepgram_api_key = encrypt(body.deepgram_api_key)
        reg.openai_api_key = encrypt(body.openai_api_key)

    try:
        await db.commit()
        await db.refresh(reg)
        logger.info(f"Agent registration successful: {body.agent_name} (id: {reg.id})")
    except Exception as e:
        logger.error(f"Agent registration failed for {body.agent_name}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to register agent: {str(e)}"
        ) from e

    call_url_base = f"{settings.base_url}/call?agent_id={reg.id}"
    return {"agent_id": reg.id, "call_url_base": call_url_base}


@app.get("/agent/config")
async def agent_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentRegistration)
        .where(AgentRegistration.user_id == current_user.id)
        .order_by(AgentRegistration.created_at.desc())
        .limit(1)
    )
    reg = result.scalar_one_or_none()
    if reg is None:
        raise HTTPException(status_code=404, detail="No agent registered")

    return {
        "display_name": reg.display_name,
        "livekit_url": reg.livekit_url,
        "livekit_api_key": decrypt(reg.livekit_api_key),
        "livekit_api_secret": decrypt(reg.livekit_api_secret),
        "deepgram_api_key": decrypt(reg.deepgram_api_key),
        "openai_api_key": decrypt(reg.openai_api_key),
    }


@app.post("/agent/heartbeat")
async def heartbeat(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentRegistration).where(AgentRegistration.user_id == current_user.id)
    )
    reg = result.scalar_one_or_none()
    if reg is not None:
        reg.last_seen = datetime.now(UTC)
        await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Call flow
# ---------------------------------------------------------------------------


class ConnectBody(BaseModel):
    agent_id: str


async def _dispatch_agent(lk_url: str, lk_key: str, lk_secret: str,
                           agent_name: str, room_name: str) -> None:
    """Dispatch agent after a short delay so the caller can join first."""
    # Validate all required parameters
    if not all([lk_url, lk_key, lk_secret, agent_name, room_name]):
        logger.error(
            f"Invalid credentials for agent dispatch to {room_name}: "
            f"url={bool(lk_url)}, key={bool(lk_key)}, secret={bool(lk_secret)}, "
            f"agent={bool(agent_name)}"
        )
        return

    try:
        await asyncio.sleep(1.5)
        async with livekit_api.LiveKitAPI(url=lk_url, api_key=lk_key, api_secret=lk_secret) as lk:
            await lk.agent_dispatch.create_dispatch(
                livekit_api.CreateAgentDispatchRequest(
                    agent_name=agent_name,
                    room=room_name,
                )
            )
        logger.info(f"Agent {agent_name} dispatched to room {room_name}")
    except Exception as e:
        logger.error(f"Agent dispatch failed for {room_name}: {e}", exc_info=True)


@app.post("/connect")
async def connect(body: ConnectBody, background_tasks: BackgroundTasks,
                  db: AsyncSession = Depends(get_db)):
    agent_id = body.agent_id
    logger.info(f"Connect request for agent {agent_id}")

    result = await db.execute(
        select(AgentRegistration).where(AgentRegistration.id == agent_id)
    )
    reg = result.scalar_one_or_none()
    if reg is None:
        logger.error(f"Connect failed: agent not found {agent_id}")
        raise HTTPException(status_code=404, detail="Agent not found")

    room_name = f"call-{secrets.token_hex(8)}"
    logger.info(f"Created room {room_name} for agent {reg.agent_name}")

    # Issue LiveKit participant token
    lk_key = decrypt(reg.livekit_api_key)
    lk_secret = decrypt(reg.livekit_api_secret)
    lk_url = reg.livekit_url

    token = livekit_api.AccessToken(lk_key, lk_secret)
    token.with_identity("caller")
    token.with_name("Caller")
    token.with_grants(livekit_api.VideoGrants(room_join=True, room=room_name))
    lk_token = token.to_jwt()

    # Dispatch agent after response is sent so caller can join the room first.
    # 1.5s delay ensures the caller has connected before the agent arrives.
    background_tasks.add_task(
        _dispatch_agent, lk_url, lk_key, lk_secret, reg.agent_name, room_name
    )

    # Log the call
    log = CallLog(
        id=str(uuid.uuid4()),
        agent_id=reg.id,
        user_id=None,
        room_name=room_name,
    )
    db.add(log)
    await db.commit()

    return {
        "token": lk_token,
        "url": reg.livekit_url,
        "room_name": room_name,
        "agent": reg.display_name,
    }


@app.get("/call_url")
async def get_call_url(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentRegistration).where(
            AgentRegistration.id == agent_id,
            AgentRegistration.user_id == current_user.id,
        )
    )
    reg = result.scalar_one_or_none()
    if reg is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    call_token = _jwt.encode(
        {
            "sub": current_user.id,
            "agent_id": agent_id,
            "exp": datetime.now(UTC) + timedelta(hours=24),
        },
        settings.hub_secret,
        algorithm="HS256",
    )
    url = f"{settings.base_url}/call?token={call_token}"
    return {"url": url, "expires_in": 86400}


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


def _require_hub_secret(x_hub_secret: str = Header(default="")) -> None:
    if not x_hub_secret or x_hub_secret != settings.hub_secret:
        raise HTTPException(status_code=403, detail="Forbidden")


class TestUserBody(BaseModel):
    email: str
    agent_name: str
    display_name: str
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    deepgram_api_key: str
    openai_api_key: str


@app.post("/admin/test-user")
async def create_test_user(
    body: TestUserBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_hub_secret),
):
    user = User(id=str(uuid.uuid4()), email=body.email, name="Integration Test")
    db.add(user)
    await db.flush()

    reg = AgentRegistration(
        id=str(uuid.uuid4()),
        user_id=user.id,
        agent_name=body.agent_name,
        display_name=body.display_name,
        livekit_url=body.livekit_url,
        livekit_api_key=encrypt(body.livekit_api_key),
        livekit_api_secret=encrypt(body.livekit_api_secret),
        deepgram_api_key=encrypt(body.deepgram_api_key),
        openai_api_key=encrypt(body.openai_api_key),
    )
    db.add(reg)
    await db.commit()

    token = create_session_token(user.id)
    call_url_base = f"{settings.base_url}/call?agent_id={reg.id}"
    return {
        "user_id": user.id,
        "token": token,
        "agent_id": reg.id,
        "call_url_base": call_url_base,
    }


@app.delete("/admin/test-user/{user_id}")
async def delete_test_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_hub_secret),
):
    logger.warning(f"Admin operation: deleting test user {user_id}")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        logger.error(f"Admin delete failed: user not found {user_id}")
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    logger.info(f"Admin operation successful: deleted user {user_id}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Dashboard stub
# ---------------------------------------------------------------------------


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(
        "<html><body><h1>Dashboard coming soon</h1></body></html>"
    )


# ---------------------------------------------------------------------------
# Serve React static build (fallback SPA routing)
# ---------------------------------------------------------------------------

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        file_path = STATIC_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        raise HTTPException(status_code=404, detail="Not found")

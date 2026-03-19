import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    google_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    registrations: Mapped[list["AgentRegistration"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    device_codes: Mapped[list["DeviceCode"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AgentRegistration(Base):
    __tablename__ = "agent_registrations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    livekit_url: Mapped[str] = mapped_column(String, nullable=False)
    livekit_api_key: Mapped[str] = mapped_column(String, nullable=False)  # encrypted
    livekit_api_secret: Mapped[str] = mapped_column(String, nullable=False)  # encrypted
    deepgram_api_key: Mapped[str] = mapped_column(String, nullable=False)  # encrypted
    openai_api_key: Mapped[str] = mapped_column(String, nullable=False)  # encrypted
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="registrations")
    call_logs: Mapped[list["CallLog"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )


class DeviceCode(Base):
    __tablename__ = "device_codes"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    token: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped["User | None"] = relationship(back_populates="device_codes")


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agent_registrations.id"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    room_name: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    agent: Mapped["AgentRegistration"] = relationship(back_populates="call_logs")

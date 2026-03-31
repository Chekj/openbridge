"""Session management for OpenBridge."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from enum import Enum

import structlog

logger = structlog.get_logger()


class SessionStatus(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"


@dataclass
class UserSession:
    session_id: str
    user_id: str
    platform: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    status: SessionStatus = SessionStatus.ACTIVE
    metadata: dict[str, Any] = field(default_factory=dict)
    _activity_callbacks: list[Callable[[], None]] = field(default_factory=list, repr=False)
    # App mode tracking
    current_app: str = field(default="terminal")
    app_context: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.last_activity = time.time()
        self.status = SessionStatus.ACTIVE
        for callback in self._activity_callbacks:
            try:
                callback()
            except Exception:
                pass

    def add_activity_callback(self, callback: Callable[[], None]) -> None:
        self._activity_callbacks.append(callback)

    def is_expired(self, timeout_seconds: float) -> bool:
        return time.time() - self.last_activity > timeout_seconds

    def close(self) -> None:
        self.status = SessionStatus.CLOSED


class SessionManager:
    def __init__(self, session_timeout: float = 3600.0):
        self._sessions: dict[str, UserSession] = {}
        self._user_sessions: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()
        self.session_timeout = session_timeout
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("session_manager_started")

    async def stop(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        async with self._lock:
            for session in self._sessions.values():
                session.close()
            self._sessions.clear()
            self._user_sessions.clear()
        logger.info("session_manager_stopped")

    async def create_session(
        self, user_id: str, platform: str, metadata: Optional[dict] = None
    ) -> UserSession:
        async with self._lock:
            session_id = str(uuid.uuid4())
            session = UserSession(
                session_id=session_id, user_id=user_id, platform=platform, metadata=metadata or {}
            )
            self._sessions[session_id] = session
            if user_id not in self._user_sessions:
                self._user_sessions[user_id] = set()
            self._user_sessions[user_id].add(session_id)
            logger.info(
                "session_created", session_id=session_id, user_id=user_id, platform=platform
            )
            return session

    def get_session(self, session_id: str) -> Optional[UserSession]:
        session = self._sessions.get(session_id)
        if session:
            session.touch()
        return session

    def get_user_sessions(self, user_id: str) -> list[UserSession]:
        session_ids = self._user_sessions.get(user_id, set())
        sessions = []
        for sid in list(session_ids):
            session = self._sessions.get(sid)
            if session:
                sessions.append(session)
                session.touch()
        return sessions

    async def close_session(self, session_id: str) -> bool:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.close()
                if session.user_id in self._user_sessions:
                    self._user_sessions[session.user_id].discard(session_id)
                logger.info("session_closed", session_id=session_id)
                return True
            return False

    async def close_user_sessions(self, user_id: str) -> int:
        async with self._lock:
            session_ids = list(self._user_sessions.get(user_id, set()))
            closed = 0
            for sid in session_ids:
                session = self._sessions.pop(sid, None)
                if session:
                    session.close()
                    closed += 1
            self._user_sessions.pop(user_id, None)
            logger.info("user_sessions_closed", user_id=user_id, count=closed)
            return closed

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(60)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("cleanup_error", error=str(e))

    async def _cleanup_expired(self) -> None:
        async with self._lock:
            expired = []
            for session_id, session in self._sessions.items():
                if session.is_expired(self.session_timeout):
                    expired.append(session_id)
            for session_id in expired:
                session = self._sessions.pop(session_id, None)
                if session:
                    session.close()
                    if session.user_id in self._user_sessions:
                        self._user_sessions[session.user_id].discard(session_id)
            if expired:
                logger.info("expired_sessions_cleaned", count=len(expired))

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_sessions": len(self._sessions),
            "unique_users": len(self._user_sessions),
            "sessions_by_platform": self._get_platform_counts(),
        }

    def _get_platform_counts(self) -> dict[str, int]:
        counts = {}
        for session in self._sessions.values():
            platform = session.platform
            counts[platform] = counts.get(platform, 0) + 1
        return counts

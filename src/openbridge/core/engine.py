"""Core PTY-based command execution engine."""

from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import select
import struct
import termios
from dataclasses import dataclass, field
from typing import Callable, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class PTYSession:
    """Represents a PTY session."""

    session_id: str
    master_fd: int
    slave_fd: int
    pid: int
    cwd: str = field(default_factory=os.getcwd)
    env: dict = field(default_factory=lambda: dict(os.environ))
    output_buffer: str = field(default="")
    active: bool = field(default=True)
    _read_task: Optional[asyncio.Task] = None
    _output_callbacks: list[Callable[[str], None]] = field(default_factory=list)

    def add_output_callback(self, callback: Callable[[str], None]) -> None:
        self._output_callbacks.append(callback)

    def remove_output_callback(self, callback: Callable[[str], None]) -> None:
        if callback in self._output_callbacks:
            self._output_callbacks.remove(callback)

    def _notify_output(self, data: str) -> None:
        for callback in self._output_callbacks:
            try:
                callback(data)
            except Exception:
                pass

    async def start_reading(self) -> None:
        self._read_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            while self.active:
                readable, _, _ = select.select([self.master_fd], [], [], 0.1)
                if readable:
                    try:
                        data = os.read(self.master_fd, 8192)
                        if data:
                            decoded = data.decode("utf-8", errors="replace")
                            self.output_buffer += decoded
                            self._notify_output(decoded)
                        else:
                            break
                    except OSError:
                        break
        except Exception as e:
            logger.error("pty_read_error", session_id=self.session_id, error=str(e))
        finally:
            self.active = False

    def write(self, data: str) -> None:
        if self.active:
            try:
                os.write(self.master_fd, data.encode("utf-8"))
            except OSError as e:
                logger.error("pty_write_error", session_id=self.session_id, error=str(e))

    def resize(self, rows: int, cols: int) -> None:
        try:
            struct_size = struct.pack("HH", rows, cols)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, struct_size)
        except OSError as e:
            logger.error("pty_resize_error", session_id=self.session_id, error=str(e))

    def terminate(self) -> None:
        self.active = False
        if self._read_task:
            self._read_task.cancel()
        try:
            os.close(self.master_fd)
        except OSError:
            pass
        try:
            os.close(self.slave_fd)
        except OSError:
            pass
        try:
            os.kill(self.pid, 15)
        except (OSError, ProcessLookupError):
            pass
        logger.info("pty_session_terminated", session_id=self.session_id)


class PTYManager:
    def __init__(self):
        self._sessions: dict[str, PTYSession] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        session_id: str,
        shell: Optional[str] = None,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
    ) -> PTYSession:
        async with self._lock:
            if session_id in self._sessions:
                await self.close_session(session_id)

            master_fd, slave_fd = pty.openpty()
            pid = os.fork()

            if pid == 0:
                os.close(master_fd)
                os.setsid()
                os.dup2(slave_fd, 0)
                os.dup2(slave_fd, 1)
                os.dup2(slave_fd, 2)
                if slave_fd > 2:
                    os.close(slave_fd)
                if cwd:
                    os.chdir(cwd)
                if env:
                    os.environ.update(env)
                shell = shell or os.environ.get("SHELL", "/bin/bash")
                os.execlp(shell, shell)
            else:
                os.close(slave_fd)
                session = PTYSession(
                    session_id=session_id,
                    master_fd=master_fd,
                    slave_fd=slave_fd,
                    pid=pid,
                    cwd=cwd or os.getcwd(),
                    env=env or dict(os.environ),
                )
                await session.start_reading()
                self._sessions[session_id] = session
                logger.info("pty_session_created", session_id=session_id, pid=pid)
                return session

    def get_session(self, session_id: str) -> Optional[PTYSession]:
        return self._sessions.get(session_id)

    async def close_session(self, session_id: str) -> bool:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.terminate()
                logger.info("pty_session_closed", session_id=session_id)
                return True
            return False

    async def close_all_sessions(self) -> None:
        async with self._lock:
            for session_id, session in list(self._sessions.items()):
                session.terminate()
                logger.info("pty_session_closed", session_id=session_id)
            self._sessions.clear()

    def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())


class BridgeEngine:
    def __init__(self):
        self.pty_manager = PTYManager()
        self._command_hooks: list[Callable[[str, str], Optional[str]]] = []

    def add_command_hook(self, hook: Callable[[str, str], Optional[str]]) -> None:
        self._command_hooks.append(hook)

    async def execute_command(
        self, session_id: str, command: str, cwd: Optional[str] = None, env: Optional[dict] = None
    ) -> PTYSession:
        for hook in self._command_hooks:
            result = hook(session_id, command)
            if result is None:
                raise PermissionError(f"Command blocked: {command}")
            command = result

        session = self.pty_manager.get_session(session_id)
        if not session:
            session = await self.pty_manager.create_session(session_id, cwd=cwd, env=env)
            await asyncio.sleep(0.1)

        if command.strip():
            session.write(command + "\n")

        return session

    async def send_input(self, session_id: str, data: str) -> None:
        session = self.pty_manager.get_session(session_id)
        if session:
            session.write(data)

    async def resize_terminal(self, session_id: str, rows: int, cols: int) -> None:
        session = self.pty_manager.get_session(session_id)
        if session:
            session.resize(rows, cols)

    async def get_output(self, session_id: str, clear: bool = True) -> Optional[str]:
        session = self.pty_manager.get_session(session_id)
        if not session:
            return None
        output = session.output_buffer
        if clear:
            session.output_buffer = ""
        return output

    async def close_session(self, session_id: str) -> bool:
        return await self.pty_manager.close_session(session_id)

    async def close_all(self) -> None:
        await self.pty_manager.close_all_sessions()

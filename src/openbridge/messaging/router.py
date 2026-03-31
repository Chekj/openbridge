"""Message router for routing messages between adapters and core."""

from __future__ import annotations

import asyncio
from typing import Any

from openbridge.adapters.base import BaseAdapter, UserMessage, BotResponse, MessageType
from openbridge.core.engine import BridgeEngine
from openbridge.core.session import SessionManager
from openbridge.messaging.bus import MessageBus
import structlog

logger = structlog.get_logger()


class MessageRouter:
    def __init__(self, engine: BridgeEngine, session_manager: SessionManager, bus: MessageBus):
        self.engine = engine
        self.session_manager = session_manager
        self.bus = bus
        self._adapters: dict[str, BaseAdapter] = {}

    def register_adapter(self, name: str, adapter: BaseAdapter) -> None:
        adapter.set_message_handler(self._handle_user_message)
        self._adapters[name] = adapter
        logger.info("adapter_registered", name=name)

    async def _handle_user_message(self, message: UserMessage) -> None:
        user_id = message.user_id
        platform = message.platform

        # Get or create session
        session_id = f"{platform}:{user_id}"
        session = self.session_manager.get_session(session_id)

        if not session:
            session = await self.session_manager.create_session(
                user_id=user_id, platform=platform, metadata={"session_id": session_id}
            )

        # Handle command
        content = message.content.strip()

        if content.startswith("/"):
            await self._handle_command(message, session_id)
        else:
            await self._handle_shell_command(message, session_id)

    async def _handle_command(self, message: UserMessage, session_id: str) -> None:
        content = message.content.strip()
        platform = message.platform
        user_id = message.user_id

        if content == "/help":
            response = BotResponse(
                content="""Available commands:
/help - Show this help
/cancel - Cancel current operation
/resize <rows> <cols> - Resize terminal
/status - Show session status

Or type any shell command to execute it."""
            )
        elif content == "/cancel":
            await self.engine.send_input(session_id, "\x03")  # Ctrl+C
            response = BotResponse(content="Sent Ctrl+C to terminal")
        elif content.startswith("/resize"):
            parts = content.split()
            if len(parts) == 3:
                try:
                    rows, cols = int(parts[1]), int(parts[2])
                    await self.engine.resize_terminal(session_id, rows, cols)
                    response = BotResponse(content=f"Terminal resized to {rows}x{cols}")
                except ValueError:
                    response = BotResponse(content="Usage: /resize <rows> <cols>")
            else:
                response = BotResponse(content="Usage: /resize <rows> <cols>")
        elif content == "/status":
            sessions = self.session_manager.get_user_sessions(session_id)
            status = f"Active sessions: {len(sessions)}"
            response = BotResponse(content=status)
        else:
            response = BotResponse(content=f"Unknown command: {content}")

        await self._send_response(platform, user_id, response)

    async def _handle_shell_command(self, message: UserMessage, session_id: str) -> None:
        user_id = message.user_id
        platform = message.platform
        command = message.content

        # Setup output callback
        output_buffer = []

        def output_callback(data: str):
            output_buffer.append(data)

        try:
            # Execute command
            session = await self.engine.execute_command(session_id, command)
            session.add_output_callback(output_callback)

            # Wait a bit for initial output
            await asyncio.sleep(0.5)

            # Get output
            output = await self.engine.get_output(session_id, clear=True)

            # Format and send response
            if output:
                formatted = self._format_for_platform(output, platform)
                response = BotResponse(content=formatted)
                await self._send_response(platform, user_id, response)
            else:
                # Check if process is still running
                await asyncio.sleep(1.0)
                output = await self.engine.get_output(session_id, clear=True)
                if output:
                    formatted = self._format_for_platform(output, platform)
                    response = BotResponse(content=formatted)
                    await self._send_response(platform, user_id, response)

        except PermissionError as e:
            response = BotResponse(content=f"Command blocked: {e}")
            await self._send_response(platform, user_id, response)
        except Exception as e:
            logger.error("command_error", session_id=session_id, error=str(e))
            response = BotResponse(content=f"Error: {e}")
            await self._send_response(platform, user_id, response)
        finally:
            # Remove callback
            session = self.engine.pty_manager.get_session(session_id)
            if session:
                session.remove_output_callback(output_callback)

    def _format_for_platform(self, output: str, platform: str) -> str:
        # Truncate if too long
        max_length = 4000 if platform == "telegram" else 2000
        if len(output) > max_length:
            output = output[:max_length] + "\n... (truncated)"

        # Wrap in code block for Telegram
        if platform == "telegram":
            output = f"```\n{output}\n```"

        return output

    async def _send_response(self, platform: str, user_id: str, response: BotResponse) -> None:
        adapter = self._adapters.get(platform)
        if adapter:
            await adapter.send_message(user_id, response)

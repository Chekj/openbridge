"""Message router for routing messages between adapters and core."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from openbridge.adapters.base import BaseAdapter, UserMessage, BotResponse, MessageType
from openbridge.apps import AppRegistry
from openbridge.core.engine import BridgeEngine
from openbridge.core.session import SessionManager, UserSession
from openbridge.messaging.bus import MessageBus
import structlog

logger = structlog.get_logger()


class MessageRouter:
    def __init__(self, engine: BridgeEngine, session_manager: SessionManager, bus: MessageBus):
        self.engine = engine
        self.session_manager = session_manager
        self.bus = bus
        self._adapters: dict[str, BaseAdapter] = {}

        # Initialize app registry
        apps_dir = Path("/etc/openbridge/apps")
        self.app_registry = AppRegistry(apps_dir)

    def register_adapter(self, name: str, adapter: BaseAdapter) -> None:
        adapter.set_message_handler(self._handle_user_message)
        self._adapters[name] = adapter
        logger.info("adapter_registered", name=name)

    async def _handle_user_message(self, message: UserMessage) -> None:
        user_id = message.user_id
        platform = message.platform
        session_id = f"{platform}:{user_id}"

        # Get or create session
        session = self.session_manager.get_session(session_id)
        if not session:
            session = await self.session_manager.create_session(
                user_id=user_id,
                platform=platform,
                metadata={"session_id": session_id},
                session_id=session_id,
            )

        content = message.content.strip()

        # Handle global commands
        if content.startswith("/"):
            # Check for app switching commands
            if content == "/app" or content == "/apps":
                await self._show_app_menu(message, session)
                return
            elif content.startswith("/app "):
                parts = content.split(" ", 1)
                if len(parts) == 2:
                    await self._switch_app(message, session, parts[1])
                else:
                    await self._show_app_menu(message, session)
                return
            elif content == "/close":
                await self._close_app(message, session)
                return

            # Check if we're in app mode
            if session.current_app != "terminal":
                await self._handle_app_command(message, session)
            else:
                await self._handle_terminal_command(message, session)
        else:
            # Regular message - route based on current app
            if session.current_app != "terminal":
                await self._handle_app_message(message, session)
            else:
                await self._handle_shell_command(message, session)

    async def _show_app_menu(self, message: UserMessage, session: UserSession) -> None:
        """Show available apps menu."""
        apps = self.app_registry.list_apps()

        lines = ["📱 OpenBridge Apps\n"]
        lines.append(f"Currently active: {session.current_app}\n")
        lines.append("Available apps:")

        for i, app in enumerate(apps, 1):
            current = " (current)" if app.slug == session.current_app else ""
            lines.append(f"{i}. {app.icon} {app.name}{current}")

        lines.append("\nSwitch with: /app <name>")
        lines.append("Example: /app opencode")

        response = BotResponse(content="\n".join(lines))
        await self._send_response(message.platform, message.user_id, response)

    async def _switch_app(self, message: UserMessage, session: UserSession, app_slug: str) -> None:
        """Switch user to different app."""
        app = self.app_registry.get(app_slug)

        if not app:
            response = BotResponse(
                content=f"❌ App '{app_slug}' not found.\n\nUse /apps to see available apps."
            )
            await self._send_response(message.platform, message.user_id, response)
            return

        # Update session
        session.current_app = app_slug
        session.app_context = {}

        # Get header with context
        header = app.get_header(session.app_context)

        welcome_text = f"{header}\n\nSwitched to {app.name} mode.\n"

        # Add footer with commands
        footer = app.get_footer(session.app_context)
        if footer:
            welcome_text += f"\n{footer}"

        response = BotResponse(content=welcome_text)
        await self._send_response(message.platform, message.user_id, response)

        logger.info("app_switched", user_id=message.user_id, app=app_slug)

    async def _close_app(self, message: UserMessage, session: UserSession) -> None:
        """Close current app and return to terminal."""
        if session.current_app == "terminal":
            response = BotResponse(content="💻 Already in Terminal mode")
        else:
            session.current_app = "terminal"
            session.app_context = {}
            response = BotResponse(
                content="💻 Back to Terminal mode\n\nYou can now use regular shell commands."
            )

        await self._send_response(message.platform, message.user_id, response)

    async def _handle_app_command(self, message: UserMessage, session: UserSession) -> None:
        """Handle command when in app mode."""
        app = self.app_registry.get(session.current_app)
        if not app:
            # App not found, reset to terminal
            session.current_app = "terminal"
            return

        content = message.content.strip()

        # Handle /close
        if content == "/close":
            await self._close_app(message, session)
            return

        # Format command for app
        command = app.format_command(content, session.app_context)

        if not command:
            # Command handled internally (like /close)
            return

        # Execute in PTY
        await self._execute_app_command(message, session, app, command)

    async def _handle_app_message(self, message: UserMessage, session: UserSession) -> None:
        """Handle regular message when in app mode."""
        app = self.app_registry.get(session.current_app)
        if not app:
            session.current_app = "terminal"
            return

        content = message.content.strip()
        command = app.format_command(content, session.app_context)

        await self._execute_app_command(message, session, app, command)

    async def _execute_app_command(
        self, message: UserMessage, session: UserSession, app, command: str
    ) -> None:
        """Execute command in app and send response."""
        user_id = message.user_id
        platform = message.platform
        session_id = f"{platform}:{user_id}"

        # Send "thinking" status
        header = app.get_header(session.app_context)
        thinking_msg = f"{header}\n\n⏳ Processing..."
        await self._send_response(platform, user_id, BotResponse(content=thinking_msg))

        try:
            # Execute command
            pty_session = await self.engine.execute_command(session_id, command)

            # Wait for output (opencode needs 8-10 seconds)
            await asyncio.sleep(8)

            # Get output
            output = await self.engine.get_output(session_id, clear=True)

            if not output:
                # Try waiting a bit more
                await asyncio.sleep(3)
                output = await self.engine.get_output(session_id, clear=True)

            if output:
                # Parse through app
                parsed = app.parse_output(output, session.app_context)

                # Build full response
                header = app.get_header(session.app_context)
                footer = app.get_footer(session.app_context)

                full_response = f"{header}\n\n{parsed}"
                if footer:
                    full_response += f"\n\n{footer}"

                # Format for platform
                formatted = self._format_for_platform(full_response, platform)
                response = BotResponse(content=formatted)
                await self._send_response(platform, user_id, response)
            else:
                # No output
                header = app.get_header(session.app_context)
                footer = app.get_footer(session.app_context)
                no_output = f"{header}\n\n⚠️ No response from {app.name}"
                if footer:
                    no_output += f"\n\n{footer}"
                await self._send_response(platform, user_id, BotResponse(content=no_output))

        except Exception as e:
            logger.error("app_command_error", session_id=session_id, error=str(e))
            header = app.get_header(session.app_context)
            error_msg = f"{header}\n\n❌ Error: {str(e)}"
            await self._send_response(platform, user_id, BotResponse(content=error_msg))

    async def _handle_terminal_command(self, message: UserMessage, session: UserSession) -> None:
        """Handle terminal-specific commands."""
        content = message.content.strip()
        platform = message.platform
        user_id = message.user_id
        session_id = f"{platform}:{user_id}"

        if content == "/help":
            response = BotResponse(
                content="""💻 Terminal Commands:

/help - Show this help
/cancel - Send Ctrl+C to terminal
/resize <rows> <cols> - Resize terminal
/status - Show session status
/app - Show app menu
/app <name> - Switch to app (opencode, terminal)
/close - Exit current app

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
            status = f"💻 Terminal Mode\n\nActive sessions: {len(sessions)}\nCurrent app: {session.current_app}"
            response = BotResponse(content=status)
        else:
            response = BotResponse(content=f"Unknown command: {content}")

        await self._send_response(platform, user_id, response)

    async def _handle_shell_command(self, message: UserMessage, session: UserSession) -> None:
        """Handle regular shell commands in terminal mode."""
        user_id = message.user_id
        platform = message.platform
        session_id = f"{platform}:{user_id}"
        command = message.content

        output_buffer = []

        def output_callback(data: str):
            output_buffer.append(data)

        try:
            pty_session = await self.engine.execute_command(session_id, command)
            pty_session.add_output_callback(output_callback)

            await asyncio.sleep(0.5)
            output = await self.engine.get_output(session_id, clear=True)

            if output:
                formatted = self._format_for_platform(output, platform)
                response = BotResponse(content=formatted)
                await self._send_response(platform, user_id, response)
            else:
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
            pty_session = self.engine.pty_manager.get_session(session_id)
            if pty_session:
                pty_session.remove_output_callback(output_callback)

    def _format_for_platform(self, output: str, platform: str) -> str:
        max_length = 4000 if platform == "telegram" else 2000
        if len(output) > max_length:
            output = output[:max_length] + "\n... (truncated)"

        if platform == "telegram":
            output = f"```\n{output}\n```"

        return output

    async def _send_response(self, platform: str, user_id: str, response: BotResponse) -> None:
        adapter = self._adapters.get(platform)
        if adapter:
            await adapter.send_message(user_id, response)

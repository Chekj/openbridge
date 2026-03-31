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
            session.current_app = "terminal"
            return

        content = message.content.strip()

        # Handle /close
        if content == "/close":
            await self._close_app(message, session)
            return

        # Handle /new - Create new session
        if content == "/new":
            await self._handle_new_session(message, session, app)
            return

        # Handle /sessions - List sessions
        if content == "/sessions":
            await self._handle_list_sessions(message, session, app)
            return

        # Handle /models - List models (placeholder for now)
        if content == "/models":
            await self._handle_list_models(message, session, app)
            return

        # Handle /agent - List agents (placeholder for now)
        if content == "/agent":
            await self._handle_list_agents(message, session, app)
            return

        # Handle /model <provider>:<model> - Switch model
        if content.startswith("/model "):
            parts = content.split(" ", 1)
            if len(parts) == 2:
                await self._handle_switch_model(message, session, app, parts[1])
            else:
                await self._handle_list_models(message, session, app)
            return

        # Handle /session <session_id> - Switch session
        if content.startswith("/session "):
            parts = content.split(" ", 1)
            if len(parts) == 2:
                await self._handle_switch_session(message, session, app, parts[1])
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
            # Check if app has send_message method (serve mode)
            if hasattr(app, "send_message") and callable(getattr(app, "send_message")):
                # Use HTTP API mode
                result = await app.send_message(command, session.app_context)
                parsed = app.parse_output(result, session.app_context)
            else:
                # Use PTY/CLI mode
                pty_session = await self.engine.execute_command(session_id, command)

                # Poll for output with dynamic waiting
                output = ""
                max_wait_time = 120  # Maximum 2 minutes for long tasks
                poll_interval = 0.5
                total_waited = 0
                no_output_count = 0

                while total_waited < max_wait_time:
                    await asyncio.sleep(poll_interval)
                    total_waited += poll_interval

                    # Check for new output
                    new_output = await self.engine.get_output(session_id, clear=True)
                    if new_output:
                        output += new_output
                        no_output_count = 0

                        # Check if we have a complete response (for opencode JSON)
                        if app.slug == "opencode" and self._has_complete_response(output):
                            break
                    else:
                        no_output_count += 1

                        # If no output for 3 seconds and we have some output, we're done
                        if no_output_count >= 6 and output:
                            break

                        # If no output for 10 seconds total, timeout
                        if no_output_count >= 20:
                            break

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

        except Exception as e:
            logger.error("app_command_error", session_id=session_id, error=str(e))
            header = app.get_header(session.app_context)
            error_msg = f"{header}\n\n❌ Error: {str(e)}"
            await self._send_response(platform, user_id, BotResponse(content=error_msg))

    def _has_complete_response(self, output: str) -> bool:
        """Check if OpenCode output has a complete response."""
        # Look for step_finish in the output
        return '"type":"step_finish"' in output or '"type": "step_finish"' in output

    async def _handle_new_session(self, message: UserMessage, session: UserSession, app) -> None:
        """Handle /new command - Create new OpenCode session."""
        platform = message.platform
        user_id = message.user_id

        if hasattr(app, "create_session") and callable(getattr(app, "create_session")):
            try:
                # Create new session
                new_session = await app.create_session(
                    title=f"Session {len(session.app_context.get('sessions', [])) + 1}"
                )
                session_id = new_session.get("id")

                if session_id:
                    # Update context with new session
                    session.app_context["session_id"] = session_id

                    header = app.get_header(session.app_context)
                    response_text = f"{header}\n\n✅ Created new session: {session_id[:12]}...\n\nYou can now start chatting!"
                    footer = app.get_footer(session.app_context)
                    if footer:
                        response_text += f"\n\n{footer}"

                    response = BotResponse(content=response_text)
                else:
                    response = BotResponse(
                        content="❌ Failed to create session: No session ID returned"
                    )
            except Exception as e:
                logger.error("new_session_error", error=str(e))
                response = BotResponse(content=f"❌ Failed to create session: {str(e)}")
        else:
            response = BotResponse(content="❌ This app doesn't support session creation")

        await self._send_response(platform, user_id, response)

    async def _handle_list_sessions(self, message: UserMessage, session: UserSession, app) -> None:
        """Handle /sessions command - List all OpenCode sessions."""
        platform = message.platform
        user_id = message.user_id

        if hasattr(app, "list_sessions") and callable(getattr(app, "list_sessions")):
            try:
                sessions = await app.list_sessions()

                if sessions:
                    lines = ["📋 OpenCode Sessions:"]
                    current_session_id = session.app_context.get("session_id", "")

                    for idx, s in enumerate(sessions[:10], 1):  # Show max 10 sessions
                        sid = s.get("id", "unknown")
                        title = s.get("title", "Untitled")

                        # Mark current session
                        marker = "👉" if sid == current_session_id else "  "
                        sid_short = sid[:12] if len(sid) > 12 else sid

                        lines.append(f"{marker} {idx}. {sid_short}... - {title}")

                    if len(sessions) > 10:
                        lines.append(f"\n... and {len(sessions) - 10} more sessions")

                    lines.append("\n💡 Tip: Use /new to create a new session")

                    header = app.get_header(session.app_context)
                    response_text = header + "\n\n" + "\n".join(lines)
                    footer = app.get_footer(session.app_context)
                    if footer:
                        response_text += f"\n\n{footer}"

                    response = BotResponse(content=response_text)
                else:
                    header = app.get_header(session.app_context)
                    response_text = (
                        f"{header}\n\nNo active sessions found.\n\nUse /new to create one!"
                    )
                    footer = app.get_footer(session.app_context)
                    if footer:
                        response_text += f"\n\n{footer}"
                    response = BotResponse(content=response_text)
            except Exception as e:
                logger.error("list_sessions_error", error=str(e))
                response = BotResponse(content=f"❌ Failed to list sessions: {str(e)}")
        else:
            response = BotResponse(content="❌ This app doesn't support session listing")

        await self._send_response(platform, user_id, response)

    async def _handle_list_models(self, message: UserMessage, session: UserSession, app) -> None:
        """Handle /models command - List available models from API."""
        platform = message.platform
        user_id = message.user_id

        if hasattr(app, "list_models") and callable(getattr(app, "list_models")):
            try:
                models = await app.list_models()

                if models:
                    # Group models by provider
                    providers = {}
                    for model in models:
                        provider_name = model.get("provider_name", "Unknown")
                        if provider_name not in providers:
                            providers[provider_name] = []
                        providers[provider_name].append(model)

                    lines = ["🤖 Available Models by Provider:\n"]

                    for provider_name, provider_models in sorted(providers.items()):
                        lines.append(f"\n📦 {provider_name}:")
                        for idx, model in enumerate(
                            provider_models[:5], 1
                        ):  # Show max 5 per provider
                            model_id = model.get("model_id", "unknown")
                            model_name = model.get("name", model_id)
                            lines.append(f"  {idx}. {model_name}")
                        if len(provider_models) > 5:
                            lines.append(f"  ... and {len(provider_models) - 5} more")

                    lines.append(
                        f"\n💡 Total: {len(models)} models from {len(providers)} providers"
                    )
                    lines.append("\nUse /models to see quick selection or tap a model button above")

                    header = app.get_header(session.app_context)
                    response_text = header + "\n\n" + "\n".join(lines)
                    footer = app.get_footer(session.app_context)
                    if footer:
                        response_text += f"\n\n{footer}"
                else:
                    header = app.get_header(session.app_context)
                    response_text = f"{header}\n\nNo models found or API unavailable.\n\nPopular models:\n• kimi-k2.5\n• gemini-2.5-pro\n• gpt-4o\n• claude-4-sonnet"
                    footer = app.get_footer(session.app_context)
                    if footer:
                        response_text += f"\n\n{footer}"

                response = BotResponse(content=response_text)
            except Exception as e:
                logger.error("list_models_error", error=str(e))
                header = app.get_header(session.app_context)
                response_text = f"{header}\n\n❌ Failed to fetch models: {str(e)}\n\nPopular models:\n• kimi-k2.5\n• gemini-2.5-pro\n• gpt-4o"
                footer = app.get_footer(session.app_context)
                if footer:
                    response_text += f"\n\n{footer}"
                response = BotResponse(content=response_text)
        else:
            header = app.get_header(session.app_context)
            response_text = f"{header}\n\n🤖 Available Models:\n\n• kimi-k2.5 (default)\n• gemini-2.5-pro\n• gpt-4o\n• claude-4-sonnet\n\n💡 This app doesn't support dynamic model listing"
            footer = app.get_footer(session.app_context)
            if footer:
                response_text += f"\n\n{footer}"
            response = BotResponse(content=response_text)

        await self._send_response(platform, user_id, response)

    async def _handle_list_agents(self, message: UserMessage, session: UserSession, app) -> None:
        """Handle /agent command - List available agents (placeholder)."""
        platform = message.platform
        user_id = message.user_id

        header = app.get_header(session.app_context)
        response_text = f"{header}\n\n🕵️ Available Agents:\n\n• build - Code builder and editor\n• ask - Question answering\n• test - Testing and debugging\n\n💡 Agent switching coming soon!"
        footer = app.get_footer(session.app_context)
        if footer:
            response_text += f"\n\n{footer}"

        response = BotResponse(content=response_text)
        await self._send_response(platform, user_id, response)

    async def _handle_switch_model(
        self, message: UserMessage, session: UserSession, app, model_spec: str
    ) -> None:
        """Handle /model <provider>:<model> command - Switch to specific model."""
        platform = message.platform
        user_id = message.user_id

        # Parse model specification
        if ":" in model_spec:
            parts = model_spec.split(":")
            provider_id = parts[0]
            model_id = parts[1]
        else:
            # Default provider
            provider_id = "opencode-go"
            model_id = model_spec

        # Store in context
        session.app_context["current_model_provider"] = provider_id
        session.app_context["current_model_id"] = model_id

        header = app.get_header(session.app_context)
        response_text = f"{header}\n\n🤖 Model switched to: {model_id}\nProvider: {provider_id}\n\nYour next message will use this model."
        footer = app.get_footer(session.app_context)
        if footer:
            response_text += f"\n\n{footer}"

        response = BotResponse(content=response_text)
        await self._send_response(platform, user_id, response)

    async def _handle_switch_session(
        self, message: UserMessage, session: UserSession, app, session_id: str
    ) -> None:
        """Handle /session <session_id> command - Switch to specific session."""
        platform = message.platform
        user_id = message.user_id

        # Update context with new session
        old_session_id = session.app_context.get("session_id", "none")
        session.app_context["session_id"] = session_id

        header = app.get_header(session.app_context)
        response_text = f"{header}\n\n📁 Switched to session: {session_id[:12]}...\n\nPrevious: {old_session_id[:12] if len(old_session_id) > 12 else old_session_id}..."
        footer = app.get_footer(session.app_context)
        if footer:
            response_text += f"\n\n{footer}"

        response = BotResponse(content=response_text)
        await self._send_response(platform, user_id, response)

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
/app - Show app menu
/app <name> - Switch to app (opencode, terminal)
/close - Exit current app
/cancel - Send Ctrl+C to terminal
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

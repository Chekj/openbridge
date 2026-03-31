"""OpenCode app integration."""

import json
import re
from typing import Dict, Any
from openbridge.apps.base import App, AppManifest
import structlog

logger = structlog.get_logger()


class OpenCodeApp(App):
    """OpenCode AI coding assistant integration."""

    def __init__(self, manifest: AppManifest):
        super().__init__(manifest)

    def format_command(self, user_input: str, context: Dict[str, Any]) -> str:
        """Convert user input to opencode CLI command."""
        # Handle app-specific commands
        if user_input == "/new":
            # Create new session
            context["session_id"] = self._generate_session_id()
            return f'opencode run --format json "New session started. Hello!"'

        elif user_input == "/models":
            return "opencode models"

        elif user_input.startswith("/model "):
            # Switch model
            model = user_input.split(" ", 1)[1] if " " in user_input else ""
            return f'opencode run --format json --model {model} "Using model {model}"'

        elif user_input == "/sessions":
            return "opencode session list"

        elif user_input == "/history":
            session_id = context.get("session_id", "")
            if session_id:
                return f"opencode export {session_id}"
            return "echo 'No active session'"

        elif user_input == "/agent":
            return "opencode agent list"

        elif user_input.startswith("/agent "):
            agent = user_input.split(" ", 1)[1] if " " in user_input else ""
            return f'opencode run --format json --agent {agent} "Switched to {agent} agent"'

        elif user_input == "/close":
            return ""  # Handled by router

        # Normal prompt - use JSON format for structured output
        session_id = context.get("session_id", "")
        if session_id:
            return f'opencode run --format json --session {session_id} "{user_input}"'
        else:
            # Create new session implicitly
            return f'opencode run --format json "{user_input}"'

    def parse_output(self, output: str, context: Dict[str, Any]) -> str:
        """Parse opencode JSON output and extract text."""
        if not output.strip():
            return "No response from OpenCode."

        try:
            lines = output.strip().split("\n")
            text_parts = []
            session_info = {}

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                    event_type = event.get("type", "")

                    if event_type == "text":
                        content = event.get("content", "")
                        if content:
                            text_parts.append(content)
                    elif event_type == "step_start":
                        # Optional: could show thinking status
                        pass
                    elif event_type == "step_finish":
                        # Extract session info if available
                        if "session" in event:
                            session_info = event.get("session", {})
                            if "id" in session_info:
                                context["session_id"] = session_info["id"]
                    elif event_type == "error":
                        error_msg = event.get("message", "Unknown error")
                        return f"❌ Error: {error_msg}"

                except json.JSONDecodeError:
                    # Not JSON, treat as plain text
                    text_parts.append(line)

            result = "".join(text_parts)

            # Clean up common artifacts
            result = self._clean_output(result)

            return result if result.strip() else "OpenCode processed your request."

        except Exception as e:
            logger.error("opencode_parse_error", error=str(e), output=output[:200])
            # Fallback to raw output
            return output

    def _clean_output(self, text: str) -> str:
        """Clean up opencode output."""
        # Remove ANSI escape codes
        text = re.sub(r"\x1b\[[0-9;]*m", "", text)

        # Remove common prompts
        text = re.sub(r"^[>\$]\s*", "", text, flags=re.MULTILINE)

        return text.strip()

    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        import uuid

        return f"oc_{uuid.uuid4().hex[:8]}"

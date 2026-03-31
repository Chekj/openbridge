"""OpenCode app integration using serve mode (HTTP API)."""

import json
import re
import httpx
from typing import Dict, Any, Optional
from openbridge.apps.base import App, AppManifest
import structlog

logger = structlog.get_logger()


class OpenCodeApp(App):
    """OpenCode AI coding assistant integration using HTTP API."""

    def __init__(self, manifest: AppManifest):
        super().__init__(manifest)
        self.base_url = "http://localhost:4096"
        self.password = "openbridge123"  # Password for Basic Auth
        self.api_client: Optional[httpx.AsyncClient] = None
        self.server_process = None

    async def start_server(self):
        """Start opencode serve if not running."""
        import subprocess
        import asyncio

        # Check if server is already running
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/health", auth=("opencode", self.password), timeout=2.0
                )
                if response.status_code == 200:
                    logger.info("opencode_server_already_running")
                    return
        except:
            pass

        # Start server
        logger.info("starting_opencode_server")
        env = {
            "HOME": "/root",
            "OPENCODE_SERVER_PASSWORD": self.password,
            "PATH": "/root/.opencode/bin:/usr/local/bin:/usr/bin:/bin",
        }

        self.server_process = subprocess.Popen(
            ["opencode", "serve", "--port", "4096", "--hostname", "127.0.0.1"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd="/opt/openbridge",
        )

        # Wait for server to be ready
        await asyncio.sleep(3)

        # Verify server is running
        for _ in range(10):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self.base_url}/health", auth=("opencode", self.password), timeout=2.0
                    )
                    if response.status_code == 200:
                        logger.info("opencode_server_started")
                        return
            except:
                pass
            await asyncio.sleep(1)

        logger.error("opencode_server_failed_to_start")

    def format_command(self, user_input: str, context: Dict[str, Any]) -> str:
        """In serve mode, we don't use CLI commands - handled via HTTP."""
        # Just return the user input - actual sending is done via HTTP
        return user_input

    async def send_message(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Send message to OpenCode via HTTP API."""
        await self.start_server()

        # Get or create session
        session_id = context.get("session_id")

        async with httpx.AsyncClient() as client:
            if not session_id:
                # Create new session
                response = await client.post(
                    f"{self.base_url}/v1/sessions",
                    json={"message": message},
                    auth=("opencode", self.password),
                    timeout=60.0,
                )
            else:
                # Continue existing session
                response = await client.post(
                    f"{self.base_url}/v1/sessions/{session_id}/messages",
                    json={"message": message},
                    auth=("opencode", self.password),
                    timeout=60.0,
                )

            if response.status_code == 200:
                data = response.json()
                # Extract session ID from response
                if "session" in data and "id" in data["session"]:
                    context["session_id"] = data["session"]["id"]
                return data
            else:
                logger.error("opencode_api_error", status=response.status_code, body=response.text)
                return {"error": f"API Error: {response.status_code}"}

    def parse_output(self, output: Any, context: Dict[str, Any]) -> str:
        """Parse OpenCode HTTP API response."""
        if "error" in output:
            return f"❌ Error: {output['error']}"

        # Extract text from response parts
        text_parts = []

        if "parts" in output:
            for part in output["parts"]:
                if part.get("type") == "text":
                    text_parts.append(part.get("text", ""))

        if "messages" in output and len(output["messages"]) > 0:
            # Get the last message
            last_msg = output["messages"][-1]
            if "parts" in last_msg:
                for part in last_msg["parts"]:
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))

        result = "".join(text_parts)
        result = self._clean_output(result)

        return result if result.strip() else "OpenCode processed your request."

    def _clean_output(self, text: str) -> str:
        """Clean up opencode output."""
        # Remove ANSI escape codes
        text = re.sub(r"\x1b\[[0-9;]*m", "", text)
        return text.strip()

    async def list_sessions(self) -> list:
        """List all OpenCode sessions via API."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/v1/sessions",
                    headers={"Authorization": "Bearer openbridge"},
                    timeout=10.0,
                )
                if response.status_code == 200:
                    return response.json().get("sessions", [])
        except Exception as e:
            logger.error("opencode_list_sessions_error", error=str(e))
        return []

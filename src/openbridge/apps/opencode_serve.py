"""OpenCode app integration using serve mode (HTTP API)."""

import json
import os
import re
import asyncio
import requests
from typing import Dict, Any, Optional
from openbridge.apps.base import App, AppManifest
import structlog

logger = structlog.get_logger()


class OpenCodeServeApp(App):
    """OpenCode AI coding assistant integration using HTTP API."""

    def __init__(self, manifest: AppManifest):
        super().__init__(manifest)
        self.base_url = "http://127.0.0.1:4096"
        self.password = os.environ.get("OPENCODE_SERVER_PASSWORD", "openbridge123")
        self.username = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
        self.server_process = None
        self._session = requests.Session()
        self._session.auth = (self.username, self.password)

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make HTTP request with auth."""
        url = f"{self.base_url}{path}"
        timeout = kwargs.pop("timeout", 300)
        return self._session.request(method, url, timeout=timeout, **kwargs)

    async def ensure_server_running(self):
        """Start opencode serve if not running."""
        import subprocess

        # Check if server is already running (use sync request in async context)
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._request("GET", "/global/health", timeout=2)
            )
            if response.status_code == 200:
                logger.info("opencode_server_already_running")
                return
        except Exception as e:
            logger.debug("opencode_server_check_failed", error=str(e))

        # Start server
        logger.info("starting_opencode_server", port=4096)
        env = os.environ.copy()
        env["OPENCODE_SERVER_PASSWORD"] = self.password
        env["OPENCODE_SERVER_USERNAME"] = self.username

        self.server_process = subprocess.Popen(
            ["/root/.opencode/bin/opencode", "serve", "--port", "4096", "--hostname", "127.0.0.1"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd="/opt/openbridge",
        )

        # Wait for server to be ready
        await asyncio.sleep(2)

        # Verify server is running
        for i in range(30):
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None, lambda: self._request("GET", "/global/health", timeout=2)
                )
                if response.status_code == 200:
                    try:
                        data = response.json()
                        logger.info("opencode_server_started", version=data.get("version"))
                        return
                    except Exception as e:
                        logger.debug("opencode_server_health_json_error", error=str(e))
            except Exception as e:
                logger.debug("opencode_server_not_ready", attempt=i + 1, error=str(e))
            await asyncio.sleep(1)

        raise RuntimeError("OpenCode server failed to start after 30 seconds")

    async def list_sessions(self) -> list:
        """List all OpenCode sessions via API."""
        await self.ensure_server_running()
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self._request("GET", "/session"))
            if response.status_code == 200:
                try:
                    sessions = response.json()
                    logger.info("opencode_list_sessions", count=len(sessions))
                    return sessions
                except Exception as e:
                    logger.error("opencode_list_sessions_json_error", error=str(e))
                    return []
            else:
                logger.error(
                    "opencode_list_sessions_failed",
                    status=response.status_code,
                    body=response.text[:200],
                )
        except Exception as e:
            logger.error("opencode_list_sessions_error", error=str(e))
        return []

    async def list_models(self) -> list:
        """List available models from OpenCode API."""
        await self.ensure_server_running()
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self._request("GET", "/provider"))
            if response.status_code == 200:
                try:
                    data = response.json()
                    # Extract models from providers
                    models = []
                    providers = data.get("all", [])
                    for provider in providers:
                        provider_id = provider.get("id", "unknown")
                        provider_models = provider.get("models", [])
                        for model in provider_models:
                            models.append(
                                {
                                    "provider_id": provider_id,
                                    "model_id": model.get("id", "unknown"),
                                    "name": model.get("name", "Unknown"),
                                    "provider_name": provider.get("name", provider_id),
                                }
                            )
                    logger.info("opencode_list_models", count=len(models))
                    return models
                except Exception as e:
                    logger.error("opencode_list_models_parse_error", error=str(e))
                    return []
            else:
                logger.error("opencode_list_models_failed", status=response.status_code)
        except Exception as e:
            logger.error("opencode_list_models_error", error=str(e))
        return []

    async def send_message_with_model(
        self, message: str, context: Dict[str, Any], model_provider: str, model_id: str
    ) -> Dict[str, Any]:
        """Send message with specific model."""
        await self.ensure_server_running()

        session_id = context.get("session_id")

        # Create session if needed
        if not session_id:
            logger.info("creating_new_opencode_session")
            session = await self.create_session(title="OpenBridge Session")
            session_id = session.get("id")
            context["session_id"] = session_id
            logger.info("opencode_session_created", session_id=session_id)

        # Store current model in context
        context["current_model_provider"] = model_provider
        context["current_model_id"] = model_id

        # Send message with specific model
        logger.info(
            "sending_opencode_message_with_model",
            session_id=session_id,
            model=f"{model_provider}/{model_id}",
        )
        body = {
            "parts": [{"type": "text", "text": message}],
            "model": {"providerID": model_provider, "modelID": model_id},
        }

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: self._request("POST", f"/session/{session_id}/message", json=body)
        )

        # Check status and handle errors
        if response.status_code != 200:
            error_text = response.text[:500] if response.text else "<empty>"
            logger.error("opencode_api_error", status=response.status_code, body=error_text)
            return {"error": f"API Error {response.status_code}: {error_text}"}

        # Safely parse JSON
        response_text = response.text
        logger.info(
            "opencode_response_received",
            status=response.status_code,
            text_length=len(response_text),
            text_preview=response_text[:100],
        )

        if not response_text:
            logger.error("opencode_empty_response", status=response.status_code)
            return {"error": "Empty response from server"}

        try:
            return response.json()
        except Exception as e:
            logger.error("opencode_json_parse_error", error=str(e), text=response_text[:500])
            return {"error": f"Invalid JSON response: {str(e)}"}

    async def create_session(self, title: Optional[str] = None) -> Dict[str, Any]:
        """Create a new OpenCode session."""
        await self.ensure_server_running()
        body = {}
        if title:
            body["title"] = title

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: self._request("POST", "/session", json=body)
        )

        if response.status_code != 200:
            error_text = response.text[:500] if response.text else "<empty>"
            logger.error(
                "opencode_create_session_error", status=response.status_code, body=error_text
            )
            raise RuntimeError(f"Failed to create session: {response.status_code} - {error_text}")

        response_text = response.text
        if not response_text:
            logger.error("opencode_create_session_empty")
            raise RuntimeError("Empty session response")

        try:
            return response.json()
        except Exception as e:
            logger.error("opencode_session_json_error", error=str(e), text=response_text[:500])
            raise RuntimeError(f"Invalid session response: {str(e)}")

    async def send_message(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Send message to OpenCode via HTTP API."""
        await self.ensure_server_running()

        session_id = context.get("session_id")

        # Create session if needed
        if not session_id:
            logger.info("creating_new_opencode_session")
            session = await self.create_session(title="OpenBridge Session")
            session_id = session.get("id")
            context["session_id"] = session_id
            # Set default model if not already set
            context.setdefault("current_model_provider", "opencode-go")
            context.setdefault("current_model_id", "kimi-k2.5")
            logger.info("opencode_session_created", session_id=session_id)

        # Send message
        logger.info("sending_opencode_message", session_id=session_id)
        body = {"parts": [{"type": "text", "text": message}]}

        loop = asyncio.get_event_loop()
        logger.info(
            "opencode_sending_request", session_id=session_id, url=f"/session/{session_id}/message"
        )
        response = await loop.run_in_executor(
            None, lambda: self._request("POST", f"/session/{session_id}/message", json=body)
        )

        logger.info(
            "opencode_response_raw",
            status=response.status_code,
            headers=dict(response.headers),
            text=response.text[:200] if response.text else "<empty>",
        )

        # Check status and handle errors
        if response.status_code != 200:
            error_text = response.text[:500] if response.text else "<empty>"
            logger.error("opencode_api_error", status=response.status_code, body=error_text)
            return {"error": f"API Error {response.status_code}: {error_text}"}

        # Safely parse JSON
        response_text = response.text
        logger.info(
            "opencode_response_received",
            status=response.status_code,
            text_length=len(response_text),
            text_preview=response_text[:100],
        )

        if not response_text:
            logger.error("opencode_empty_response", status=response.status_code)
            return {"error": "Empty response from server"}

        try:
            return response.json()
        except Exception as e:
            logger.error("opencode_json_parse_error", error=str(e), text=response_text[:500])
            return {"error": f"Invalid JSON response: {str(e)}"}

    def parse_output(self, output: Any, context: Dict[str, Any]) -> str:
        """Parse OpenCode HTTP API response."""
        if isinstance(output, dict) and "error" in output:
            return f"❌ Error: {output['error']}"

        if not isinstance(output, dict):
            return str(output)

        # Extract text from response parts
        text_parts = []

        # Response format: { "info": Message, "parts": Part[] }
        if "parts" in output:
            for part in output["parts"]:
                if part.get("type") == "text":
                    text_parts.append(part.get("text", ""))

        result = "\n".join(text_parts)
        result = self._clean_output(result)

        return result if result.strip() else "OpenCode processed your request."

    def _clean_output(self, text: str) -> str:
        """Clean up opencode output."""
        # Remove ANSI escape codes
        text = re.sub(r"\x1b\[[0-9;]*m", "", text)
        return text.strip()

    def format_command(self, user_input: str, context: Dict[str, Any]) -> str:
        """In serve mode, we don't use CLI commands - handled via HTTP."""
        return user_input

    async def cleanup(self):
        """Cleanup resources."""
        if self._session:
            self._session.close()
        if self.server_process:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except:
                self.server_process.kill()
            self.server_process = None

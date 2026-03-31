"""Main server orchestration."""

from __future__ import annotations

import asyncio
from typing import Optional

import structlog

# Import adapters to register them
from openbridge.adapters import telegram, discord
from openbridge.adapters.registry import create_adapter
from openbridge.config import Config
from openbridge.core.engine import BridgeEngine
from openbridge.core.session import SessionManager
from openbridge.messaging.bus import MessageBus
from openbridge.messaging.router import MessageRouter

logger = structlog.get_logger()


class BridgeServer:
    def __init__(self, config: Config):
        self.config = config
        self.engine = BridgeEngine()
        self.session_manager = SessionManager(config.security.session_timeout)
        self.message_bus = MessageBus()
        self.router = MessageRouter(self.engine, self.session_manager, self.message_bus)
        self._adapters: list = []
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the bridge server."""
        logger.info("server_starting")

        # Ensure directories exist
        self.config.ensure_directories()

        # Start session manager
        await self.session_manager.start()

        # Initialize adapters
        await self._init_adapters()

        self._running = True
        logger.info("server_started")

        # Wait for shutdown
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        """Stop the bridge server."""
        logger.info("server_stopping")

        self._running = False

        # Disconnect all adapters
        for adapter in self._adapters:
            try:
                await adapter.disconnect()
            except Exception as e:
                logger.error("adapter_disconnect_error", adapter=adapter.name, error=str(e))

        # Stop session manager
        await self.session_manager.stop()

        # Close all PTY sessions
        await self.engine.close_all()

        self._shutdown_event.set()
        logger.info("server_stopped")

    async def _init_adapters(self) -> None:
        """Initialize and connect all enabled adapters."""
        for adapter_name, adapter_config in self.config.adapters.items():
            if not getattr(adapter_config, "enabled", False):
                continue

            adapter = create_adapter(adapter_name, adapter_config)
            if adapter:
                self.router.register_adapter(adapter_name, adapter)
                success = await adapter.connect()
                if success:
                    self._adapters.append(adapter)
                    logger.info("adapter_connected", name=adapter_name)
                else:
                    logger.error("adapter_connect_failed", name=adapter_name)
            else:
                logger.error("adapter_not_found", name=adapter_name)

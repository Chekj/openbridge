"""Base adapter interface for messaging platforms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional
from enum import Enum

import structlog

logger = structlog.get_logger()


class MessageType(Enum):
    TEXT = "text"
    COMMAND = "command"
    FILE = "file"
    IMAGE = "image"
    SYSTEM = "system"


@dataclass
class UserMessage:
    message_id: str
    user_id: str
    platform: str
    content: str
    message_type: MessageType
    metadata: dict[str, Any]
    reply_to: Optional[str] = None


@dataclass
class BotResponse:
    content: str
    response_type: MessageType = MessageType.TEXT
    metadata: dict[str, Any] = None
    parse_mode: Optional[str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseAdapter(ABC):
    def __init__(self, config: Any):
        self.config = config
        self.name = self.__class__.__name__.lower().replace("adapter", "")
        self._running = False
        self._message_handler: Optional[Callable[[UserMessage], Any]] = None

    @abstractmethod
    async def connect(self) -> bool:
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        pass

    @abstractmethod
    async def send_message(self, user_id: str, response: BotResponse) -> bool:
        pass

    def set_message_handler(self, handler: Callable[[UserMessage], Any]) -> None:
        self._message_handler = handler

    async def handle_message(self, message: UserMessage) -> None:
        if self._message_handler:
            try:
                await self._message_handler(message)
            except Exception as e:
                logger.error("message_handler_error", platform=self.name, error=str(e))

    @property
    def is_running(self) -> bool:
        return self._running

    def _create_message(self, raw_message: dict) -> Optional[UserMessage]:
        try:
            return self._parse_message(raw_message)
        except Exception as e:
            logger.error("message_parse_error", platform=self.name, error=str(e))
            return None

    @abstractmethod
    def _parse_message(self, raw_message: dict) -> Optional[UserMessage]:
        pass

    @abstractmethod
    def get_user_info(self, user_id: str) -> dict[str, Any]:
        pass

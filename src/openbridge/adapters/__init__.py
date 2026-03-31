"""Adapters for messaging platforms."""

from openbridge.adapters.base import BaseAdapter, UserMessage, BotResponse, MessageType
from openbridge.adapters.registry import register_adapter, create_adapter

__all__ = [
    "BaseAdapter",
    "UserMessage",
    "BotResponse",
    "MessageType",
    "register_adapter",
    "create_adapter",
]

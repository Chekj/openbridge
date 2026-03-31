"""Adapter registry and management."""

from __future__ import annotations

from typing import Any, Type

from openbridge.adapters.base import BaseAdapter
from openbridge.config import Config

ADAPTER_REGISTRY: dict[str, Type[BaseAdapter]] = {}


def register_adapter(name: str):
    def decorator(cls: Type[BaseAdapter]) -> Type[BaseAdapter]:
        ADAPTER_REGISTRY[name.lower()] = cls
        return cls

    return decorator


def get_adapter(name: str) -> Type[BaseAdapter] | None:
    return ADAPTER_REGISTRY.get(name.lower())


def list_adapters() -> list[str]:
    return list(ADAPTER_REGISTRY.keys())


def create_adapter(name: str, config: Any) -> BaseAdapter | None:
    adapter_cls = get_adapter(name)
    if adapter_cls:
        return adapter_cls(config)
    return None

"""Tests for core engine."""

import pytest
import asyncio
from openbridge.core.engine import BridgeEngine, PTYManager


@pytest.mark.asyncio
async def test_pty_manager_create():
    """Test PTY manager creation."""
    manager = PTYManager()
    assert manager.list_sessions() == []


@pytest.mark.asyncio
async def test_bridge_engine_create():
    """Test bridge engine creation."""
    engine = BridgeEngine()
    assert engine.pty_manager is not None

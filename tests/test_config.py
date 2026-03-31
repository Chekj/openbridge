"""Tests for OpenBridge."""

import pytest
from openbridge.config import Config


def test_config_default():
    """Test default configuration."""
    config = Config()
    assert config.server.host == "0.0.0.0"
    assert config.server.port == 8080
    assert config.security.session_timeout == 3600


def test_config_from_env():
    """Test configuration from environment variables."""
    import os

    os.environ["OB_SERVER_HOST"] = "127.0.0.1"
    os.environ["OB_SERVER_PORT"] = "9000"

    config = Config.from_env()
    assert config.server.host == "127.0.0.1"
    assert config.server.port == 9000

    # Clean up
    del os.environ["OB_SERVER_HOST"]
    del os.environ["OB_SERVER_PORT"]

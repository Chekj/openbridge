"""OpenBridge - Production-grade remote CLI bridge for mobile devices."""

__version__ = "0.1.0"
__author__ = "OpenBridge Team"
__license__ = "MIT"

from openbridge.config import Config
from openbridge.core.engine import BridgeEngine
from openbridge.core.session import SessionManager

__all__ = ["Config", "BridgeEngine", "SessionManager"]

"""App system for OpenBridge."""

from openbridge.apps.base import App, AppRegistry, AppManifest
from openbridge.apps.terminal import TerminalApp
from openbridge.apps.opencode_serve import OpenCodeServeApp
from openbridge.apps.generic import GenericCliApp

__all__ = [
    "App",
    "AppRegistry",
    "AppManifest",
    "TerminalApp",
    "OpenCodeServeApp",
    "GenericCliApp",
]

"""Base app system for OpenBridge."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import yaml
import structlog

logger = structlog.get_logger()


@dataclass
class AppManifest:
    """App configuration manifest."""

    name: str
    slug: str
    description: str
    version: str
    icon: str = "📱"
    command: Dict[str, Any] = field(default_factory=dict)
    ui: Dict[str, str] = field(default_factory=dict)
    commands: list = field(default_factory=list)

    @classmethod
    def from_file(cls, path: Path) -> "AppManifest":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)


class App(ABC):
    """Base class for all apps."""

    def __init__(self, manifest: AppManifest):
        self.manifest = manifest
        self.name = manifest.name
        self.slug = manifest.slug
        self.icon = manifest.icon

    @abstractmethod
    def format_command(self, user_input: str, context: Dict[str, Any]) -> str:
        """Convert user input to shell command."""
        pass

    @abstractmethod
    def parse_output(self, output: str, context: Dict[str, Any]) -> str:
        """Parse command output for display."""
        pass

    def get_header(self, context: Dict[str, Any]) -> str:
        """Get message header."""
        header = self.manifest.ui.get("header", f"{self.icon} {self.name}")
        # Replace placeholders
        for key, value in context.items():
            header = header.replace(f"{{{key}}}", str(value))
        # Handle session_id specially if still in template
        if "{session_id}" in header:
            session_id = context.get("session_id", "")
            display_id = session_id[:8] if session_id else "new"
            header = header.replace("{session_id}", display_id)
        return header

    def get_footer(self, context: Dict[str, Any]) -> str:
        """Get message footer."""
        footer = self.manifest.ui.get("footer", "")
        # Build commands list if not specified
        if not footer and self.manifest.commands:
            cmds = " ".join([f"/{cmd['name']}" for cmd in self.manifest.commands])
            footer = f"Commands: {cmds}"
        return footer


class AppRegistry:
    """Registry of all installed apps."""

    def __init__(self, apps_dir: Path):
        self.apps_dir = apps_dir
        self.apps: Dict[str, App] = {}
        self._load_apps()

    def _load_apps(self):
        """Load all app manifests from directory."""
        if not self.apps_dir.exists():
            logger.warning("apps_dir_not_found", path=str(self.apps_dir))
            return

        for manifest_file in self.apps_dir.glob("*.yaml"):
            try:
                manifest = AppManifest.from_file(manifest_file)
                # Create appropriate app instance based on type
                app = self._create_app(manifest)
                if app:
                    self.apps[app.slug] = app
                    logger.info("app_loaded", slug=app.slug, name=app.name)
            except Exception as e:
                logger.error("app_load_failed", file=str(manifest_file), error=str(e))

    def _create_app(self, manifest: AppManifest) -> Optional[App]:
        """Create app instance from manifest."""
        # Import here to avoid circular imports
        from openbridge.apps.terminal import TerminalApp
        from openbridge.apps.opencode_serve import OpenCodeServeApp

        app_type = manifest.command.get("type", "cli")

        if manifest.slug == "terminal":
            return TerminalApp(manifest)
        elif manifest.slug == "opencode":
            return OpenCodeServeApp(manifest)
        else:
            # Generic CLI app
            from openbridge.apps.generic import GenericCliApp

            return GenericCliApp(manifest)

    def get(self, slug: str) -> Optional[App]:
        """Get app by slug."""
        return self.apps.get(slug)

    def list_apps(self) -> list:
        """List all available apps."""
        return list(self.apps.values())

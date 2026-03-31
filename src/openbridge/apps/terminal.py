"""Terminal app - default bash shell."""

from openbridge.apps.base import App, AppManifest


class TerminalApp(App):
    """Default terminal app - passes commands through unchanged."""

    def __init__(self, manifest: AppManifest):
        super().__init__(manifest)

    def format_command(self, user_input: str, context: dict) -> str:
        """No transformation for terminal."""
        return user_input

    def parse_output(self, output: str, context: dict) -> str:
        """No parsing for terminal."""
        return output

"""Generic CLI app for simple command-line tools."""

from openbridge.apps.base import App, AppManifest


class GenericCliApp(App):
    """Generic CLI app wrapper."""

    def __init__(self, manifest: AppManifest):
        super().__init__(manifest)
        self.binary = manifest.command.get("binary", manifest.slug)
        self.args_template = manifest.command.get("args", "{input}")

    def format_command(self, user_input: str, context: dict) -> str:
        """Format command with template."""
        args = self.args_template.format(input=user_input)
        return f"{self.binary} {args}"

    def parse_output(self, output: str, context: dict) -> str:
        """Return output as-is."""
        return output

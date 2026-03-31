"""Interactive setup wizard for OpenBridge."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from openbridge.config import Config

console = Console()


class SetupWizard:
    def __init__(self):
        self.config = Config()
        self.config_path = Path.home() / ".openbridge" / "config.yaml"

    def run(self) -> Config:
        console.print(
            Panel.fit(
                Text("Welcome to OpenBridge Setup", style="bold cyan"),
                subtitle="Production-grade remote CLI bridge",
            )
        )

        console.print("\n[dim]This wizard will help you configure OpenBridge.\n")

        # Security settings
        self._setup_security()

        # Adapter selection
        self._setup_adapters()

        # Features
        self._setup_features()

        # Save configuration
        self._save_config()

        return self.config

    def _setup_security(self) -> None:
        console.print("\n[bold]Security Configuration[/bold]\n")

        # Generate or use JWT secret
        if questionary.confirm("Generate new JWT secret?").ask():
            self.config.security.jwt_secret = secrets.token_hex(32)
            console.print("[green]Generated new JWT secret[/green]")

        # Session timeout
        timeout = questionary.text("Session timeout (seconds):", default="3600").ask()
        self.config.security.session_timeout = int(timeout)

        # Max sessions
        max_sessions = questionary.text("Max sessions per user:", default="3").ask()
        self.config.security.max_sessions_per_user = int(max_sessions)

    def _setup_adapters(self) -> None:
        console.print("\n[bold]Messaging Platform Configuration[/bold]\n")

        platforms = questionary.checkbox(
            "Select platforms to enable:",
            choices=[
                questionary.Choice("Telegram", value="telegram"),
                questionary.Choice("Discord", value="discord"),
                questionary.Choice("WhatsApp", value="whatsapp"),
            ],
        ).ask()

        if "telegram" in platforms:
            self._setup_telegram()

        if "discord" in platforms:
            self._setup_discord()

        if "whatsapp" in platforms:
            console.print(
                "\n[yellow]Note: WhatsApp will require QR code authentication on first run.[/yellow]"
            )
            self.config.adapters["whatsapp"].enabled = True

    def _setup_telegram(self) -> None:
        console.print("\n[cyan]Telegram Setup[/cyan]")
        console.print("1. Message @BotFather on Telegram")
        console.print("2. Create a new bot with /newbot")
        console.print("3. Copy the bot token\n")

        token = questionary.text("Bot token:").ask()
        if token:
            self.config.adapters["telegram"].enabled = True
            self.config.adapters["telegram"].bot_token = token

            allowed = questionary.text(
                "Allowed user IDs (comma-separated, leave empty for all):"
            ).ask()
            if allowed:
                user_ids = [int(x.strip()) for x in allowed.split(",") if x.strip()]
                self.config.adapters["telegram"].allowed_users = user_ids

    def _setup_discord(self) -> None:
        console.print("\n[cyan]Discord Setup[/cyan]")
        console.print("1. Go to https://discord.com/developers/applications")
        console.print("2. Create a new application")
        console.print("3. Go to Bot section and copy the token\n")

        token = questionary.text("Bot token:").ask()
        if token:
            self.config.adapters["discord"].enabled = True
            self.config.adapters["discord"].bot_token = token

            guild = questionary.text("Guild ID (optional):").ask()
            if guild:
                self.config.adapters["discord"].guild_id = guild

    def _setup_features(self) -> None:
        console.print("\n[bold]Feature Configuration[/bold]\n")

        self.config.features.file_transfer = questionary.confirm(
            "Enable file transfer?", default=True
        ).ask()

        self.config.features.session_persistence = questionary.confirm(
            "Enable session persistence?", default=True
        ).ask()

        self.config.features.rate_limiting.enabled = questionary.confirm(
            "Enable rate limiting?", default=True
        ).ask()

    def _save_config(self) -> None:
        self.config.ensure_directories()
        self.config.to_file(self.config_path)

        console.print(f"\n[green]Configuration saved to: {self.config_path}[/green]\n")

        console.print(
            Panel(
                "[bold]Setup Complete![/bold]\n\n"
                "Start OpenBridge with:\n"
                "  [cyan]openbridge start[/cyan]\n\n"
                "Or as a service:\n"
                "  [cyan]openbridge service install[/cyan]",
                title="Next Steps",
            )
        )

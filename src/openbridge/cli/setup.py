"""Interactive setup wizard for OpenBridge."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn

from openbridge.config import Config

console = Console()


class SetupWizard:
    """Interactive setup wizard for OpenBridge configuration."""

    def __init__(self):
        self.config = Config()
        # Determine config path based on whether running as root
        self.is_root = os.geteuid() == 0
        if self.is_root:
            # System-wide installation uses /etc/openbridge
            self.config_path = Path("/etc/openbridge/config.yaml")
        else:
            # User installation uses ~/.openbridge
            config_dir = Path(os.getenv("OB_CONFIG", Path.home() / ".openbridge")).parent
            self.config_path = config_dir / "config.yaml"
        self.auto_start = False

    def run(self, auto_start: bool = False) -> Config:
        """Run the complete setup wizard."""
        self.auto_start = auto_start

        self._show_welcome()
        self._setup_platforms()
        self._setup_security()
        self._setup_features()
        self._review_and_save()

        if auto_start:
            self._install_and_start_service()

        return self.config

    def _show_welcome(self) -> None:
        """Display welcome message."""
        console.print(
            Panel.fit(
                Text("Welcome to OpenBridge Setup", style="bold cyan")
                + "\n"
                + Text("Configure your remote CLI bridge", style="dim"),
                border_style="cyan",
            )
        )
        console.print("")

    def _setup_platforms(self) -> None:
        """Configure messaging platforms."""
        console.print("[bold cyan]Step 1: Choose Your Platforms[/bold cyan]")
        console.print("")

        platforms = questionary.checkbox(
            "Which messaging platforms do you want to use?",
            choices=[
                questionary.Choice(
                    "Telegram (Recommended - Easiest)", value="telegram", checked=True
                ),
                questionary.Choice("Discord", value="discord"),
                questionary.Choice("WhatsApp (QR code required)", value="whatsapp"),
            ],
            instruction="Use arrow keys and Space to select, Enter to confirm",
        ).ask()

        if not platforms:
            console.print("[yellow]No platforms selected. You can configure later.[/yellow]")
            return

        # Configure each selected platform
        if "telegram" in platforms:
            self._setup_telegram()

        if "discord" in platforms:
            self._setup_discord()

        if "whatsapp" in platforms:
            self._setup_whatsapp()

    def _setup_telegram(self) -> None:
        """Configure Telegram bot."""
        console.print("")
        console.print(
            Panel(
                "[bold]Telegram Setup[/bold]\n\n"
                "1. Open Telegram on your phone or computer\n"
                "2. Search for @BotFather and start a chat\n"
                "3. Send: [cyan]/newbot[/cyan]\n"
                "4. Follow instructions to create a bot\n"
                "5. Copy the bot token (looks like: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz)\n",
                border_style="blue",
            )
        )

        token = questionary.text(
            "Enter your Telegram bot token:",
            validate=lambda text: len(text) > 20 or "Token must be at least 20 characters",
        ).ask()

        if token:
            self.config.adapters["telegram"].enabled = True
            self.config.adapters["telegram"].bot_token = token

            # Ask about user restrictions
            restrict = questionary.confirm(
                "Restrict access to specific Telegram users? (More secure)", default=True
            ).ask()

            if restrict:
                console.print("")
                console.print(
                    Panel(
                        "[bold]Important:[/bold] Use [cyan]Numeric User ID[/cyan], NOT username!\n\n"
                        "[bold]User ID[/bold] = Permanent number (e.g., [green]123456789[/green])\n"
                        "[bold]Username[/bold] = @handle that can change (e.g., @john_doe)\n\n"
                        "[dim]Why User ID? It's permanent and cannot be spoofed for better security.[/dim]\n\n"
                        "[bold]How to find your User ID:[/bold]\n"
                        "1. Open Telegram\n"
                        "2. Message: [cyan]@userinfobot[/cyan]\n"
                        "3. It will reply with your numeric ID\n\n"
                        "[bold]Example:[/bold] If @userinfobot says 'Id: 123456789', enter: [green]123456789[/green]",
                        border_style="yellow",
                    )
                )
                console.print("")
                users = questionary.text(
                    "Enter numeric User IDs (comma-separated):",
                    instruction="Example: 123456789, 987654321",
                ).ask()
                if users:
                    user_ids = []
                    for user_input in users.split(","):
                        user_input = user_input.strip()
                        # Remove @ if present
                        if user_input.startswith("@"):
                            user_input = user_input[1:]
                        # Try to convert to int (User ID)
                        if user_input.isdigit():
                            user_ids.append(int(user_input))
                        elif user_input:
                            console.print(
                                f"[yellow]⚠ Skipping '{user_input}' - usernames not supported. Use numeric User ID instead.[/yellow]"
                            )

                    if user_ids:
                        self.config.adapters["telegram"].allowed_users = user_ids
                        console.print(f"[green]✓ Added {len(user_ids)} authorized user(s)[/green]")
                    else:
                        console.print(
                            "[yellow]⚠ No valid User IDs provided - allowing all users[/yellow]"
                        )

            console.print("[green]✓ Telegram configured[/green]")

    def _setup_discord(self) -> None:
        """Configure Discord bot."""
        console.print("")
        console.print(
            Panel(
                "[bold]Discord Setup[/bold]\n\n"
                "1. Go to: [cyan]https://discord.com/developers/applications[/cyan]\n"
                "2. Click 'New Application' and give it a name\n"
                "3. Go to 'Bot' section on the left\n"
                "4. Click 'Add Bot' → 'Yes, do it!'\n"
                "5. Click 'Copy Token' under Token\n"
                "6. (Optional) Enable 'Message Content Intent'\n",
                border_style="purple",
            )
        )

        token = questionary.text(
            "Enter your Discord bot token:",
            validate=lambda text: len(text) > 50 or "Token must be at least 50 characters",
        ).ask()

        if token:
            self.config.adapters["discord"].enabled = True
            self.config.adapters["discord"].bot_token = token

            # Ask about server restriction
            guild = questionary.text(
                "Restrict to specific Discord server? (Enter server ID or leave empty)"
            ).ask()
            if guild:
                self.config.adapters["discord"].guild_id = guild

            console.print("[green]✓ Discord configured[/green]")

    def _setup_whatsapp(self) -> None:
        """Configure WhatsApp."""
        console.print("")
        console.print(
            Panel(
                "[bold]WhatsApp Setup[/bold]\n\n"
                "WhatsApp requires QR code authentication.\n"
                "You'll scan a QR code after starting OpenBridge.",
                border_style="green",
            )
        )

        self.config.adapters["whatsapp"].enabled = True
        console.print("[green]✓ WhatsApp enabled (QR setup required on first start)[/green]")

    def _setup_security(self) -> None:
        """Configure security settings."""
        console.print("")
        console.print("[bold cyan]Step 2: Security Configuration[/bold cyan]")
        console.print("")

        # Session timeout
        timeout = questionary.text(
            "Session timeout in seconds:",
            default="3600",
            validate=lambda text: text.isdigit() and int(text) > 0 or "Must be a positive number",
        ).ask()
        self.config.security.session_timeout = int(timeout)

        # Max sessions
        max_sessions = questionary.text(
            "Max sessions per user:",
            default="3",
            validate=lambda text: text.isdigit() and int(text) > 0 or "Must be a positive number",
        ).ask()
        self.config.security.max_sessions_per_user = int(max_sessions)

        # Command restrictions
        console.print("")
        restrict_commands = questionary.confirm(
            "Restrict which commands can be executed? (Recommended)", default=False
        ).ask()

        if restrict_commands:
            console.print("[dim]Commands are matched using glob patterns (e.g., 'ls *', 'cat *')")
            console.print("[dim]Blocked commands take priority over allowed commands")

            blocked = questionary.text(
                "Blocked commands (comma-separated):", default="rm -rf /, mkfs.*, dd if=/dev/zero"
            ).ask()
            if blocked:
                self.config.security.blocked_commands = [c.strip() for c in blocked.split(",")]

        console.print("[green]✓ Security configured[/green]")

    def _setup_features(self) -> None:
        """Configure feature settings."""
        console.print("")
        console.print("[bold cyan]Step 3: Feature Configuration[/bold cyan]")
        console.print("")

        self.config.features.file_transfer = questionary.confirm(
            "Enable file transfers?", default=True
        ).ask()

        self.config.features.session_persistence = questionary.confirm(
            "Enable session persistence? (Sessions survive reconnections)", default=True
        ).ask()

        self.config.features.rate_limiting.enabled = questionary.confirm(
            "Enable rate limiting? (Prevents abuse)", default=True
        ).ask()

        if self.config.features.rate_limiting.enabled:
            rate = questionary.text(
                "Max commands per minute:",
                default="30",
                validate=lambda text: text.isdigit() or "Must be a number",
            ).ask()
            self.config.features.rate_limiting.commands_per_minute = int(rate)

        console.print("[green]✓ Features configured[/green]")

    def _review_and_save(self) -> None:
        """Review configuration and save."""
        console.print("")
        console.print("[bold cyan]Step 4: Review Configuration[/bold cyan]")
        console.print("")

        # Show summary
        enabled_platforms = []
        if self.config.adapters["telegram"].enabled:
            enabled_platforms.append("Telegram")
        if self.config.adapters["discord"].enabled:
            enabled_platforms.append("Discord")
        if self.config.adapters["whatsapp"].enabled:
            enabled_platforms.append("WhatsApp")

        summary = f"""
[bold]Configuration Summary:[/bold]

Platforms: {", ".join(enabled_platforms) if enabled_platforms else "None"}
Session Timeout: {self.config.security.session_timeout} seconds
Max Sessions: {self.config.security.max_sessions_per_user}
File Transfer: {"Yes" if self.config.features.file_transfer else "No"}
Rate Limiting: {"Yes" if self.config.features.rate_limiting.enabled else "No"}

Config Location: {self.config_path}
"""
        console.print(summary)

        # Save config
        if questionary.confirm("Save this configuration?", default=True).ask():
            self.config.ensure_directories()
            self.config.to_file(self.config_path)

            # If running as root, ensure config is readable by service user
            if self.is_root:
                import subprocess

                subprocess.run(
                    ["chown", "-R", "openbridge:openbridge", str(self.config_path.parent)],
                    check=False,
                )

            console.print(f"[green]✓ Configuration saved to {self.config_path}[/green]")
        else:
            console.print("[yellow]Configuration not saved. Run setup again to configure.[/yellow]")
            sys.exit(0)

    def _install_and_start_service(self) -> None:
        """Install systemd service and start OpenBridge."""
        console.print("")
        console.print("[bold cyan]Step 5: Installing Service & Starting OpenBridge[/bold cyan]")
        console.print("")

        # Check if systemd is available
        if not self._is_systemd_available():
            console.print(
                "[yellow]systemd not available. Starting OpenBridge in foreground...[/yellow]"
            )
            self._start_foreground()
            return

        # Ask about systemd
        use_systemd = questionary.confirm(
            "Install OpenBridge as a system service? (Recommended - auto-starts on boot)",
            default=True,
        ).ask()

        if use_systemd:
            self._install_systemd_service()
        else:
            self._start_foreground()

    def _is_systemd_available(self) -> bool:
        """Check if systemd is available."""
        try:
            subprocess.run(["systemctl", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _install_systemd_service(self) -> None:
        """Install and start systemd service."""
        service_file = Path("/etc/systemd/system/openbridge.service")

        # Determine sudo command (skip if already root)
        sudo_cmd = [] if self.is_root else ["sudo"]

        # Get service user from environment variable set by install.sh
        # or use default behavior
        service_user = os.environ.get("OB_SERVICE_USER", None)

        # If not set by install.sh, use defaults based on installation type
        if service_user is None:
            if self.is_root:
                service_user = "openbridge"
                install_dir = "/opt/openbridge"
            else:
                service_user = os.getenv("USER")
                install_dir = Path.home() / ".local/share/openbridge"
        else:
            # Use values from install.sh
            if self.is_root:
                install_dir = "/opt/openbridge"
            else:
                install_dir = Path.home() / ".local/share/openbridge"

        # Create service content
        service_content = f"""[Unit]
Description=OpenBridge - Remote CLI Bridge
After=network.target

[Service]
Type=simple
User={service_user}
Group={service_user}
WorkingDirectory={install_dir}
Environment=PATH={install_dir}/venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
Environment=OB_CONFIG={self.config_path}
ExecStart={install_dir}/venv/bin/openbridge start
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5s
KillMode=mixed

[Install]
WantedBy=multi-user.target
"""

        try:
            # Write service file to a location we can access
            # Use config directory which we know we can write to
            temp_file = self.config_path.parent / "openbridge.service.tmp"
            temp_file.write_text(service_content)

            # Install service
            if self.is_root:
                console.print("[dim]Installing service...[/dim]")
            else:
                console.print("[dim]Installing service (requires sudo)...[/dim]")

            subprocess.run([*sudo_cmd, "cp", str(temp_file), str(service_file)], check=True)
            subprocess.run([*sudo_cmd, "systemctl", "daemon-reload"], check=True)
            subprocess.run([*sudo_cmd, "systemctl", "enable", "openbridge"], check=True)
            subprocess.run([*sudo_cmd, "systemctl", "start", "openbridge"], check=True)

            console.print("[green]✓ OpenBridge service installed and started![/green]")
            console.print("")
            console.print("[bold]Service Commands:[/bold]")
            if self.is_root:
                console.print("  systemctl status openbridge   - Check status")
                console.print("  systemctl stop openbridge     - Stop service")
                console.print("  systemctl restart openbridge  - Restart service")
            else:
                console.print("  sudo systemctl status openbridge  - Check status")
                console.print("  sudo systemctl stop openbridge    - Stop service")
                console.print("  sudo systemctl restart openbridge - Restart service")
            console.print("  sudo systemctl disable openbridge - Disable auto-start")

        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to install service: {e}[/red]")
            console.print("[yellow]Starting in foreground instead...[/yellow]")
            self._start_foreground()

    def _start_foreground(self) -> None:
        """Start OpenBridge in foreground."""
        console.print("[green]✓ Starting OpenBridge...[/green]")
        console.print("")
        console.print("[yellow]Press Ctrl+C to stop[/yellow]")
        console.print("")

        try:
            subprocess.run(["openbridge", "start"])
        except KeyboardInterrupt:
            console.print("\n[yellow]OpenBridge stopped[/yellow]")


def run_setup(auto_start: bool = False) -> None:
    """Entry point for setup command."""
    wizard = SetupWizard()
    wizard.run(auto_start=auto_start)

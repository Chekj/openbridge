"""CLI commands for OpenBridge."""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

import click
import structlog
from rich.console import Console

from openbridge.config import Config
from openbridge.server import BridgeServer

console = Console()
logger = structlog.get_logger()


@click.group()
@click.option("--config", "-c", type=click.Path(), help="Path to config file")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def cli(ctx, config, verbose):
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--auto-start", "-a", is_flag=True, help="Auto-start after setup (used by installer)")
@click.pass_context
def setup(ctx, auto_start):
    """Run interactive setup wizard."""
    from openbridge.cli.setup import run_setup

    run_setup(auto_start=auto_start)


@cli.command()
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=8080, help="Port to bind to")
@click.option("--daemon", "-d", is_flag=True, help="Run as daemon")
@click.pass_context
def start(ctx, host, port, daemon):
    """Start the OpenBridge server."""
    import os

    config_path = ctx.obj.get("config_path")

    # Load configuration
    if config_path:
        # Config path provided via CLI
        config = Config.from_file(config_path)
    elif os.environ.get("OB_CONFIG"):
        # Config path provided via environment variable
        env_path = Path(os.environ["OB_CONFIG"]).expanduser()
        if env_path.exists():
            config = Config.from_file(env_path)
        else:
            console.print(f"[red]Config file not found: {env_path}[/red]")
            sys.exit(1)
    else:
        # Check default location
        default_path = Path.home() / ".openbridge" / "config.yaml"
        if default_path.exists():
            config = Config.from_file(default_path)
        else:
            console.print("[red]No configuration found. Run 'openbridge setup' first.[/red]")
            sys.exit(1)

    # Override with CLI options
    config.server.host = host
    config.server.port = port

    # Setup logging
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(10 if ctx.obj.get("verbose") else 20)
    )

    # Create and start server
    server = BridgeServer(config)

    def signal_handler(sig, frame):
        console.print("\n[yellow]Shutting down...[/yellow]")
        asyncio.create_task(server.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        pass


@cli.command()
@click.pass_context
def status(ctx):
    """Check server status."""
    console.print("[yellow]Status check not yet implemented[/yellow]")


@cli.command()
def version():
    """Show version information."""
    from openbridge import __version__

    console.print(f"OpenBridge [cyan]v{__version__}[/cyan]")


def main():
    cli()

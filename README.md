# OpenBridge

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Production-grade remote CLI bridge for mobile devices**

Connect to your computer's terminal from anywhere using Telegram, Discord, WhatsApp, and more. Run any CLI tool (opencode, codex, etc.) from your phone with full interactive support.

![OpenBridge Demo](https://via.placeholder.com/800x400?text=OpenBridge+Demo)

## Features

- **Multi-Platform Support** - Telegram, Discord, WhatsApp (extensible architecture)
- **Full CLI Experience** - Interactive programs (vim, htop, codex, opencode) work perfectly
- **Mobile-Optimized** - Formatted output for small screens with pagination
- **Session Persistence** - Sessions survive reconnections and device switches
- **Production-Ready** - Docker, systemd, monitoring, and logging included
- **Easy Setup** - One-command installation with interactive wizard
- **Secure** - JWT authentication, command allowlists, rate limiting

## Quick Start

### One-Command Installation 🚀

**For regular user (recommended):**
```bash
curl -fsSL https://raw.githubusercontent.com/Chekj/openbridge/main/scripts/install.sh | bash
```

**For system-wide installation (as root):**
```bash
# Download first, then run (required for interactive setup)
curl -fsSL https://raw.githubusercontent.com/Chekj/openbridge/main/scripts/install.sh -o install.sh
sudo bash install.sh
```

**That's it!** The installer will:
1. ✓ Download and install OpenBridge
2. ✓ Launch interactive setup wizard
3. ✓ Configure your chosen platforms (Telegram, Discord, WhatsApp)
4. ✓ Install as systemd service (auto-starts on boot)
5. ✓ Start the server immediately

You'll just need to answer a few prompts to configure your bots.

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/Chekj/openbridge.git
cd openbridge

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install
pip install -e .

# Run setup wizard
openbridge setup

# Start server
openbridge start
```

## Usage

Once connected, simply send any command from your messaging app:

```
ls -la
cd /var/log
tail -f syslog
vim myfile.txt
opencode "create a python script"
```

### Special Commands

- `/help` - Show help message
- `/cancel` - Send Ctrl+C to terminal
- `/resize <rows> <cols>` - Resize terminal
- `/status` - Show session status

## Configuration

Configuration is stored in `~/.openbridge/config.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 8080

adapters:
  telegram:
    enabled: true
    bot_token: "YOUR_BOT_TOKEN"
    allowed_users: []  # Empty = allow all
  
  discord:
    enabled: true
    bot_token: "YOUR_BOT_TOKEN"
    guild_id: null

security:
  allowed_commands: ["*"]  # Allow all
  blocked_commands: ["rm -rf /", "mkfs.*"]
  session_timeout: 3600
```

### Environment Variables

All config options can be set via environment variables:

```bash
export OB_TELEGRAM_TOKEN="your_token"
export OB_DISCORD_TOKEN="your_token"
export OB_SERVER_PORT=8080
```

## Docker Deployment

```bash
# Using docker-compose
docker-compose up -d

# Or using Docker directly
docker run -d \
  -e OB_TELEGRAM_TOKEN=your_token \
  -e OB_DISCORD_TOKEN=your_token \
  -v ~/.openbridge:/data \
  -p 8080:8080 \
  openbridge/openbridge:latest
```

## Systemd Service

```bash
# Install service
sudo cp scripts/systemd/openbridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable openbridge
sudo systemctl start openbridge

# Check status
sudo systemctl status openbridge
```

## Architecture

```
Mobile Apps (Telegram/Discord/WhatsApp)
    ↓
Platform Adapters
    ↓
Message Router
    ↓
Bridge Engine (PTY)
    ↓
Host System Shell
```

- **Adapters**: Handle platform-specific APIs
- **Router**: Routes messages and manages sessions
- **Engine**: PTY-based command execution
- **Session Manager**: User session tracking and cleanup

## Development

```bash
# Setup development environment
git clone https://github.com/Chekj/openbridge.git
cd openbridge
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/
black src/

# Type checking
mypy src/openbridge
```

## Adding New Platforms

Create a new adapter by implementing the `BaseAdapter` interface:

```python
from openbridge.adapters import BaseAdapter, UserMessage, BotResponse

@register_adapter("myplatform")
class MyPlatformAdapter(BaseAdapter):
    async def connect(self) -> bool:
        # Connect to platform API
        pass
    
    async def send_message(self, user_id: str, response: BotResponse) -> bool:
        # Send message to user
        pass
```

## Security Considerations

- **Command Filtering**: Use `allowed_commands` and `blocked_commands`
- **User Authentication**: Configure `allowed_users` per adapter
- **Rate Limiting**: Built-in rate limiting per user
- **Session Timeout**: Automatic session cleanup
- **No Root**: Never run as root user

## Troubleshooting

**Bot not responding:**
- Check bot token is correct
- Ensure bot is started with `openbridge start`
- Check logs: `~/.openbridge/logs/`

**Commands not executing:**
- Check command is in `allowed_commands`
- Verify not in `blocked_commands`
- Check user is in `allowed_users`

**Connection issues:**
- Verify firewall allows connections
- Check platform API status
- Review logs for errors

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - see [LICENSE](LICENSE) file

## Support

- Documentation: https://docs.openbridge.dev
- Issues: https://github.com/Chekj/openbridge/issues
- Discussions: https://github.com/Chekj/openbridge/discussions

---

Made with love for remote developers everywhere.

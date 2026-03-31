#!/bin/bash
# OpenBridge One-Line Installer
# Works with or without root
# Usage: curl -fsSL https://raw.githubusercontent.com/Chekj/openbridge/main/scripts/install.sh | bash

set -e

REPO_URL="https://github.com/Chekj/openbridge"

# Detect if running as root
IS_ROOT=false
if [ "$EUID" -eq 0 ]; then
    IS_ROOT=true
fi

# Set paths based on root/non-root
if [ "$IS_ROOT" = true ]; then
    INSTALL_DIR="/opt/openbridge"
    BIN_DIR="/usr/local/bin"
    CONFIG_DIR="/etc/openbridge"
    SERVICE_USER="openbridge"
else
    INSTALL_DIR="$HOME/.local/share/openbridge"
    BIN_DIR="$HOME/.local/bin"
    CONFIG_DIR="$HOME/.openbridge"
    SERVICE_USER="$USER"
fi

VENV_DIR="$INSTALL_DIR/venv"

echo "=========================================="
echo "OpenBridge Installer"
echo "Production-grade remote CLI bridge"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Helper functions
print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

print_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

print_header() {
    echo -e "${BLUE}$1${NC}"
}

# Check Python version
check_python() {
    print_step "Checking Python version..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
        PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
        
        if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 11 ]; then
            print_success "Python $PYTHON_VERSION found"
            return 0
        fi
    fi
    
    print_error "Python 3.11+ is required"
    echo "Please install Python 3.11 or higher: https://python.org"
    exit 1
}

# Check pip
check_pip() {
    print_step "Checking pip..."
    
    if command -v pip3 &> /dev/null; then
        print_success "pip3 found"
        return 0
    fi
    
    print_error "pip3 is required"
    exit 1
}

# Check git
check_git() {
    print_step "Checking git..."
    
    if ! command -v git &> /dev/null; then
        print_error "git is required but not installed"
        echo "Please install git: sudo apt-get install git"
        exit 1
    fi
    print_success "git found"
}

# Setup service user for root install
setup_service_user() {
    if [ "$IS_ROOT" = true ]; then
        print_step "Setting up service user..."
        if ! id -u "$SERVICE_USER" &>/dev/null; then
            useradd -r -s /bin/false -d "$INSTALL_DIR" -c "OpenBridge service" "$SERVICE_USER"
            print_success "Created user: $SERVICE_USER"
        else
            print_info "User $SERVICE_USER already exists"
        fi
    fi
}

# Create directories
setup_directories() {
    print_step "Creating directories..."
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$BIN_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$CONFIG_DIR/logs"
    mkdir -p "$CONFIG_DIR/sessions"
    
    if [ "$IS_ROOT" = true ]; then
        chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
        chown -R "$SERVICE_USER:$SERVICE_USER" "$CONFIG_DIR"
    fi
    
    print_success "Directories created"
}

# Download OpenBridge
download_openbridge() {
    print_step "Downloading OpenBridge..."
    
    # Always fix git ownership issues first if running as root
    if [ "$IS_ROOT" = true ] && [ -d "$INSTALL_DIR/.git" ]; then
        git config --global --add safe.directory "$INSTALL_DIR" 2>/dev/null || true
    fi
    
    if [ -d "$INSTALL_DIR/.git" ]; then
        print_info "Updating existing installation..."
        cd "$INSTALL_DIR"
        # Try to pull, if it fails, remove and re-clone
        if ! git pull; then
            print_info "Update failed, re-cloning..."
            cd /
            rm -rf "$INSTALL_DIR"
            git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
        fi
    else
        print_info "Cloning repository..."
        rm -rf "$INSTALL_DIR"
        git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
    fi
    
    if [ "$IS_ROOT" = true ]; then
        chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    fi
    
    print_success "OpenBridge downloaded"
}

# Setup virtual environment
setup_venv() {
    print_step "Setting up virtual environment..."
    
    if [ "$IS_ROOT" = true ]; then
        # Run as service user
        su -s /bin/bash "$SERVICE_USER" -c "
            cd $INSTALL_DIR
            python3 -m venv $VENV_DIR
            source $VENV_DIR/bin/activate
            pip install --upgrade pip --quiet
            pip install -e $INSTALL_DIR --quiet
        "
    else
        if [ ! -d "$VENV_DIR" ]; then
            python3 -m venv "$VENV_DIR"
        fi
        
        source "$VENV_DIR/bin/activate"
        pip install --upgrade pip --quiet
        pip install -e "$INSTALL_DIR" --quiet
    fi
    
    print_success "Virtual environment ready"
}

# Create wrapper script
create_wrapper() {
    print_step "Creating command shortcuts..."
    
    if [ "$IS_ROOT" = true ]; then
        # System-wide command
        cat > "$BIN_DIR/openbridge" << EOF
#!/bin/bash
if [ "\$EUID" -ne 0 ]; then
    echo "OpenBridge is installed system-wide. Please use: sudo openbridge"
    exit 1
fi
source "$VENV_DIR/bin/activate"
exec openbridge "\$@"
EOF
    else
        # User-local command
        cat > "$BIN_DIR/openbridge" << EOF
#!/bin/bash
source "$VENV_DIR/bin/activate"
exec openbridge "\$@"
EOF
    fi
    
    chmod +x "$BIN_DIR/openbridge"
    
    # Create 'ob' alias
    ln -sf "$BIN_DIR/openbridge" "$BIN_DIR/ob"
    
    print_success "Commands created: openbridge, ob"
}

# Setup shell PATH (non-root only)
setup_shell_path() {
    if [ "$IS_ROOT" = false ]; then
        print_step "Configuring shell..."
        
        SHELL_NAME=$(basename "$SHELL")
        
        case "$SHELL_NAME" in
            bash)
                RC_FILE="$HOME/.bashrc"
                ;;
            zsh)
                RC_FILE="$HOME/.zshrc"
                ;;
            fish)
                RC_FILE="$HOME/.config/fish/config.fish"
                mkdir -p "$(dirname "$RC_FILE")"
                ;;
            *)
                RC_FILE="$HOME/.profile"
                ;;
        esac
        
        if [ -f "$RC_FILE" ]; then
            if ! grep -q "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
                echo "" >> "$RC_FILE"
                echo "# OpenBridge" >> "$RC_FILE"
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC_FILE"
            fi
        else
            echo 'export PATH="$HOME/.local/bin:$PATH"' > "$RC_FILE"
        fi
        
        # Export for current session
        export PATH="$BIN_DIR:$PATH"
        
        print_success "Shell configured"
    fi
}

# Check if running interactively
is_interactive() {
    [ -t 0 ]
}

# Create default config
create_default_config() {
    print_step "Creating default configuration..."
    
    CONFIG_FILE="$CONFIG_DIR/config.yaml"
    
    cat > "$CONFIG_FILE" << EOF
server:
  host: 0.0.0.0
  port: 8080
  workers: 1
  reload: false
  log_level: INFO

security:
  jwt_secret: "$(openssl rand -hex 32)"
  session_timeout: 3600
  max_sessions_per_user: 3
  allowed_commands:
    - "*"
  blocked_commands:
    - "rm -rf /"
    - "mkfs.*"
    - "dd if=/dev/zero"
  require_auth: true
  encryption_enabled: false

adapters:
  telegram:
    enabled: false
    bot_token: ""
    allowed_users: []
    webhook_url: null
    polling_timeout: 30
  
  discord:
    enabled: false
    bot_token: ""
    guild_id: null
    allowed_roles: []
    command_prefix: "!"
  
  whatsapp:
    enabled: false
    session_path: ".whatsapp_session"
    webhook_url: null

redis:
  enabled: false
  host: localhost
  port: 6379
  db: 0
  password: null

features:
  file_transfer: true
  session_persistence: true
  auto_cleanup: true
  rate_limiting:
    enabled: true
    commands_per_minute: 30
    messages_per_second: 5
    burst_size: 10

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: null
  max_bytes: 10485760
  backup_count: 5

data_dir: $CONFIG_DIR
EOF

    if [ "$IS_ROOT" = true ]; then
        chown "$SERVICE_USER:$SERVICE_USER" "$CONFIG_FILE"
    fi
    
    print_success "Default configuration created"
}

# Run interactive setup
run_setup() {
    # Check if running in interactive mode
    if ! is_interactive; then
        print_info "Non-interactive mode detected"
        print_info "Creating default configuration..."
        create_default_config
        return
    fi
    
    print_header ""
    print_header "=========================================="
    print_header "  INTERACTIVE SETUP WIZARD"
    print_header "=========================================="
    echo ""
    
    if [ "$IS_ROOT" = true ]; then
        # Run setup as service user
        su -s /bin/bash "$SERVICE_USER" -c "
            source $VENV_DIR/bin/activate
            $VENV_DIR/bin/openbridge setup --auto-start
        "
    else
        # Run setup as current user
        source "$VENV_DIR/bin/activate"
        "$BIN_DIR/openbridge" setup --auto-start
    fi
}

# Install systemd service
install_systemd() {
    print_step "Installing systemd service..."
    
    if ! command -v systemctl &> /dev/null; then
        print_info "systemd not found, skipping service installation"
        return 1
    fi
    
    # Create service file
    SERVICE_FILE="/etc/systemd/system/openbridge.service"
    
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=OpenBridge - Remote CLI Bridge
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
Environment=OB_CONFIG=$CONFIG_DIR/config.yaml
ExecStart=$VENV_DIR/bin/openbridge start
ExecReload=/bin/kill -HUP \$MAINPID
Restart=on-failure
RestartSec=5s
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    systemctl enable openbridge.service
    print_success "Systemd service installed and enabled"
}

# Main installation
main() {
    print_header "Starting OpenBridge installation..."
    
    if [ "$IS_ROOT" = true ]; then
        print_info "Running as root - installing system-wide"
    else
        print_info "Running as user - installing locally"
    fi
    
    check_python
    check_pip
    check_git
    setup_service_user
    setup_directories
    download_openbridge
    setup_venv
    create_wrapper
    setup_shell_path
    
    if [ "$IS_ROOT" = true ]; then
        install_systemd
    fi
    
    echo ""
    print_success "Installation complete!"
    echo ""
    
    # Run interactive setup
    run_setup
    
    echo ""
    print_header "=========================================="
    print_success "OpenBridge is installed!"
    print_header "=========================================="
    echo ""
    
    # Check if we ran in non-interactive mode
    if ! is_interactive; then
        print_info "Non-interactive installation complete!"
        echo ""
        echo "Next steps:"
        echo "  1. Edit the configuration file:"
        if [ "$IS_ROOT" = true ]; then
            echo "     sudo nano $CONFIG_DIR/config.yaml"
        else
            echo "     nano $CONFIG_DIR/config.yaml"
        fi
        echo ""
        echo "  2. Add your bot tokens (Telegram/Discord):"
        echo "     - Telegram: Message @BotFather to create a bot"
        echo "     - Discord: Go to https://discord.com/developers/applications"
        echo ""
        echo "  3. Start OpenBridge:"
        if [ "$IS_ROOT" = true ]; then
            echo "     sudo systemctl start openbridge"
        else
            echo "     openbridge start"
        fi
        echo ""
    fi
    
    if [ "$IS_ROOT" = true ]; then
        echo "System-wide installation:"
        echo ""
        echo "Commands (run as root or with sudo):"
        echo "  sudo openbridge --help    Show all commands"
        echo "  sudo openbridge status    Check server status"
        echo "  sudo openbridge stop      Stop the server"
        echo ""
        echo "Service commands:"
        echo "  sudo systemctl status openbridge  - Check status"
        echo "  sudo systemctl stop openbridge    - Stop service"
        echo "  sudo systemctl restart openbridge - Restart service"
        echo ""
        echo "Configuration: $CONFIG_DIR/config.yaml"
        echo "Logs: $CONFIG_DIR/logs/"
    else
        echo "User installation:"
        echo ""
        echo "Commands available:"
        echo "  openbridge --help    Show all commands"
        echo "  openbridge status    Check server status"
        echo "  openbridge stop      Stop the server"
        echo ""
        echo "Configuration: $CONFIG_DIR/config.yaml"
        echo "Logs: $CONFIG_DIR/logs/"
        echo ""
        echo "To uninstall: rm -rf $INSTALL_DIR $CONFIG_DIR"
    fi
    
    echo ""
}

# Run main function
main

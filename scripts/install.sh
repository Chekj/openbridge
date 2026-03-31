#!/bin/bash
# OpenBridge One-Line Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/Chekj/openbridge/main/scripts/install.sh | bash

set -e

REPO_URL="https://github.com/Chekj/openbridge"
INSTALL_DIR="$HOME/.local/share/openbridge"
BIN_DIR="$HOME/.local/bin"
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

# Check if running as root
check_not_root() {
    if [ "$EUID" -eq 0 ]; then
        print_error "Do not run this script as root!"
        echo "OpenBridge will ask for sudo only when needed for systemd installation."
        exit 1
    fi
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

# Create directories
setup_directories() {
    print_step "Creating directories..."
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$BIN_DIR"
    mkdir -p "$HOME/.openbridge"
    mkdir -p "$HOME/.openbridge/logs"
    mkdir -p "$HOME/.openbridge/sessions"
    print_success "Directories created"
}

# Download OpenBridge
download_openbridge() {
    print_step "Downloading OpenBridge..."
    
    if [ -d "$INSTALL_DIR/.git" ]; then
        print_info "Updating existing installation..."
        cd "$INSTALL_DIR"
        git pull
    else
        print_info "Cloning repository..."
        rm -rf "$INSTALL_DIR"
        git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
    fi
    
    print_success "OpenBridge downloaded"
}

# Setup virtual environment
setup_venv() {
    print_step "Setting up virtual environment..."
    
    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
    fi
    
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip --quiet
    pip install -e "$INSTALL_DIR" --quiet
    
    print_success "Virtual environment ready"
}

# Create wrapper script
create_wrapper() {
    print_step "Creating command shortcuts..."
    
    cat > "$BIN_DIR/openbridge" << EOF
#!/bin/bash
source "$VENV_DIR/bin/activate"
exec openbridge "\$@"
EOF
    chmod +x "$BIN_DIR/openbridge"
    
    # Create 'ob' alias
    ln -sf "$BIN_DIR/openbridge" "$BIN_DIR/ob"
    
    print_success "Commands created: openbridge, ob"
}

# Setup shell PATH
setup_shell_path() {
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
}

# Run interactive setup
run_setup() {
    print_header ""
    print_header "=========================================="
    print_header "  INTERACTIVE SETUP WIZARD"
    print_header "=========================================="
    echo ""
    
    # Source venv and run setup
    source "$VENV_DIR/bin/activate"
    "$BIN_DIR/openbridge" setup --auto-start
}

# Install systemd service
install_systemd() {
    print_step "Installing systemd service..."
    
    if ! command -v systemctl &> /dev/null; then
        print_info "systemd not found, skipping service installation"
        return 1
    fi
    
    # Create service file
    SERVICE_FILE="/tmp/openbridge.service"
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=OpenBridge - Remote CLI Bridge
After=network.target

[Service]
Type=simple
User=$USER
Group=$(id -gn)
WorkingDirectory=$HOME
Environment=PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
Environment=OB_CONFIG=$HOME/.openbridge/config.yaml
ExecStart=$VENV_DIR/bin/openbridge start
ExecReload=/bin/kill -HUP \$MAINPID
Restart=on-failure
RestartSec=5s
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOF
    
    # Install service (requires sudo)
    if sudo cp "$SERVICE_FILE" /etc/systemd/system/openbridge.service 2>/dev/null; then
        sudo systemctl daemon-reload
        sudo systemctl enable openbridge.service
        print_success "Systemd service installed"
        return 0
    else
        print_info "Could not install systemd service (sudo required)"
        return 1
    fi
}

# Main installation
main() {
    print_header "Starting OpenBridge installation..."
    
    check_not_root
    check_python
    check_pip
    check_git
    setup_directories
    download_openbridge
    setup_venv
    create_wrapper
    setup_shell_path
    
    echo ""
    print_success "Installation complete!"
    echo ""
    
    # Run interactive setup
    run_setup
    
    echo ""
    print_header "=========================================="
    print_success "OpenBridge is installed and configured!"
    print_header "=========================================="
    echo ""
    echo "Commands available:"
    echo "  openbridge --help    Show all commands"
    echo "  openbridge status    Check server status"
    echo "  openbridge stop      Stop the server"
    echo ""
    echo "Configuration: ~/.openbridge/config.yaml"
    echo "Logs: ~/.openbridge/logs/"
    echo ""
    echo "To uninstall: rm -rf ~/.local/share/openbridge ~/.openbridge"
    echo ""
}

# Run main function
main

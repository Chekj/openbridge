#!/bin/bash
# OpenBridge One-Line Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/username/openbridge/main/scripts/install.sh | bash

set -e

REPO_URL="https://github.com/username/openbridge"
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

# Check Python version
check_python() {
    print_info "Checking Python version..."
    
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
    print_info "Checking pip..."
    
    if command -v pip3 &> /dev/null; then
        print_success "pip3 found"
        return 0
    fi
    
    print_error "pip3 is required"
    exit 1
}

# Create directories
setup_directories() {
    print_info "Creating directories..."
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$BIN_DIR"
    mkdir -p "$HOME/.openbridge"
    mkdir -p "$HOME/.openbridge/logs"
    print_success "Directories created"
}

# Install OpenBridge
install_openbridge() {
    print_info "Installing OpenBridge..."
    
    # Check if running from local directory
    if [ -f "pyproject.toml" ] && grep -q "openbridge" pyproject.toml 2>/dev/null; then
        print_info "Installing from local directory..."
        cp -r . "$INSTALL_DIR"
    else
        print_info "Downloading from GitHub..."
        if command -v git &> /dev/null; then
            if [ -d "$INSTALL_DIR/.git" ]; then
                cd "$INSTALL_DIR"
                git pull
            else
                rm -rf "$INSTALL_DIR"
                git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
            fi
        else
            print_info "Downloading release archive..."
            curl -L "$REPO_URL/releases/latest/download/openbridge.tar.gz" | tar -xz -C "$INSTALL_DIR" --strip-components=1
        fi
    fi
    
    print_success "Source code ready"
}

# Setup virtual environment
setup_venv() {
    print_info "Setting up virtual environment..."
    
    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
    fi
    
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip
    pip install -e "$INSTALL_DIR"
    
    print_success "Virtual environment created"
}

# Create wrapper script
create_wrapper() {
    print_info "Creating command wrapper..."
    
    cat > "$BIN_DIR/openbridge" << 'EOF'
#!/bin/bash
VENV_DIR="$HOME/.local/share/openbridge/venv"
source "$VENV_DIR/bin/activate"
exec openbridge "$@"
EOF
    
    chmod +x "$BIN_DIR/openbridge"
    
    # Also create 'ob' alias
    ln -sf "$BIN_DIR/openbridge" "$BIN_DIR/ob"
    
    print_success "Command wrapper created"
}

# Setup shell integration
setup_shell() {
    print_info "Configuring shell..."
    
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
            print_success "Added to PATH in $RC_FILE"
        fi
    else
        echo 'export PATH="$HOME/.local/bin:$PATH"' > "$RC_FILE"
        print_success "Created $RC_FILE with PATH"
    fi
}

# Run setup wizard
run_setup() {
    print_info "Running setup wizard..."
    
    if [ -t 0 ]; then
        # Interactive terminal
        "$BIN_DIR/openbridge" setup
    else
        print_info "Non-interactive mode detected"
        print_info "Please run 'openbridge setup' manually to configure"
    fi
}

# Main installation
main() {
    print_info "Starting installation..."
    
    check_python
    check_pip
    setup_directories
    install_openbridge
    setup_venv
    create_wrapper
    setup_shell
    
    echo ""
    echo "=========================================="
    print_success "Installation Complete!"
    echo "=========================================="
    echo ""
    echo "OpenBridge is installed in: $INSTALL_DIR"
    echo ""
    echo "Next steps:"
    echo "  1. Restart your terminal or run:"
    echo "     source ~/.bashrc  # or ~/.zshrc"
    echo ""
    echo "  2. Run setup wizard:"
    echo "     openbridge setup"
    echo ""
    echo "  3. Start the server:"
    echo "     openbridge start"
    echo ""
    echo "  4. Install as service (optional):"
    echo "     sudo cp $INSTALL_DIR/scripts/systemd/openbridge.service /etc/systemd/system/"
    echo ""
    echo "Documentation: https://docs.openbridge.dev"
    echo ""
    
    # Offer to run setup now if interactive
    if [ -t 0 ]; then
        read -p "Would you like to run the setup wizard now? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            run_setup
        fi
    fi
}

main

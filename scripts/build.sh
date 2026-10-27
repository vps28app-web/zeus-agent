#!/usr/bin/env bash
set -euo pipefail

# Build script for Zeus agent harness and Go sandbox.
# Usage: ./scripts/build.sh

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SANDBOX_DIR="$PROJECT_DIR/sandbox"
WHATSAPP_DIR="$PROJECT_DIR/gateway/whatsapp/baileys"
VENV_DIR="$PROJECT_DIR/.venv"

echo "==> Building Zeus sandbox (Go)"
cd "$SANDBOX_DIR"
go build -buildvcs=false -o sandbox ./cmd/sandbox

echo "==> Building WhatsApp Baileys bridge (Node/TypeScript)"
cd "$WHATSAPP_DIR"
npm install
npm run build

echo "==> Setting up Python virtual environment"
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "$PROJECT_DIR/requirements.txt"

echo "==> Running Python tests"
cd "$PROJECT_DIR"
python -m pytest tests/ -q

echo "==> Build complete"
echo "  Sandbox binary: $SANDBOX_DIR/sandbox"
echo "  WhatsApp bridge: $WHATSAPP_DIR/dist/index.js"
echo "  Python venv:    $VENV_DIR"
echo ""
echo "To start the sandbox server manually (add this same generated value to $PROJECT_DIR/.env for Zeus):"
echo '  export ZEUS_SANDBOX_AUTH_TOKEN="$(openssl rand -hex 32)"'
echo "  cd $SANDBOX_DIR && sudo -E ./sandbox -addr 127.0.0.1:9876"
echo ""
echo "The systemd installer requires a 64-hex token in $PROJECT_DIR/.env; it installs a root-owned binary at /usr/local/lib/zeus/sandbox and copies only the token to /etc/zeus/sandbox.env."
echo "To start the WhatsApp bridge manually:"
echo "  cd $WHATSAPP_DIR && node dist/index.js"
echo ""
echo "To install systemd services:"
echo "  sudo ./scripts/install-systemd.sh"

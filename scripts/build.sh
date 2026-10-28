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
echo "The preferred installation is ./scripts/install.sh; it creates the state token in ZEUS_HOME/.env (default: ~/.zeus/.env)."
echo "For the privileged systemd service, use only a trusted, clean Git checkout and run sudo ./scripts/install-systemd.sh."
echo "The service installer copies the sandbox to /usr/local/lib/zeus/sandbox and only the token to /etc/zeus/sandbox.env."
echo "To start the WhatsApp bridge manually:"
echo "  cd $WHATSAPP_DIR && node dist/index.js"
echo ""
echo "To install systemd services:"
echo "  sudo ./scripts/install-systemd.sh"

#!/usr/bin/env bash
set -euo pipefail

# Install and enable Zeus systemd services.
# Must be run as root or with sudo.

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root. Use: sudo $0"
    exit 1
fi

install_service() {
    local service_name="$1"
    local src="$PROJECT_DIR/systemd/$service_name"
    local dst="/etc/systemd/system/$service_name"

    if [[ ! -f "$src" ]]; then
        echo "Service file not found: $src"
        return 1
    fi

    echo "==> Installing $service_name"
    cp "$src" "$dst"
    sed -i "s|/home/vps28/Documentos/Dev/Zeus|$PROJECT_DIR|g" "$dst"
    systemctl daemon-reload
    systemctl enable "$service_name"
}

# Sandbox must be built before installing.
if [[ ! -f "$PROJECT_DIR/sandbox/sandbox" ]]; then
    echo "Sandbox binary not found. Run ./scripts/build.sh first."
    exit 1
fi

install_service "zeus-sandbox.service"
install_service "zeus-telegram-gateway.service"
install_service "zeus-discord-gateway.service"
install_service "zeus-whatsapp-bridge.service"
install_service "zeus-whatsapp-gateway.service"

# Restart sandbox; leave chat gateways stopped until configured.
systemctl restart zeus-sandbox.service

echo ""
echo "Zeus services installed."
echo "Sandbox is running."
echo ""
echo "Start chat gateways after configuring .env:"
echo "  sudo systemctl start zeus-telegram-gateway.service"
echo "  sudo systemctl start zeus-discord-gateway.service"
echo "  sudo systemctl start zeus-whatsapp-bridge.service"
echo "  sudo systemctl start zeus-whatsapp-gateway.service"
echo ""
echo "Check logs with:"
echo "  journalctl -u zeus-telegram-gateway.service -f"
echo "  journalctl -u zeus-discord-gateway.service -f"
echo "  journalctl -u zeus-whatsapp-bridge.service -f"
echo "  journalctl -u zeus-whatsapp-gateway.service -f"

#!/usr/bin/env bash
set -euo pipefail

# Install and enable the Zeus sandbox systemd service.
# Must be run as root or with sudo.

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="zeus-sandbox.service"
SERVICE_SRC="$PROJECT_DIR/systemd/$SERVICE_NAME"
SERVICE_DST="/etc/systemd/system/$SERVICE_NAME"

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root. Use: sudo $0"
    exit 1
fi

if [[ ! -f "$PROJECT_DIR/sandbox/sandbox" ]]; then
    echo "Sandbox binary not found. Run ./scripts/build.sh first."
    exit 1
fi

echo "==> Installing $SERVICE_NAME"
cp "$SERVICE_SRC" "$SERVICE_DST"

# Ensure the ExecStart path matches the actual project directory.
sed -i "s|/home/vps28/Documentos/Dev/Zeus|$PROJECT_DIR|g" "$SERVICE_DST"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# Install WhatsApp bridge service if the bridge exists.
WHATSAPP_SERVICE="zeus-whatsapp-gateway.service"
WHATSAPP_SERVICE_SRC="$PROJECT_DIR/systemd/$WHATSAPP_SERVICE"
if [[ -f "$WHATSAPP_SERVICE_SRC" ]]; then
    echo "==> Installing $WHATSAPP_SERVICE"
    cp "$WHATSAPP_SERVICE_SRC" "/etc/systemd/system/$WHATSAPP_SERVICE"
    sed -i "s|/home/vps28/Documentos/Dev/Zeus|$PROJECT_DIR|g" "/etc/systemd/system/$WHATSAPP_SERVICE"
    systemctl daemon-reload
    systemctl enable "$WHATSAPP_SERVICE"
    echo "To start the WhatsApp bridge, scan the QR code after starting the service:"
    echo "  sudo systemctl start $WHATSAPP_SERVICE"
    echo "  journalctl -u $WHATSAPP_SERVICE -f"
fi

# Install Discord gateway service.
DISCORD_SERVICE="zeus-discord-gateway.service"
DISCORD_SERVICE_SRC="$PROJECT_DIR/systemd/$DISCORD_SERVICE"
if [[ -f "$DISCORD_SERVICE_SRC" ]]; then
    echo "==> Installing $DISCORD_SERVICE"
    cp "$DISCORD_SERVICE_SRC" "/etc/systemd/system/$DISCORD_SERVICE"
    sed -i "s|/home/vps28/Documentos/Dev/Zeus|$PROJECT_DIR|g" "/etc/systemd/system/$DISCORD_SERVICE"
    systemctl daemon-reload
    systemctl enable "$DISCORD_SERVICE"
    echo "To start the Discord gateway:"
    echo "  sudo systemctl start $DISCORD_SERVICE"
    echo "  journalctl -u $DISCORD_SERVICE -f"
fi

echo "==> Service status:"
systemctl status --no-pager "$SERVICE_NAME"

echo ""
echo "Zeus services installed."
echo "Check logs with: journalctl -u $SERVICE_NAME -f"

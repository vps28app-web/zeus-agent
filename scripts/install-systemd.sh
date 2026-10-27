#!/usr/bin/env bash
set -euo pipefail

# Install and enable Zeus systemd services.
# Must be run as root or with sudo.

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! "$PROJECT_DIR" =~ ^/[A-Za-z0-9_./-]+$ ]]; then
    echo "Project path contains unsupported systemd-template characters: $PROJECT_DIR"
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root. Use: sudo $0"
    exit 1
fi

# Sandbox must be built before installing.
if [[ ! -f "$PROJECT_DIR/sandbox/sandbox" ]]; then
    echo "Sandbox binary not found. Run ./scripts/build.sh first."
    exit 1
fi

PROJECT_USER="$(stat -c '%U' "$PROJECT_DIR")"
if [[ "$PROJECT_USER" == "root" || ! "$PROJECT_USER" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
    echo "Project directory must be owned by a non-root service user."
    exit 1
fi

if [[ ! -f "$PROJECT_DIR/.env" || ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    echo "Missing .env or project Python environment. Configure Zeus first."
    exit 1
fi
if [[ -L "$PROJECT_DIR/.env" ]]; then
    echo "Refusing to read credentials through a symlink: $PROJECT_DIR/.env"
    exit 1
fi
chmod 600 "$PROJECT_DIR/.env"
SANDBOX_TOKEN="$("$PROJECT_DIR/.venv/bin/python" -c 'from dotenv import dotenv_values; import sys; print(dotenv_values(sys.argv[1]).get("ZEUS_SANDBOX_AUTH_TOKEN") or "")' "$PROJECT_DIR/.env")"
if [[ ! "$SANDBOX_TOKEN" =~ ^[0-9a-fA-F]{64}$ ]]; then
    echo "Set a 64-character random ZEUS_SANDBOX_AUTH_TOKEN in $PROJECT_DIR/.env first."
    exit 1
fi
SANDBOX_CONFIG_DIR="/etc/zeus"
if [[ -L "$SANDBOX_CONFIG_DIR" ]]; then
    echo "Refusing symlink for sandbox config directory: $SANDBOX_CONFIG_DIR"
    exit 1
fi
install -d -o root -g root -m 700 "$SANDBOX_CONFIG_DIR"
SANDBOX_ENV_FILE="$SANDBOX_CONFIG_DIR/sandbox.env"
if [[ -L "$SANDBOX_ENV_FILE" ]]; then
    echo "Refusing to overwrite symlink: $SANDBOX_ENV_FILE"
    exit 1
fi
umask 077
SANDBOX_ENV_TMP="$(mktemp "$SANDBOX_CONFIG_DIR/sandbox.env.XXXXXX")"
trap 'rm -f -- "$SANDBOX_ENV_TMP"' EXIT
printf 'ZEUS_SANDBOX_AUTH_TOKEN=%s\n' "$SANDBOX_TOKEN" > "$SANDBOX_ENV_TMP"
chmod 600 "$SANDBOX_ENV_TMP"
mv -fT -- "$SANDBOX_ENV_TMP" "$SANDBOX_ENV_FILE"
trap - EXIT
unset SANDBOX_TOKEN

SANDBOX_INSTALL_DIR="/usr/local/lib/zeus"
SANDBOX_BINARY="$SANDBOX_INSTALL_DIR/sandbox"
if [[ -L "$SANDBOX_INSTALL_DIR" || -L "$SANDBOX_BINARY" ]]; then
    echo "Refusing symlink in privileged sandbox install path."
    exit 1
fi
install -d -o root -g root -m 755 "$SANDBOX_INSTALL_DIR"
install -o root -g root -m 755 "$PROJECT_DIR/sandbox/sandbox" "$SANDBOX_BINARY"

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
    sed -i \\
        -e "s|/home/vps28/Documentos/Dev/Zeus|$PROJECT_DIR|g" \\
        -e "s|/home/vps28/.zeus/.env|$PROJECT_DIR/.env|g" \\
        -e "s|^User=vps28$|User=$PROJECT_USER|" \\
        "$dst"
    systemctl daemon-reload
    systemctl enable "$service_name"
}

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

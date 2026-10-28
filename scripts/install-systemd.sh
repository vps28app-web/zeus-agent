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

BUILD_SNAPSHOT=""
SANDBOX_ENV_TMP=""
cleanup() {
    if [[ -n "$SANDBOX_ENV_TMP" ]]; then
        rm -f -- "$SANDBOX_ENV_TMP"
    fi
    if [[ -n "$BUILD_SNAPSHOT" ]]; then
        rm -rf -- "$BUILD_SNAPSHOT"
    fi
}
trap cleanup EXIT

PROJECT_USER="$(stat -c '%U' "$PROJECT_DIR")"
if [[ "$PROJECT_USER" == "root" || ! "$PROJECT_USER" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
    echo "Project directory must be owned by a non-root service user."
    exit 1
fi
if ! command -v git >/dev/null 2>&1; then
    echo "Git is required to verify a clean source checkout."
    exit 1
fi
if ! GIT_STATUS="$(git -c safe.directory="$PROJECT_DIR" -C "$PROJECT_DIR" status --porcelain)"; then
    echo "Could not verify the Git checkout; refusing privileged installation."
    exit 1
fi
if [[ -n "$GIT_STATUS" ]]; then
    echo "Refusing privileged systemd installation from a dirty checkout; commit/revert local changes first."
    exit 1
fi
if ! command -v go >/dev/null 2>&1; then
    echo "Go 1.20+ is required to build the privileged sandbox from the committed source."
    exit 1
fi
if ! GIT_COMMIT="$(git -c safe.directory="$PROJECT_DIR" -C "$PROJECT_DIR" rev-parse --verify HEAD)"; then
    echo "Could not identify the committed source revision; refusing privileged installation."
    exit 1
fi
BUILD_SNAPSHOT="$(mktemp -d /tmp/zeus-install.XXXXXX)"
if ! git -c safe.directory="$PROJECT_DIR" -C "$PROJECT_DIR" archive "$GIT_COMMIT" sandbox systemd | tar -x -C "$BUILD_SNAPSHOT"; then
    echo "Could not create a trusted source snapshot from commit $GIT_COMMIT."
    exit 1
fi
if ! (cd "$BUILD_SNAPSHOT/sandbox" && CGO_ENABLED=0 GOTOOLCHAIN=local go build -o "$BUILD_SNAPSHOT/sandbox-bin" ./cmd/sandbox); then
    echo "Could not build the sandbox from committed source revision $GIT_COMMIT."
    exit 1
fi

if [[ ! -f "$PROJECT_DIR/.zeus-home" || -L "$PROJECT_DIR/.zeus-home" ]]; then
    echo "Missing .zeus-home state-path file. Run scripts/install.sh first."
    exit 1
fi
IFS= read -r STATE_HOME < "$PROJECT_DIR/.zeus-home"
if [[ "$STATE_HOME" != /* || ! "$STATE_HOME" =~ ^/[A-Za-z0-9_./-]+$ || ! -d "$STATE_HOME" ]]; then
    echo "Invalid ZEUS_HOME path recorded in $PROJECT_DIR/.zeus-home"
    exit 1
fi
if [[ "$(realpath -e -- "$STATE_HOME")" != "$STATE_HOME" ]]; then
    echo "ZEUS_HOME contains symlink or non-canonical path components."
    exit 1
fi
if [[ -L "$STATE_HOME" || -L "$STATE_HOME/.env" || ! -f "$STATE_HOME/.env" ]]; then
    echo "Missing or unsafe Zeus state environment file: $STATE_HOME/.env"
    exit 1
fi
if [[ "$(stat -c '%U' "$STATE_HOME")" != "$PROJECT_USER" ]]; then
    echo "ZEUS_HOME must be owned by the same user as the project checkout."
    exit 1
fi
if [[ "$(stat -c '%U' "$STATE_HOME/.env")" != "$PROJECT_USER" ]]; then
    echo "ZEUS_HOME/.env must be owned by the project user."
    exit 1
fi
chmod 600 "$STATE_HOME/.env"
SANDBOX_TOKEN=""
while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    line="${line#"${line%%[![:space:]]*}"}"
    if [[ "$line" == export[[:space:]]* ]]; then
        line="${line#export}"
        line="${line#"${line%%[![:space:]]*}"}"
    fi
    case "$line" in
        ZEUS_SANDBOX_AUTH_TOKEN=*)
            SANDBOX_TOKEN="${line#*=}"
            SANDBOX_TOKEN="${SANDBOX_TOKEN#"${SANDBOX_TOKEN%%[![:space:]]*}"}"
            SANDBOX_TOKEN="${SANDBOX_TOKEN%"${SANDBOX_TOKEN##*[![:space:]]}"}"
            if [[ "${SANDBOX_TOKEN:0:1}" == '"' && "${SANDBOX_TOKEN: -1}" == '"' ]]; then
                SANDBOX_TOKEN="${SANDBOX_TOKEN:1:${#SANDBOX_TOKEN}-2}"
            elif [[ "${SANDBOX_TOKEN:0:1}" == "'" && "${SANDBOX_TOKEN: -1}" == "'" ]]; then
                SANDBOX_TOKEN="${SANDBOX_TOKEN:1:${#SANDBOX_TOKEN}-2}"
            fi
            ;;
    esac
done < "$STATE_HOME/.env"
if [[ ! "$SANDBOX_TOKEN" =~ ^[0-9a-fA-F]{64}$ ]]; then
    echo "Set a 64-character random ZEUS_SANDBOX_AUTH_TOKEN in $STATE_HOME/.env first."
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
printf 'ZEUS_SANDBOX_AUTH_TOKEN=%s\n' "$SANDBOX_TOKEN" > "$SANDBOX_ENV_TMP"
chmod 600 "$SANDBOX_ENV_TMP"
mv -fT -- "$SANDBOX_ENV_TMP" "$SANDBOX_ENV_FILE"
SANDBOX_ENV_TMP=""
unset SANDBOX_TOKEN

SANDBOX_INSTALL_DIR="/usr/local/lib/zeus"
SANDBOX_BINARY="$SANDBOX_INSTALL_DIR/sandbox"
if [[ -L "$SANDBOX_INSTALL_DIR" || -L "$SANDBOX_BINARY" ]]; then
    echo "Refusing symlink in privileged sandbox install path."
    exit 1
fi
install -d -o root -g root -m 755 "$SANDBOX_INSTALL_DIR"
install -o root -g root -m 755 "$BUILD_SNAPSHOT/sandbox-bin" "$SANDBOX_BINARY"

install_service() {
    local service_name="$1"
    local enable_service="${2:-no}"
    local src="$BUILD_SNAPSHOT/systemd/$service_name"
    local dst="/etc/systemd/system/$service_name"

    if [[ ! -f "$src" ]]; then
        echo "Service file not found: $src"
        return 1
    fi

    echo "==> Installing $service_name"
    cp "$src" "$dst"
    sed -i \\
        -e "s|/home/vps28/Documentos/Dev/Zeus|$PROJECT_DIR|g" \\
        -e "s|/home/vps28/.zeus|$STATE_HOME|g" \\
        -e "s|^User=vps28$|User=$PROJECT_USER|" \\
        "$dst"
    systemctl daemon-reload
    if [[ "$enable_service" == "yes" ]]; then
        systemctl enable "$service_name"
    fi
}

install_service "zeus-sandbox.service" yes
install_service "zeus-telegram-gateway.service"
install_service "zeus-discord-gateway.service"
install_service "zeus-whatsapp-bridge.service"
install_service "zeus-whatsapp-gateway.service"

# Restart sandbox; leave chat gateways stopped until configured.
systemctl restart zeus-sandbox.service

echo ""
echo "Zeus services installed."
echo "Sandbox is running and enabled at boot."
echo ""
echo "Chat gateway units are installed but disabled; start after configuring .env:"
echo "  sudo systemctl start zeus-telegram-gateway.service"
echo "  sudo systemctl start zeus-discord-gateway.service"
echo "  sudo systemctl start zeus-whatsapp-bridge.service"
echo "  sudo systemctl start zeus-whatsapp-gateway.service"
echo "Enable one persistently with: sudo systemctl enable --now zeus-telegram-gateway.service"

echo ""
echo "Check logs with:"
echo "  journalctl -u zeus-telegram-gateway.service -f"
echo "  journalctl -u zeus-discord-gateway.service -f"
echo "  journalctl -u zeus-whatsapp-bridge.service -f"
echo "  journalctl -u zeus-whatsapp-gateway.service -f"

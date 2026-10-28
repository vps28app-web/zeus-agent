#!/usr/bin/env bash
set -euo pipefail

# Install Zeus from the source checkout containing this script. Does not require sudo.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_HOME="${ZEUS_HOME:-$HOME/.zeus}"
VENV_DIR="$PROJECT_DIR/.venv"
STATE_ENV="$STATE_HOME/.env"
STATE_HOME_FILE="$PROJECT_DIR/.zeus-home"

if [[ $EUID -eq 0 ]]; then
    echo "Run this installer as your normal user, not with sudo."
    exit 1
fi
if [[ ! -f "$PROJECT_DIR/pyproject.toml" || ! -d "$PROJECT_DIR/zeus" ]]; then
    echo "Run scripts/install.sh from a Zeus source checkout."
    exit 1
fi
if [[ "$STATE_HOME" != /* ]]; then
    echo "ZEUS_HOME must be an absolute path."
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.8+ is required. Install Python and its venv module first."
    exit 1
fi
RESOLVED_STATE_HOME="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$STATE_HOME")"
if [[ "$RESOLVED_STATE_HOME" != "$STATE_HOME" ]]; then
    echo "ZEUS_HOME must not contain symlink or non-canonical path components: $STATE_HOME"
    echo "Resolved path: $RESOLVED_STATE_HOME"
    exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)'; then
    echo "Python 3.8+ is required."
    exit 1
fi

printf 'Installing Zeus from: %s\n' "$PROJECT_DIR"
printf 'Zeus state directory: %s\n' "$STATE_HOME"

# Keep user configuration and credentials outside the source tree.
if [[ -L "$STATE_HOME" ]]; then
    echo "Refusing to use a symlink as ZEUS_HOME: $STATE_HOME"
    exit 1
fi
mkdir -p "$STATE_HOME"
chmod 700 "$STATE_HOME"
if [[ -L "$STATE_ENV" ]]; then
    echo "Refusing to write credentials through a symlink: $STATE_ENV"
    exit 1
fi
umask 077
if [[ ! -f "$STATE_ENV" ]]; then
    cat > "$STATE_ENV" <<'EOF'
# Zeus user configuration. Run `zeus setup` to select a provider and add API credentials.
ZEUS_PROVIDER=openrouter
ZEUS_MODEL=openrouter/auto
ZEUS_USE_SQLITE=true
ZEUS_EXECUTION_PERMISSION=sandbox_only
ZEUS_FILE_PERMISSION=read_only
EOF
fi
chmod 600 "$STATE_ENV"

# Record the state path for the root-owned systemd installer; this file has no secrets.
if [[ -L "$STATE_HOME_FILE" ]]; then
    echo "Refusing to write state-home configuration through a symlink: $STATE_HOME_FILE"
    exit 1
fi
STATE_HOME_TMP="$(mktemp "$PROJECT_DIR/.zeus-home.XXXXXX")"
trap 'rm -f -- "$STATE_HOME_TMP"' EXIT
printf '%s\n' "$STATE_HOME" > "$STATE_HOME_TMP"
chmod 600 "$STATE_HOME_TMP"
python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' "$STATE_HOME_TMP" "$STATE_HOME_FILE"
trap - EXIT

# Create a project-local virtualenv and install the package entry points.
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    python3 -m venv "$VENV_DIR" || {
        echo "Could not create the virtualenv. On Debian/Ubuntu install python3-venv."
        exit 1
    }
fi
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -e "$PROJECT_DIR"

# Generate one random sandbox token in the private state .env.
SANDBOX_TOKEN="$("$VENV_DIR/bin/python" -c 'from dotenv import dotenv_values; import sys; print(dotenv_values(sys.argv[1]).get("ZEUS_SANDBOX_AUTH_TOKEN") or "")' "$STATE_ENV")"
if [[ -z "$SANDBOX_TOKEN" ]]; then
    SANDBOX_TOKEN="$("$VENV_DIR/bin/python" -c 'import secrets; print(secrets.token_hex(32))')"
    printf '\nZEUS_SANDBOX_AUTH_TOKEN=%s\n' "$SANDBOX_TOKEN" >> "$STATE_ENV"
fi
if [[ ! "$SANDBOX_TOKEN" =~ ^[0-9a-fA-F]{64}$ ]]; then
    echo "ZEUS_SANDBOX_AUTH_TOKEN must be 64 hexadecimal characters (32 random bytes)."
    exit 1
fi
unset SANDBOX_TOKEN
chmod 600 "$STATE_ENV"

# Build the optional sandbox only on its supported runtime platform.
SANDBOX_BUILT=0
if [[ "${ZEUS_SKIP_SANDBOX:-0}" != "1" ]] && command -v go >/dev/null 2>&1; then
    if [[ "$(uname -s)" == "Linux" && "$(uname -m)" == "x86_64" ]]; then
        if (cd "$PROJECT_DIR/sandbox" && go build -o sandbox ./cmd/sandbox); then
            SANDBOX_BUILT=1
            echo "Go sandbox built."
        else
            echo "WARNING: sandbox build failed; isolated code execution is unavailable."
        fi
    else
        echo "Skipping Go sandbox: runtime support requires Linux amd64."
    fi
else
    echo "Skipping Go sandbox: Go is missing or ZEUS_SKIP_SANDBOX=1."
fi

# Add convenience launchers without overwriting an unrelated user command.
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
write_launcher() {
    local name="$1"
    local entrypoint="$2"
    local target="$BIN_DIR/$name"
    if [[ -e "$target" || -L "$target" ]]; then
        if ! grep -Fq '# Managed by Zeus Agent installer' "$target" 2>/dev/null; then
            echo "Keeping existing command unchanged: $target"
            return 0
        fi
    fi
    local tmp
    tmp="$(mktemp "$BIN_DIR/.${name}.XXXXXX")"
    {
        printf '#!/usr/bin/env bash\n# Managed by Zeus Agent installer\n'
        printf 'ZEUS_INSTALL_DIR=%q\n' "$PROJECT_DIR"
        printf 'ZEUS_DEFAULT_HOME=%q\n' "$STATE_HOME"
        printf 'export ZEUS_HOME="${ZEUS_HOME:-$ZEUS_DEFAULT_HOME}"\n'
        printf 'cd "$ZEUS_INSTALL_DIR"\n'
        printf 'exec "$ZEUS_INSTALL_DIR/.venv/bin/%s" "$@"\n' "$entrypoint"
    } > "$tmp"
    chmod 755 "$tmp"
    python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' "$tmp" "$target"
}
write_launcher zeus zeus
write_launcher Zeus Zeus
write_launcher zeus-gateway zeus-gateway

printf '\nZeus installed successfully.\n'
printf 'Install directory: %s\nState directory:   %s\n' "$PROJECT_DIR" "$STATE_HOME"
printf 'Next: zeus setup\n'
if [[ "$SANDBOX_BUILT" == "1" ]]; then
    printf 'Optional privileged sandbox service: sudo %s/scripts/install-systemd.sh\n' "$PROJECT_DIR"
else
    printf 'For isolated code execution, install Go and build the Linux amd64 sandbox; see docs/SANDBOX.md.\n'
fi
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) printf 'Add %s to PATH to use the zeus commands directly.\n' "$BIN_DIR" ;;
esac

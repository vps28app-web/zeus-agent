'use strict';

// Pure resolution logic for the npm `zeus` launcher. Kept free of process
// dependencies so it can be unit-tested with a fake filesystem.

const REPOSITORY_MARKERS = ['pyproject.toml', 'zeus', 'scripts/install.sh'];

function pathFor(platform) {
  const path = require('node:path');
  return platform === 'win32' ? path.win32 : path;
}

function isCanonicalAbsolutePath(candidate) {
  if (typeof candidate !== 'string' || candidate.length === 0) return false;
  if (candidate.includes('\0') || /[\r\n]/.test(candidate)) return false;
  if (candidate.length > 1 && /[\\/]+$/.test(candidate)) return false;
  const path = require('node:path');
  if (!path.isAbsolute(candidate)) return false;
  return path.normalize(candidate) === candidate;
}

function findCheckoutAbove(startDirectory, existsSync) {
  const path = require('node:path');
  let directory = path.resolve(startDirectory);
  for (;;) {
    const looksLikeZeusCheckout = REPOSITORY_MARKERS.every(
      (marker) => existsSync(path.join(directory, marker)),
    );
    if (looksLikeZeusCheckout) return directory;
    const parent = path.dirname(directory);
    if (parent === directory) return null;
    directory = parent;
  }
}

function entryPath(installDir, platform, entryName) {
  const path = pathFor(platform);
  const suffix = platform === 'win32' ? '.exe' : '';
  const binDir = platform === 'win32' ? 'Scripts' : 'bin';
  return path.join(installDir, '.venv', binDir, entryName + suffix);
}

function defaultInstallDirectory(home) {
  const path = require('node:path');
  return path.join(home, '.local', 'share', 'zeus-agent');
}

function readRegistryDirectory(stateHome, readFileSync) {
  const path = require('node:path');
  let content;
  try {
    content = readFileSync(path.join(stateHome, 'install-dir'), 'utf8');
  } catch {
    return null;
  }
  const firstLine = String(content).split(/\r?\n/, 1)[0].trim();
  return isCanonicalAbsolutePath(firstLine) ? firstLine : null;
}

function resolveInstallDirectory(options) {
  const {
    envInstallDir,
    cwd,
    home,
    stateHome,
    platform = process.platform,
    existsSync = () => false,
    readFileSync = () => {
      throw new Error('sem registro de instalação');
    },
  } = options;
  const path = require('node:path');
  const tried = [];

  const attempt = (installDir, source) => {
    const entry = entryPath(installDir, platform, 'zeus');
    tried.push(installDir);
    return existsSync(entry) ? { installDir, entry, source } : null;
  };

  if (typeof envInstallDir === 'string' && envInstallDir.trim()) {
    if (!path.isAbsolute(envInstallDir)) {
      return {
        error: `ZEUS_INSTALL_DIR precisa ser um caminho absoluto: ${envInstallDir}`,
        tried,
      };
    }
    const resolved = attempt(path.resolve(envInstallDir), 'env');
    if (resolved) return resolved;
    return {
      error: `ZEUS_INSTALL_DIR não aponta para uma instalação do Zeus (.venv/bin/zeus ausente): ${envInstallDir}`,
      tried,
    };
  }

  const checkout = findCheckoutAbove(cwd, existsSync);
  if (checkout) {
    const resolved = attempt(checkout, 'checkout');
    if (resolved) return resolved;
  }

  const registry = readRegistryDirectory(stateHome, readFileSync);
  if (registry) {
    const resolved = attempt(registry, 'registry');
    if (resolved) return resolved;
  }

  const fallback = defaultInstallDirectory(home);
  const resolved = attempt(fallback, 'default');
  if (resolved) return resolved;

  const hint = checkout
    ? ` Um checkout do Zeus existe em ${checkout}, mas sem .venv; execute scripts/install.sh nesse checkout primeiro.`
    : ' Instale o Zeus primeiro: rode scripts/install.sh em um checkout ou npx --yes --package=git+https://github.com/vps28app-web/zeus-agent.git zeus-install.';
  return {
    error: `Nenhuma instalação do Zeus encontrada${tried.length ? ` (tentativas: ${tried.join(', ')})` : ''}.${hint}`,
    tried,
  };
}

function entryNameForLauncher(invokedName) {
  const base = String(invokedName || '').replace(/\.exe$/i, '');
  return base === 'zeus-gateway' ? 'zeus-gateway' : 'zeus';
}

module.exports = {
  defaultInstallDirectory,
  entryNameForLauncher,
  entryPath,
  findCheckoutAbove,
  isCanonicalAbsolutePath,
  readRegistryDirectory,
  resolveInstallDirectory,
};

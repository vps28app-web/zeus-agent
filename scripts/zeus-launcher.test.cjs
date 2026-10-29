const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {
  defaultInstallDirectory,
  entryNameForLauncher,
  entryPath,
  findCheckoutAbove,
  isCanonicalAbsolutePath,
  readRegistryDirectory,
  resolveInstallDirectory,
} = require('./zeus-launcher-lib.cjs');

function tempRoot() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'zeus-launcher-test-'));
}

function makeVenv(installDir, entryName = 'zeus') {
  fs.mkdirSync(path.join(installDir, '.venv', 'bin'), { recursive: true });
  fs.writeFileSync(path.join(installDir, '.venv', 'bin', entryName), '#!/bin/sh\n');
}

function makeInstall(root) {
  const dir = fs.mkdtempSync(path.join(root, 'install-'));
  makeVenv(dir);
  return dir;
}

function makeCheckout(root, { withVenv = true } = {}) {
  const dir = fs.mkdtempSync(path.join(root, 'checkout-'));
  fs.mkdirSync(path.join(dir, 'zeus'), { recursive: true });
  fs.mkdirSync(path.join(dir, 'scripts'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'pyproject.toml'), '[project]\nname = "zeus-agent"\n');
  fs.writeFileSync(path.join(dir, 'scripts', 'install.sh'), '#!/usr/bin/env bash\n');
  if (withVenv) makeVenv(dir);
  return dir;
}

function makeStateHome(root, installDir) {
  const dir = fs.mkdtempSync(path.join(root, 'state-'));
  if (installDir) fs.writeFileSync(path.join(dir, 'install-dir'), `${installDir}\n`);
  return dir;
}

function resolve(options) {
  return resolveInstallDirectory({
    platform: 'linux',
    existsSync: fs.existsSync,
    readFileSync: fs.readFileSync,
    ...options,
  });
}

test('maps launcher names to venv entry points', () => {
  assert.equal(entryNameForLauncher('zeus'), 'zeus');
  assert.equal(entryNameForLauncher('Zeus'), 'zeus');
  assert.equal(entryNameForLauncher('zeus-launcher.cjs'), 'zeus');
  assert.equal(entryNameForLauncher('zeus-gateway'), 'zeus-gateway');
  assert.equal(entryNameForLauncher('zeus-gateway.exe'), 'zeus-gateway');
  assert.equal(entryNameForLauncher(undefined), 'zeus');
});

test('builds platform-specific venv entry paths', () => {
  assert.equal(entryPath('/opt/zeus', 'linux', 'zeus'), '/opt/zeus/.venv/bin/zeus');
  assert.equal(
    entryPath('C:\\zeus', 'win32', 'zeus-gateway'),
    'C:\\zeus\\.venv\\Scripts\\zeus-gateway.exe',
  );
});

test('validates canonical absolute paths for the registry', () => {
  assert.equal(isCanonicalAbsolutePath('/opt/zeus'), true);
  assert.equal(isCanonicalAbsolutePath('zeus'), false);
  assert.equal(isCanonicalAbsolutePath('/opt/zeus/'), false);
  assert.equal(isCanonicalAbsolutePath('/opt/../opt/zeus'), false);
  assert.equal(isCanonicalAbsolutePath('/opt/zeus\nrm -rf /'), false);
  assert.equal(isCanonicalAbsolutePath(''), false);
});

test('reads the install-dir registry defensively', () => {
  const root = tempRoot();
  assert.equal(readRegistryDirectory(makeStateHome(root, '/opt/zeus'), fs.readFileSync), '/opt/zeus');
  const empty = fs.mkdtempSync(path.join(root, 'state-'));
  assert.equal(readRegistryDirectory(empty, fs.readFileSync), null);
  const garbage = fs.mkdtempSync(path.join(root, 'state-'));
  fs.writeFileSync(path.join(garbage, 'install-dir'), 'cd /tmp && rm -rf ~\n');
  assert.equal(readRegistryDirectory(garbage, fs.readFileSync), null);
  const relative = fs.mkdtempSync(path.join(root, 'state-'));
  fs.writeFileSync(path.join(relative, 'install-dir'), 'zeus\n');
  assert.equal(readRegistryDirectory(relative, fs.readFileSync), null);
});

test('prefers ZEUS_INSTALL_DIR when it points at a valid install', () => {
  const root = tempRoot();
  const envInstall = makeInstall(root);
  const registryInstall = makeInstall(root);
  const stateHome = makeStateHome(root, registryInstall);
  const result = resolve({ envInstallDir: envInstall, cwd: root, home: root, stateHome });
  assert.equal(result.source, 'env');
  assert.equal(result.installDir, envInstall);
  assert.equal(result.entry, path.join(envInstall, '.venv', 'bin', 'zeus'));
});

test('rejects a broken ZEUS_INSTALL_DIR instead of silently falling back', () => {
  const root = tempRoot();
  const broken = fs.mkdtempSync(path.join(root, 'broken-'));
  const registryInstall = makeInstall(root);
  const stateHome = makeStateHome(root, registryInstall);
  const result = resolve({ envInstallDir: broken, cwd: root, home: root, stateHome });
  assert.match(result.error, /ZEUS_INSTALL_DIR/);
  const relative = resolve({ envInstallDir: 'zeus', cwd: root, home: root, stateHome });
  assert.match(relative.error, /caminho absoluto/);
});

test('prefers a Zeus checkout above the current directory over the registry', () => {
  const root = tempRoot();
  const checkout = makeCheckout(root);
  const registryInstall = makeInstall(root);
  const stateHome = makeStateHome(root, registryInstall);
  const nested = path.join(checkout, 'zeus', 'cli', 'nested');
  fs.mkdirSync(nested, { recursive: true });
  const result = resolve({ cwd: nested, home: root, stateHome });
  assert.equal(result.source, 'checkout');
  assert.equal(result.installDir, checkout);
});

test('falls back to the registry when run outside a checkout', () => {
  const root = tempRoot();
  const outside = fs.mkdtempSync(path.join(root, 'cwd-'));
  const registryInstall = makeInstall(root);
  const stateHome = makeStateHome(root, registryInstall);
  const result = resolve({ cwd: outside, home: root, stateHome });
  assert.equal(result.source, 'registry');
  assert.equal(result.installDir, registryInstall);
});

test('falls back to the default install directory', () => {
  const root = tempRoot();
  const home = fs.mkdtempSync(path.join(root, 'home-'));
  const defaultInstall = defaultInstallDirectory(home);
  makeVenv(defaultInstall);
  const outside = fs.mkdtempSync(path.join(root, 'cwd-'));
  const stateHome = fs.mkdtempSync(path.join(root, 'state-'));
  const result = resolve({ cwd: outside, home, stateHome });
  assert.equal(result.source, 'default');
  assert.equal(result.installDir, defaultInstall);
});

test('reports a helpful error when no installation exists', () => {
  const root = tempRoot();
  const outside = fs.mkdtempSync(path.join(root, 'cwd-'));
  const home = fs.mkdtempSync(path.join(root, 'home-'));
  const stateHome = fs.mkdtempSync(path.join(root, 'state-'));
  const result = resolve({ cwd: outside, home, stateHome });
  assert.match(result.error, /Nenhuma instalação do Zeus/);
  assert.match(result.error, /zeus-install/);
});

test('suggests installing inside a checkout that lacks a venv', () => {
  const root = tempRoot();
  const checkout = makeCheckout(root, { withVenv: false });
  const home = fs.mkdtempSync(path.join(root, 'home-'));
  const stateHome = fs.mkdtempSync(path.join(root, 'state-'));
  const result = resolve({ cwd: checkout, home, stateHome });
  assert.match(result.error, /scripts\/install\.sh/);
  assert.match(result.error, new RegExp(checkout.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});

test('finds a Zeus checkout above any nested directory', () => {
  const root = tempRoot();
  const checkout = makeCheckout(root, { withVenv: false });
  const nested = path.join(checkout, 'zeus', 'tools');
  assert.equal(findCheckoutAbove(nested, fs.existsSync), checkout);
  const elsewhere = fs.mkdtempSync(path.join(root, 'cwd-'));
  assert.equal(findCheckoutAbove(elsewhere, fs.existsSync), null);
});

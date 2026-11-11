const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const repoRoot = path.resolve(__dirname, '..');
const installScript = path.join(__dirname, 'install-desktop.sh');
const uninstallScript = path.join(__dirname, 'uninstall-desktop.sh');
const releaseBin = path.join(repoRoot, 'desktop', 'target', 'release', 'zeus-desktop');

test('install-desktop.sh and uninstall-desktop.sh support --help', () => {
  const r1 = spawnSync('bash', [installScript, '--help'], { encoding: 'utf8' });
  assert.equal(r1.status, 0);
  assert.match(r1.stdout, /--no-build/);
  assert.match(r1.stdout, /--with-core/);
  assert.match(r1.stdout, /--skip-core/);

  const r2 = spawnSync('bash', [uninstallScript, '--help'], { encoding: 'utf8' });
  assert.equal(r2.status, 0);
  assert.match(r2.stdout, /--state/);
});

test('install-desktop.sh checks and installs Zeus Core base by default when missing', (t) => {
  const fakeRepo = fs.mkdtempSync(path.join(os.tmpdir(), 'zeus-desktop-core-check-'));
  t.after(() => fs.rmSync(fakeRepo, { recursive: true, force: true }));

  fs.mkdirSync(path.join(fakeRepo, 'scripts'), { recursive: true });
  fs.mkdirSync(path.join(fakeRepo, 'desktop', 'target', 'release'), { recursive: true });
  fs.mkdirSync(path.join(fakeRepo, 'desktop', 'assets'), { recursive: true });
  fs.mkdirSync(path.join(fakeRepo, 'zeus'), { recursive: true });

  fs.copyFileSync(installScript, path.join(fakeRepo, 'scripts', 'install-desktop.sh'));
  fs.writeFileSync(path.join(fakeRepo, 'desktop', 'Cargo.toml'), '[package]\nname="zeus-desktop"\n');
  fs.writeFileSync(path.join(fakeRepo, 'desktop', 'assets', 'zeus-desktop.svg'), '<svg/>');
  fs.writeFileSync(path.join(fakeRepo, 'desktop', 'target', 'release', 'zeus-desktop'), '#!/bin/sh\nexit 0\n', { mode: 0o755 });

  const markerFile = path.join(fakeRepo, 'core-installed.marker');
  fs.writeFileSync(
    path.join(fakeRepo, 'scripts', 'install.sh'),
    [
      '#!/usr/bin/env bash',
      'set -e',
      `touch ${JSON.stringify(markerFile)}`,
      `mkdir -p ${JSON.stringify(path.join(fakeRepo, '.venv', 'bin'))}`,
      `cat > ${JSON.stringify(path.join(fakeRepo, '.venv', 'bin', 'python3'))} <<'PY'`,
      '#!/usr/bin/env bash',
      'exit 0',
      'PY',
      `chmod +x ${JSON.stringify(path.join(fakeRepo, '.venv', 'bin', 'python3'))}`,
    ].join('\n'),
    { mode: 0o755 }
  );

  const fakeHome = path.join(fakeRepo, 'home');
  const env = {
    ...process.env,
    HOME: fakeHome,
    ZEUS_HOME: path.join(fakeHome, '.zeus'),
    ZEUS_DESKTOP_PREFIX: path.join(fakeHome, '.local'),
    XDG_DATA_HOME: path.join(fakeHome, '.local', 'share'),
  };

  const res = spawnSync('bash', [path.join(fakeRepo, 'scripts', 'install-desktop.sh'), '--no-build'], {
    env,
    encoding: 'utf8',
  });
  assert.equal(res.status, 0, `expected core+desktop install to succeed: ${res.stderr}\n${res.stdout}`);
  assert.ok(fs.existsSync(markerFile), 'scripts/install.sh must be invoked automatically when core is missing');
});

test('install-desktop.sh --no-build installs and uninstall-desktop.sh removes cleanly in isolated HOME', (t) => {
  if (!fs.existsSync(releaseBin)) {
    t.skip('Release binary not built in desktop/target/release/zeus-desktop');
    return;
  }

  const fakeHome = fs.mkdtempSync(path.join(os.tmpdir(), 'zeus-desktop-inst-'));
  t.after(() => fs.rmSync(fakeHome, { recursive: true, force: true }));

  const prefix = path.join(fakeHome, '.local');
  const dataHome = path.join(fakeHome, '.local', 'share');
  const stateHome = path.join(fakeHome, '.zeus');

  const env = {
    ...process.env,
    HOME: fakeHome,
    ZEUS_HOME: stateHome,
    ZEUS_DESKTOP_PREFIX: prefix,
    XDG_DATA_HOME: dataHome,
  };

  const inst = spawnSync('bash', [installScript, '--no-build'], { env, encoding: 'utf8' });
  assert.equal(inst.status, 0, `install failed: ${inst.stderr}\n${inst.stdout}`);

  const launcherPath = path.join(prefix, 'bin', 'zeus-desktop');
  const installedBin = path.join(prefix, 'lib', 'zeus-desktop', 'zeus-desktop');
  const desktopFile = path.join(dataHome, 'applications', 'zeus-desktop.desktop');
  const iconFile = path.join(dataHome, 'icons', 'hicolor', 'scalable', 'apps', 'zeus-desktop.svg');

  assert.ok(fs.existsSync(launcherPath), 'launcher should exist');
  assert.ok(fs.existsSync(installedBin), 'binary should exist');
  assert.ok(fs.existsSync(desktopFile), '.desktop file should exist');
  assert.ok(fs.existsSync(iconFile), 'SVG icon should exist');

  const launcherContent = fs.readFileSync(launcherPath, 'utf8');
  assert.match(launcherContent, /# Managed by Zeus Desktop installer/);
  assert.ok(launcherContent.includes(installedBin));

  const desktopContent = fs.readFileSync(desktopFile, 'utf8');
  assert.ok(desktopContent.includes(`Exec=${launcherPath}`));
  assert.ok(desktopContent.includes('Icon=zeus-desktop'));

  const uninst = spawnSync('bash', [uninstallScript], { env, encoding: 'utf8' });
  assert.equal(uninst.status, 0, `uninstall failed: ${uninst.stderr}\n${uninst.stdout}`);

  assert.ok(!fs.existsSync(launcherPath), 'launcher should be removed');
  assert.ok(!fs.existsSync(installedBin), 'binary should be removed');
  assert.ok(!fs.existsSync(desktopFile), '.desktop file should be removed');
  assert.ok(!fs.existsSync(iconFile), 'SVG icon should be removed');
});

test('install-desktop.sh preserves unmanaged existing zeus-desktop binary', (t) => {
  if (!fs.existsSync(releaseBin)) {
    t.skip('Release binary not built');
    return;
  }

  const fakeHome = fs.mkdtempSync(path.join(os.tmpdir(), 'zeus-desktop-preserve-'));
  t.after(() => fs.rmSync(fakeHome, { recursive: true, force: true }));

  const prefix = path.join(fakeHome, '.local');
  const binDir = path.join(prefix, 'bin');
  fs.mkdirSync(binDir, { recursive: true });
  const customLauncher = path.join(binDir, 'zeus-desktop');
  fs.writeFileSync(customLauncher, '#!/bin/sh\necho custom\n');

  const env = {
    ...process.env,
    HOME: fakeHome,
    ZEUS_HOME: path.join(fakeHome, '.zeus'),
    ZEUS_DESKTOP_PREFIX: prefix,
    XDG_DATA_HOME: path.join(fakeHome, '.local', 'share'),
  };

  const inst = spawnSync('bash', [installScript, '--no-build'], { env, encoding: 'utf8' });
  assert.equal(inst.status, 0, inst.stderr);
  assert.equal(fs.readFileSync(customLauncher, 'utf8'), '#!/bin/sh\necho custom\n');
});

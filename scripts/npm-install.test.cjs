const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {
  assertNodeVersion,
  assertLinuxAmd64,
  assertCleanCheckout,
  buildAptInstallCommand,
  getInstallDirectory,
  isDebianFamily,
  isOfficialRemote,
  needsPrerequisiteInstall,
  parseGoVersion,
  parsePythonVersion,
} = require('./npm-install-lib.cjs');

test('accepts Linux amd64 for the full systemd sandbox installer', () => {
  assert.doesNotThrow(() => assertLinuxAmd64('linux', 'x64'));
});

test('requires Node.js 18 or newer for the npm installer', () => {
  assert.doesNotThrow(() => assertNodeVersion('v20.10.0'));
  assert.throws(() => assertNodeVersion('v16.20.2'), /Node.js 18/);
});

test('rejects hosts without the Linux amd64 sandbox backend', () => {
  assert.throws(() => assertLinuxAmd64('win32', 'x64'), /Linux amd64/);
  assert.throws(() => assertLinuxAmd64('linux', 'arm64'), /Linux amd64/);
  assert.throws(() => assertLinuxAmd64('darwin', 'x64'), /Linux amd64/);
});

test('parses Python and Go versions from their command output', () => {
  assert.deepEqual(parsePythonVersion('Python 3.12.4'), [3, 12, 4]);
  assert.deepEqual(parseGoVersion('go version go1.22.2 linux/amd64'), [1, 22, 2]);
});

test('marks required runtimes and venv support for package installation', () => {
  assert.deepEqual(
    needsPrerequisiteInstall({ pythonVersion: [3, 12, 1], venvAvailable: true, gitAvailable: true, goVersion: [1, 22, 2] }),
    [],
  );
  assert.deepEqual(
    needsPrerequisiteInstall({ pythonVersion: [3, 12, 1], venvAvailable: false, gitAvailable: true, goVersion: [1, 22, 2] }),
    ['python3-venv'],
  );
  assert.deepEqual(
    needsPrerequisiteInstall({ pythonVersion: [3, 7, 9], venvAvailable: false, gitAvailable: false, goVersion: [1, 19, 9] }),
    ['git', 'python3', 'python3-venv', 'golang-go'],
  );
});

test('recognizes Debian-family distributions for automated prerequisite setup', () => {
  assert.equal(isDebianFamily('ID=pop\nID_LIKE="ubuntu debian"'), true);
  assert.equal(isDebianFamily('ID=fedora\nID_LIKE="rhel"'), false);
});

test('keeps the cloned installation source in the user data directory', () => {
  assert.equal(getInstallDirectory('/home/alice'), path.join('/home/alice', '.local', 'share', 'zeus-agent'));
});

test('accepts only the official GitHub repository as a source checkout', () => {
  assert.equal(isOfficialRemote('git@github.com:vps28app-web/zeus-agent.git'), true);
  assert.equal(isOfficialRemote('https://github.com/vps28app-web/zeus-agent.git'), true);
  assert.equal(isOfficialRemote('https://example.com/zeus-agent.git'), false);
});

test('requires a clean checkout before root-owned installation', () => {
  assert.doesNotThrow(() => assertCleanCheckout(''));
  assert.throws(() => assertCleanCheckout(' M scripts/install.sh\n'), /checkout Git limpo/);
});

test('builds a fixed apt command from allow-listed package names', () => {
  assert.equal(
    buildAptInstallCommand(['git', 'python3-venv']),
    'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y -- git python3-venv',
  );
  assert.throws(() => buildAptInstallCommand(['python3; touch /tmp/pwned']), /invalid package name/);
});

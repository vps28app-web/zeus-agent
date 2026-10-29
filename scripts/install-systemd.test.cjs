const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const installerPath = path.join(__dirname, 'install-systemd.sh');
const installer = fs.readFileSync(installerPath, 'utf8');
const sedStart = installer.indexOf('    sed -i');
const sedEnd = installer.indexOf('\n    systemctl daemon-reload', sedStart);
assert.notEqual(sedStart, -1, 'install_service must contain the systemd unit sed command');
assert.notEqual(sedEnd, -1, 'sed command must be followed by systemctl daemon-reload');
const sedCommand = installer.slice(sedStart, sedEnd);

test('rewrites systemd unit paths and service user in one sed invocation', (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'zeus-systemd-test-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const unitPath = path.join(directory, 'zeus-sandbox.service');
  fs.writeFileSync(unitPath, [
    'WorkingDirectory=/home/vps28/Documentos/Dev/Zeus',
    'EnvironmentFile=/home/vps28/.zeus/.env',
    'User=vps28',
    '',
  ].join('\n'));

  const script = [
    'set -e',
    'PROJECT_DIR=/home/valdeir/.local/share/zeus-agent',
    'STATE_HOME=/home/valdeir/.zeus',
    'PROJECT_USER=valdeir',
    `dst=${JSON.stringify(unitPath)}`,
    sedCommand,
  ].join('\n');
  const result = spawnSync('bash', ['-c', script], { encoding: 'utf8' });

  assert.equal(result.status, 0, `sed command failed: ${result.stderr}`);
  assert.equal(fs.readFileSync(unitPath, 'utf8'), [
    'WorkingDirectory=/home/valdeir/.local/share/zeus-agent',
    'EnvironmentFile=/home/valdeir/.zeus/.env',
    'User=valdeir',
    '',
  ].join('\n'));
});

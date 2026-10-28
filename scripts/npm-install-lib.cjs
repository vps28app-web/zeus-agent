function assertNodeVersion(version) {
  const match = String(version || '').match(/^v?(\d+)/);
  if (!match || Number(match[1]) < 18) {
    throw new Error('O instalador npm requer Node.js 18 ou superior.');
  }
}

function assertLinuxAmd64(platform, arch) {
  if (platform !== 'linux' || arch !== 'x64') {
    throw new Error('A instalação completa da sandbox exige Linux amd64 com systemd. No Windows, use WSL2 com systemd habilitado.');
  }
}

function parseVersion(output) {
  const match = String(output).match(/(?:Python\s+|go version go)?(\d+)\.(\d+)(?:\.(\d+))?/i);
  if (!match) return null;
  return [Number(match[1]), Number(match[2]), Number(match[3] || 0)];
}

function parsePythonVersion(output) {
  return parseVersion(output);
}

function parseGoVersion(output) {
  return parseVersion(output);
}

function atLeast(version, major, minor) {
  return Array.isArray(version) && (version[0] > major || (version[0] === major && version[1] >= minor));
}

function needsPrerequisiteInstall({ pythonVersion, venvAvailable, gitAvailable, goVersion }) {
  const packages = [];
  if (!gitAvailable) packages.push('git');
  if (!atLeast(pythonVersion, 3, 8)) packages.push('python3');
  if (!venvAvailable || !atLeast(pythonVersion, 3, 8)) packages.push('python3-venv');
  if (!atLeast(goVersion, 1, 20)) packages.push('golang-go');
  return packages;
}

function isDebianFamily(osRelease) {
  const values = {};
  for (const line of String(osRelease).split(/\r?\n/)) {
    const match = line.match(/^([A-Z_]+)=(.*)$/);
    if (match) values[match[1]] = match[2].replace(/^['"]|['"]$/g, '').toLowerCase();
  }
  const ids = `${values.ID || ''} ${values.ID_LIKE || ''}`.split(/\s+/).filter(Boolean);
  return ids.some((id) => ['debian', 'ubuntu', 'pop', 'linuxmint', 'elementary'].includes(id));
}

function getInstallDirectory(home) {
  const path = require('node:path');
  return path.join(home, '.local', 'share', 'zeus-agent');
}

function isOfficialRemote(remote) {
  const normalized = String(remote || '').replace(/\.git$/, '').replace(/\/$/, '');
  return normalized === 'git@github.com:vps28app-web/zeus-agent'
    || normalized === 'ssh://git@github.com/vps28app-web/zeus-agent'
    || normalized === 'https://github.com/vps28app-web/zeus-agent';
}

function assertCleanCheckout(status) {
  if (String(status || '').trim()) {
    throw new Error('O instalador privilegiado exige um checkout Git limpo; preserve suas alterações ou use um clone novo.');
  }
}

function buildAptInstallCommand(packages) {
  if (!Array.isArray(packages) || packages.some((name) => !/^[a-z0-9][a-z0-9+.-]*$/.test(name))) {
    throw new Error('invalid package name');
  }
  return `apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y -- ${packages.join(' ')}`;
}

module.exports = {
  assertCleanCheckout,
  assertLinuxAmd64,
  assertNodeVersion,
  buildAptInstallCommand,
  getInstallDirectory,
  isDebianFamily,
  isOfficialRemote,
  needsPrerequisiteInstall,
  parseGoVersion,
  parsePythonVersion,
};

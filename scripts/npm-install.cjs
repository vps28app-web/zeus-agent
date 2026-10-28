#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const {
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
} = require('./npm-install-lib.cjs');

const REPOSITORY_URL = 'https://github.com/vps28app-web/zeus-agent.git';
const REQUIRED_PACKAGES = ['git', 'python3', 'python3-venv', 'golang-go'];

function execute(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    env: options.env || process.env,
    encoding: 'utf8',
    stdio: options.inherit ? 'inherit' : 'pipe',
  });
  if (result.error) {
    if (options.capture && result.error.code === 'ENOENT') {
      return { status: 127, stdout: '', stderr: result.error.message };
    }
    throw result.error;
  }
  if (options.capture) return { status: result.status, stdout: result.stdout || '', stderr: result.stderr || '' };
  if (result.status !== 0) {
    throw new Error(`${command} falhou com código ${result.status ?? 'desconhecido'}.`);
  }
  return { status: result.status, stdout: result.stdout || '', stderr: result.stderr || '' };
}

function outputOf(command, args = []) {
  const result = execute(command, args, { capture: true });
  return result.status === 0 ? result.stdout.trim() : null;
}

function hasCommand(command) {
  return outputOf('sh', ['-c', `command -v ${command}`]) !== null;
}

function inspectPrerequisites() {
  const pythonOutput = outputOf('python3', ['--version']);
  const pythonVersion = pythonOutput ? parsePythonVersion(pythonOutput) : null;
  const venvAvailable = pythonVersion
    ? execute('python3', ['-c', 'import venv, ensurepip'], { capture: true }).status === 0
    : false;
  const gitAvailable = Boolean(outputOf('/usr/bin/git', ['--version']) || outputOf('/bin/git', ['--version']));
  const systemGoOutput = outputOf('/usr/bin/go', ['version']);
  return {
    pythonVersion,
    venvAvailable,
    gitAvailable,
    goVersion: systemGoOutput ? parseGoVersion(systemGoOutput) : null,
  };
}

function readOsRelease() {
  try {
    return fs.readFileSync('/etc/os-release', 'utf8');
  } catch {
    return '';
  }
}

function elevated(command, args) {
  const graphical = Boolean(process.env.DISPLAY || process.env.WAYLAND_DISPLAY);
  if (graphical && hasCommand('pkexec')) {
    return execute('pkexec', ['--user', 'root', command, ...args], { inherit: true });
  }
  if (hasCommand('sudo')) {
    return execute('sudo', [command, ...args], { inherit: true });
  }
  throw new Error('Preciso de autorização administrativa via sudo ou pkexec para instalar dependências e o serviço da sandbox.');
}

async function confirm(message) {
  assertNodeVersion(process.versions.node);
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    throw new Error('Execute o instalador em um terminal interativo para confirmar a instalação privilegiada.');
  }
  const readline = require('node:readline/promises');
  const prompt = readline.createInterface({ input: process.stdin, output: process.stdout });
  try {
    const answer = await prompt.question(`${message} [s/N] `);
    return /^(s|sim|y|yes)$/i.test(answer.trim());
  } finally {
    prompt.close();
  }
}

function findRepositoryRoot(start) {
  let directory = path.resolve(start);
  while (true) {
    if (fs.existsSync(path.join(directory, '.git'))
      && fs.existsSync(path.join(directory, 'pyproject.toml'))
      && fs.existsSync(path.join(directory, 'scripts', 'install.sh'))
      && fs.existsSync(path.join(directory, 'scripts', 'install-systemd.sh'))) {
      const root = outputOf('git', ['-C', directory, 'rev-parse', '--show-toplevel']);
      if (root && path.resolve(root) === directory) return directory;
    }
    const parent = path.dirname(directory);
    if (parent === directory) return null;
    directory = parent;
  }
}

function verifyRepository(directory) {
  const remote = outputOf('git', ['-C', directory, 'remote', 'get-url', 'origin']);
  if (!isOfficialRemote(remote)) {
    throw new Error(`O checkout em ${directory} não aponta para o repositório oficial Zeus.`);
  }
  const status = outputOf('git', ['-C', directory, 'status', '--porcelain', '--untracked-files=all']);
  assertCleanCheckout(status || '');
}

function prepareSourceDirectory(existingSource = null) {
  if (existingSource) return existingSource;

  const currentRoot = findRepositoryRoot(process.cwd()) || findRepositoryRoot(__dirname);
  if (currentRoot) {
    verifyRepository(currentRoot);
    return currentRoot;
  }

  const directory = getInstallDirectory(os.homedir());
  if (fs.existsSync(directory)) {
    verifyRepository(directory);
    const branch = outputOf('git', ['-C', directory, 'branch', '--show-current']);
    if (branch !== 'main') throw new Error(`O checkout ${directory} não está na branch main.`);
    execute('git', ['-C', directory, 'fetch', REPOSITORY_URL, 'main'], { cwd: directory, inherit: true });
    execute('git', ['-C', directory, 'merge', '--ff-only', 'FETCH_HEAD'], { cwd: directory, inherit: true });
    verifyRepository(directory);
    console.log(`Usando checkout Zeus atualizado: ${directory}`);
    return directory;
  }
  fs.mkdirSync(path.dirname(directory), { recursive: true });
  execute('git', ['clone', '--depth', '1', REPOSITORY_URL, directory], { inherit: true });
  verifyRepository(directory);
  return directory;
}

function ensureSystemdAvailable() {
  if (!hasCommand('systemctl') || outputOf('systemctl', ['show', '--property=Version']) === null) {
    throw new Error('systemd não está ativo. A instalação completa da sandbox requer systemd; WSL precisa estar configurado com systemd habilitado.');
  }
}

async function runInstaller(argv = process.argv.slice(2)) {
  assertNodeVersion(process.versions.node);
  if (argv.includes('--help') || argv.includes('-h')) {
    console.log('Instalação completa do Zeus (Linux amd64, Debian/Ubuntu e derivados).');
    console.log('Uso: npm run install:zeus [-- --skip-setup]');
    console.log('Instala dependências, prepara o Zeus, instala/inicia a sandbox systemd e configura o provedor.');
    return 0;
  }
  const skipSetup = argv.includes('--skip-setup');
  const unknown = argv.filter((arg) => arg !== '--skip-setup');
  if (unknown.length) throw new Error(`Opção desconhecida: ${unknown[0]}`);

  assertLinuxAmd64(process.platform, process.arch);
  if (typeof process.getuid === 'function' && process.getuid() === 0) {
    throw new Error('Não execute npm/Zeus como root. Rode como usuário normal; o instalador pedirá autorização quando necessário.');
  }
  const osRelease = readOsRelease();
  if (!isDebianFamily(osRelease)) {
    throw new Error('A instalação automática de dependências via npm suporta Debian/Ubuntu e derivados. Em outras distribuições, instale Git, Python 3.8+, venv e Go 1.20+ primeiro.');
  }
  const currentSource = findRepositoryRoot(process.cwd()) || findRepositoryRoot(__dirname);
  if (currentSource) verifyRepository(currentSource);
  ensureSystemdAvailable();

  const initial = inspectPrerequisites();
  const missing = needsPrerequisiteInstall(initial);
  console.log('O instalador vai preparar Git, Python/venv e Go; clonar/instalar o Zeus; instalar e iniciar a sandbox como serviço systemd; e abrir a configuração do provedor.');
  console.log('A instalação do serviço e dos pacotes do sistema solicitará autorização administrativa local.');
  if (!await confirm('Continuar?')) {
    console.log('Instalação cancelada; nenhum pacote ou serviço foi alterado.');
    return 1;
  }

  if (missing.length) {
    const command = buildAptInstallCommand(REQUIRED_PACKAGES);
    console.log(`Instalando dependências do sistema: ${REQUIRED_PACKAGES.join(', ')}`);
    elevated('/bin/sh', ['-c', command]);
  }

  const ready = inspectPrerequisites();
  const stillMissing = needsPrerequisiteInstall(ready);
  if (stillMissing.length) {
    throw new Error(`Pré-requisitos ainda ausentes ou incompatíveis: ${stillMissing.join(', ')}. Verifique as versões exigidas (Python >=3.8, Go >=1.20).`);
  }

  const source = prepareSourceDirectory(currentSource);
  const sourceCommit = outputOf('git', ['-C', source, 'rev-parse', 'HEAD']);
  if (!sourceCommit) throw new Error('Não foi possível identificar a revisão do código Zeus.');
  console.log(`Instalando Zeus do checkout: ${source}`);
  console.log(`Revisão fonte: ${sourceCommit}`);
  execute('bash', [path.join(source, 'scripts', 'install.sh')], { cwd: source, inherit: true });
  const sandboxBinary = path.join(source, 'sandbox', 'sandbox');
  if (!fs.existsSync(sandboxBinary)) {
    throw new Error('A compilação da sandbox não produziu sandbox/sandbox. Confira a saída do Go e tente novamente.');
  }

  verifyRepository(source);
  const systemdInstaller = path.join(source, 'scripts', 'install-systemd.sh');
  console.log('Instalando e iniciando o serviço privilegiado da sandbox…');
  elevated(systemdInstaller, []);
  if (execute('systemctl', ['is-active', '--quiet', 'zeus-sandbox.service'], { capture: true }).status !== 0) {
    throw new Error('O serviço zeus-sandbox.service não ficou ativo. Verifique: journalctl -u zeus-sandbox.service');
  }
  console.log('Sandbox instalada, habilitada e ativa.');

  if (!skipSetup) {
    const zeus = path.join(source, '.venv', 'bin', 'zeus');
    execute(zeus, ['setup'], { cwd: source, inherit: true });
  }
  console.log('Instalação do Zeus concluída.');
  return 0;
}

if (require.main === module) {
  runInstaller().then((code) => {
    process.exitCode = code;
  }).catch((error) => {
    console.error(`Erro: ${error.message}`);
    process.exitCode = 1;
  });
}

module.exports = { runInstaller };

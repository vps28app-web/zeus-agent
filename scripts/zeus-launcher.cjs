#!/usr/bin/env node
'use strict';

// npm launcher for Zeus: finds the Zeus installation and runs its venv
// entry point while preserving the caller's working directory, so `zeus`
// works from any directory.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const {
  entryNameForLauncher,
  entryPath,
  resolveInstallDirectory,
} = require('./zeus-launcher-lib.cjs');

const SIGNAL_EXIT_CODES = { SIGHUP: 129, SIGINT: 130, SIGQUIT: 131, SIGTERM: 143 };

function main() {
  const stateHome = process.env.ZEUS_HOME || path.join(os.homedir(), '.zeus');
  const resolution = resolveInstallDirectory({
    envInstallDir: process.env.ZEUS_INSTALL_DIR,
    cwd: process.cwd(),
    home: os.homedir(),
    stateHome,
    platform: process.platform,
    existsSync: fs.existsSync,
    readFileSync: fs.readFileSync,
  });
  if (resolution.error) {
    console.error(`Erro: ${resolution.error}`);
    process.exitCode = 1;
    return;
  }

  let entry = resolution.entry;
  if (entryNameForLauncher(path.basename(process.argv[1] || 'zeus')) === 'zeus-gateway') {
    entry = entryPath(resolution.installDir, process.platform, 'zeus-gateway');
    if (!fs.existsSync(entry)) {
      console.error(`Erro: zeus-gateway não está instalado em ${resolution.installDir} (${entry} ausente).`);
      process.exitCode = 1;
      return;
    }
  }

  // spawn inherits the current working directory: Zeus runs where the user is.
  // Export the install dir so Zeus can still load the checkout's .env as a
  // fallback (the legacy launcher got this for free by cd'ing into it).
  const child = spawn(entry, process.argv.slice(2), {
    stdio: 'inherit',
    env: { ...process.env, ZEUS_INSTALL_DIR: resolution.installDir },
  });

  for (const signal of Object.keys(SIGNAL_EXIT_CODES)) {
    process.on(signal, () => {
      child.kill(signal);
    });
  }
  child.on('error', (error) => {
    console.error(`Erro: não foi possível executar ${entry}: ${error.message}`);
    process.exitCode = 1;
  });
  child.on('exit', (code, signal) => {
    if (signal && SIGNAL_EXIT_CODES[signal] !== undefined) {
      process.exit(SIGNAL_EXIT_CODES[signal]);
    }
    process.exitCode = code === null || code === undefined ? 1 : code;
  });
}

if (require.main === module) main();

module.exports = { main };

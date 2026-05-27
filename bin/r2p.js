#!/usr/bin/env node
"use strict";

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..");
const args = ["-m", "tools.workflow_cli.install_cli", ...process.argv.slice(2)];
const env = {
  ...process.env,
  PYTHONPATH: process.env.PYTHONPATH
    ? `${repoRoot}${path.delimiter}${process.env.PYTHONPATH}`
    : repoRoot,
};

function runPython(command) {
  return spawnSync(command, args, {
    cwd: repoRoot,
    env,
    stdio: "inherit",
  });
}

let result = runPython("python3");
if (result.error && result.error.code === "ENOENT") {
  result = runPython("python");
}

if (result.error) {
  console.error(`r2p: failed to start Python: ${result.error.message}`);
  process.exit(1);
}

if (result.signal) {
  process.kill(process.pid, result.signal);
}

process.exit(result.status ?? 1);

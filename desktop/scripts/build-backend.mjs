// Cross-platform backend freeze + stage (replaces the Unix-only .venv shell scripts).
// 1. Runs PyInstaller on packaging/dielectric-server.spec → <root>/resources/dielectric-server
// 2. Stages it into desktop/resources/dielectric-server for electron-builder extraResources.
//
// Python resolution order: $PYTHON env (CI sets it) → project .venv (local dev) → PATH.

import { execFileSync } from "node:child_process";
import { existsSync, rmSync, cpSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";

const here = path.dirname(fileURLToPath(import.meta.url));
const desktop = path.resolve(here, "..");
const root = path.resolve(desktop, "..");
const isWin = process.platform === "win32";

function resolvePython() {
  if (process.env.PYTHON) return process.env.PYTHON;
  const venv = isWin
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : path.join(root, ".venv", "bin", "python");
  if (existsSync(venv)) return venv;
  return isWin ? "python" : "python3";
}

const py = resolvePython();
console.log(`[build-backend] python = ${py}`);

execFileSync(
  py,
  ["-m", "PyInstaller", "packaging/dielectric-server.spec", "--noconfirm", "--distpath", "resources"],
  { cwd: root, stdio: "inherit" },
);

const src = path.join(root, "resources", "dielectric-server");
const dst = path.join(desktop, "resources", "dielectric-server");
rmSync(path.join(desktop, "resources"), { recursive: true, force: true });
cpSync(src, dst, { recursive: true });
console.log(`[build-backend] staged → ${dst}`);

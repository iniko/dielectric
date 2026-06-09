import { spawn, ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import { randomBytes } from "node:crypto";
import path from "node:path";
import process from "node:process";
import { app } from "electron";

export interface Backend {
  url: string;
  token: string;
  stop: () => Promise<void>;
}

/** Ask the OS for a free loopback port by binding to :0 and reading it back. */
function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const port = (srv.address() as { port: number }).port;
      srv.close(() => resolve(port));
    });
  });
}

/** Resolve the command that starts FastAPI: bundled binary in prod, project .venv in dev. */
function serverCommand(port: number): { cmd: string; args: string[]; cwd: string } {
  const host = "127.0.0.1";
  if (app.isPackaged) {
    // PyInstaller onedir binary, bundled via electron-builder extraResources → resources/server.
    const exe = process.platform === "win32" ? "dielectric-server.exe" : "dielectric-server";
    const bin = path.join(process.resourcesPath, "server", exe);
    return { cmd: bin, args: ["--host", host, "--port", String(port)], cwd: path.dirname(bin) };
  }
  // Dev: project root is two levels up from desktop/electron/dist/.
  const root = path.resolve(__dirname, "..", "..", "..");
  const py =
    process.platform === "win32"
      ? path.join(root, ".venv", "Scripts", "python.exe")
      : path.join(root, ".venv", "bin", "python");
  return {
    cmd: py,
    args: ["-m", "backend.run_server", "--host", host, "--port", String(port)],
    cwd: root,
  };
}

async function waitForHealth(url: string, token: string, timeoutMs = 30_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${url}/api/health`, {
        headers: { "x-dielectric-token": token },
      });
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`Backend did not become healthy within ${timeoutMs}ms`);
}

export async function startBackend(): Promise<Backend> {
  const port = await findFreePort();
  const token = randomBytes(24).toString("hex");
  const url = `http://127.0.0.1:${port}`;
  const { cmd, args, cwd } = serverCommand(port);

  const child: ChildProcess = spawn(cmd, args, {
    cwd,
    env: {
      ...process.env,
      DIELECTRIC_AUTH_TOKEN: token,
      // Leave DIELECTRIC_ALLOW_ORIGINS unset: the backend default already allows the dev
      // renderer (localhost:5173), and its allow_origin_regex covers the packaged file://
      // renderer (Origin "null") and the app:// scheme — so both dev and prod pass CORS.
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  child.stdout?.on("data", (d) => console.log(`[backend] ${String(d).trimEnd()}`));
  child.stderr?.on("data", (d) => console.error(`[backend] ${String(d).trimEnd()}`));
  child.on("exit", (code) => console.log(`[backend] exited with code ${code}`));

  await waitForHealth(url, token);

  const stop = (): Promise<void> =>
    new Promise<void>((resolve) => {
      if (!child.pid || child.killed) return resolve();
      if (process.platform === "win32") {
        // Kill the whole tree — uvicorn may have spawned children.
        spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"]);
      } else {
        child.kill("SIGTERM");
        setTimeout(() => {
          if (!child.killed) child.kill("SIGKILL");
        }, 3000);
      }
      child.on("exit", () => resolve());
      setTimeout(resolve, 4000); // hard cap so quitting never hangs
    });

  return { url, token, stop };
}

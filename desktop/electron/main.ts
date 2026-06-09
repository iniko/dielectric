import path from "node:path";
import process from "node:process";
import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import { startBackend, Backend } from "./backend";

let backend: Backend | null = null;
let win: BrowserWindow | null = null;
let stopping = false;

const isDev = !app.isPackaged;

async function createWindow(): Promise<void> {
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true, // renderer cannot touch Node
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // Register listeners BEFORE loading — `ready-to-show` can fire during load, so attaching
  // it after `await load*` would miss it and the window (show:false) would never appear.
  win.once("ready-to-show", () => win?.show());

  // External links open in the system browser, never in-app.
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  win.on("closed", () => {
    win = null;
  });

  // Hand the renderer the live backend coordinates via the URL query string the preload
  // reads — race-free, available before first paint (vs. async IPC after load).
  const params = `apiBase=${encodeURIComponent(backend!.url)}&token=${backend!.token}`;

  if (isDev) {
    await win.loadURL(`http://localhost:5173/?${params}`);
    // DevTools on demand only: toggle with ⌥⌘I (macOS) / Ctrl+Shift+I (Win/Linux), or set
    // DEVTOOLS=1 to auto-open. Never opens in the packaged app (gated behind isDev).
    if (process.env.DEVTOOLS) win.webContents.openDevTools({ mode: "detach" });
  } else {
    await win.loadFile(path.join(__dirname, "..", "..", "renderer", "index.html"), {
      search: params,
    });
  }

  // Belt-and-suspenders: load has resolved, so showing now is always safe even if
  // ready-to-show already fired before the listener was attached.
  win.show();
  win.focus();
}

app.whenReady().then(async () => {
  try {
    backend = await startBackend();
  } catch (err) {
    dialog.showErrorBox("Backend failed to start", String(err));
    app.quit();
    return;
  }
  await createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) void createWindow();
  });
});

// Clean shutdown: stop the Python process before the app fully exits.
app.on("before-quit", (e) => {
  if (stopping || !backend) return;
  e.preventDefault();
  stopping = true;
  backend.stop().finally(() => {
    backend = null;
    app.quit();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

// Example IPC: native "save file" dialog for report exports.
ipcMain.handle("dialog:saveReport", async (_e, defaultName: string) => {
  const { canceled, filePath } = await dialog.showSaveDialog({ defaultPath: defaultName });
  return canceled ? null : filePath;
});

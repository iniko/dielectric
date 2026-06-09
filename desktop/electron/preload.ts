import { contextBridge, ipcRenderer } from "electron";

// The ONLY bridge between renderer and Node. Everything here is explicitly allow-listed;
// the renderer gets no require(), no fs, no raw ipcRenderer.

const params = new URLSearchParams(globalThis.location?.search ?? "");

contextBridge.exposeInMainWorld("desktop", {
  apiBase: params.get("apiBase") ?? "",
  token: params.get("token") ?? "",
});

contextBridge.exposeInMainWorld("native", {
  /** Open the OS save dialog; returns the chosen absolute path or null if cancelled. */
  saveReport: (defaultName: string): Promise<string | null> =>
    ipcRenderer.invoke("dialog:saveReport", defaultName),
});

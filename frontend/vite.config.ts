import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The backend runs on port 8001 (port 8000 is taken on this machine); /api is proxied to it in dev.
// `process` exists at config-eval time (Node) but @types/node isn't a frontend dep, so read the
// flag off globalThis to stay dependency-free.
const isElectron = Boolean(
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.ELECTRON,
);

export default defineConfig({
  // Relative asset paths so the built index.html loads under Electron's file:// scheme.
  // Harmless for web hosting from the site root; flip via env if your host needs "/".
  base: isElectron ? "./" : "/",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
    },
  },
});

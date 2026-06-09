var _a, _b;
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
// The backend runs on port 8001 (port 8000 is taken on this machine); /api is proxied to it in dev.
// `process` exists at config-eval time (Node) but @types/node isn't a frontend dep, so read the
// flag off globalThis to stay dependency-free.
var isElectron = Boolean((_b = (_a = globalThis.process) === null || _a === void 0 ? void 0 : _a.env) === null || _b === void 0 ? void 0 : _b.ELECTRON);
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

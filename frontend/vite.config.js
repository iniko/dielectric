import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
// The backend runs on port 8001 (port 8000 is taken on this machine); /api is proxied to it in dev.
export default defineConfig({
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

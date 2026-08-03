import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Build output lands inside the Python package so PyInstaller ships it and
// FastAPI can serve it from a single directory. In development the dev server
// proxies /api to the uvicorn process instead.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../src/jawut/static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/ready": "http://127.0.0.1:8000",
    },
  },
});

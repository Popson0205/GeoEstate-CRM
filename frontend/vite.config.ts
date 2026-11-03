/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on :8001 (uvicorn) and is reached through /api, as in production.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: "http://localhost:8001", rewrite: (p) => p.replace(/^\/api/, "") } } },
  test: { environment: "jsdom", globals: false },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/auth": "http://localhost:8080",
      "/agent": "http://localhost:8080",
      "/connect": "http://localhost:8080",
      "/call_url": "http://localhost:8080",
    },
  },
  build: {
    outDir: "../backend/static",
    emptyOutDir: true,
  },
});

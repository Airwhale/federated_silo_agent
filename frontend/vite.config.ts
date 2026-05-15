import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    host: "127.0.0.1",
    // 5200, not Vite's default 5173, so this branch can run alongside
    // a parallel build that holds 5173. Backend CORS allows both.
    port: 5200,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});

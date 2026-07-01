import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  build: {
    rollupOptions: {
      output: {
        // Vite 8 uses Rolldown, whose `manualChunks` is a function (not the
        // Rollup object-map form). Group vendors so no single chunk exceeds
        // Vite's 500 kB warning threshold.
        manualChunks(id: string): string | undefined {
          if (!id.includes("node_modules")) return undefined;
          if (/\/(react|react-dom|react-router|react-router-dom)\//.test(id)) {
            return "react-vendor";
          }
          if (id.includes("@tanstack")) return "query-vendor";
          if (/\/(react-hook-form|zod|@hookform)\//.test(id)) return "form-vendor";
          if (id.includes("@radix-ui")) return "radix-vendor";
          return undefined;
        },
      },
    },
  },
  server: {
    proxy: {
      "/auth": "http://localhost:8000",
      "/tools": "http://localhost:8000",
      "/runs": "http://localhost:8000",
      "/admin": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  test: {
    globals: true,
    environment: "./vitest.environment.ts",
    setupFiles: ["./src/vitest.setup.ts"],
    css: true,
    exclude: ["e2e/**", "node_modules/**"],
  },
});

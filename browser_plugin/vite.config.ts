import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Vite config for Manifest V3 Chrome Extension.
// Side panel:  React app compiled to dist/side_panel/
// Background:  single-file ES module compiled to dist/background.js
// Content:     single-file IIFE compiled to dist/content.js
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        side_panel: resolve(__dirname, "side_panel.html"),
        background: resolve(__dirname, "src/background/index.ts"),
        content: resolve(__dirname, "src/content/extract.ts"),
      },
      output: {
        // Background service worker must be a single module file.
        entryFileNames: (chunk) => {
          if (chunk.name === "background") return "background.js";
          if (chunk.name === "content") return "content.js";
          return "side_panel/[name]-[hash].js";
        },
        chunkFileNames: "side_panel/chunks/[name]-[hash].js",
        assetFileNames: (asset) => {
          if (asset.name?.endsWith(".css")) return "side_panel/[name][extname]";
          return "assets/[name][extname]";
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});

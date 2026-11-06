import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// JS・CSS・データ（src/data の JSON）・画像を 1 つの dist/index.html にまとめる。
// S3 の署名付き URL 1 本で配れるようにするため（docs/WEB_PLAN.md 2.3 の A 案）。
export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile()],
  base: "./",
  build: {
    assetsInlineLimit: 100_000_000,
    chunkSizeWarningLimit: 10_000,
  },
});

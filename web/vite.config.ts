import { existsSync, readdirSync } from "node:fs";
import path from "node:path";
import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";
import { s3DataPlugin } from "./server/s3-data.ts";

const CACHE_DIR = path.resolve(import.meta.dirname, "cache");

// build の前に cache/ にデータがあるかを確かめる（無いと、データなしの 1 ファイルができてしまう）
function requireCache(): Plugin {
  return {
    name: "ct125-require-cache",
    apply: "build",
    buildStart() {
      const files = existsSync(CACHE_DIR) ? readdirSync(CACHE_DIR) : [];
      if (!files.includes("rides.json")) {
        throw new Error("cache/rides.json がありません。先に scripts/pull-data.ps1 で S3 からデータを取ってきてください");
      }
    },
  };
}

export default defineConfig(({ command, mode }) => {
  // .env.local を読む。第 3 引数 "" で VITE_ の付かない変数も読む（この値はブラウザには渡さない）
  const env = loadEnv(mode, process.cwd(), "");
  const build = command === "build";
  return {
    plugins: [react(), tailwindcss(), s3DataPlugin(env, CACHE_DIR), requireCache(), viteSingleFile()],
    base: "./",
    define: {
      // build のときだけ cache/ のデータを HTML に埋め込む（src/lib/data.ts）
      __EMBED_DATA__: JSON.stringify(build),
    },
    // localhost だけで待ち受ける（host を変えると同じ Wi-Fi の端末から S3 の中身が見えてしまう）
    // cache/ は dev サーバーが S3 から取るたびに書き込むので監視しない（監視すると画面の再読み込みが連鎖する）
    server: { port: 5173, strictPort: true, watch: { ignored: ["**/cache/**", "**/dist/**"] } },
    preview: { port: 4173, strictPort: true },
    build: {
      assetsInlineLimit: 100_000_000,
      chunkSizeWarningLimit: 10_000,
    },
  };
});

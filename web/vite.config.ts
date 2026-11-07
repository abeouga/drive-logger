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

// データの取り方（src/lib/dataSource.ts）。どれになるかは起動のしかたで決まる
//   dev      : npm run dev           … Vite の dev サーバーが S3（または cache/）から返す。ログインなし
//   hosted   : npm run build         … CloudFront で配る。ログインして /api/data/ から取る
//   embedded : npm run build:single  … cache/ のデータを 1 つの HTML に埋め込む（オフラインで見せる用）
type DataMode = "dev" | "hosted" | "embedded";

function dataModeOf(command: "serve" | "build", mode: string): DataMode {
  if (command === "serve") return "dev";
  if (mode === "single") return "embedded";
  return "hosted";
}

export default defineConfig(({ command, mode }) => {
  // .env.local を読む。第 3 引数 "" で VITE_ の付かない変数も読む（この値はブラウザには渡さない）
  const env = loadEnv(mode, process.cwd(), "");
  const dataMode = dataModeOf(command, mode);
  const embedded = dataMode === "embedded";
  return {
    plugins: [react(), tailwindcss(), s3DataPlugin(env, CACHE_DIR), ...(embedded ? [requireCache(), viteSingleFile()] : [])],
    base: embedded ? "./" : "/",
    define: {
      __DATA_MODE__: JSON.stringify(dataMode),
      // embedded のときだけ cache/ のデータを HTML に埋め込む（src/lib/data.ts）
      __EMBED_DATA__: JSON.stringify(embedded),
    },
    // localhost だけで待ち受ける（host を変えると同じ Wi-Fi の端末から S3 の中身が見えてしまう）
    // cache/ は dev サーバーが S3 から取るたびに書き込むので監視しない（監視すると画面の再読み込みが連鎖する）
    server: { port: 5173, strictPort: true, watch: { ignored: ["**/cache/**", "**/dist/**"] } },
    preview: { port: 4173, strictPort: true },
    build: embedded ? { assetsInlineLimit: 100_000_000, chunkSizeWarningLimit: 10_000 } : { chunkSizeWarningLimit: 3_000 } // 地図（maplibre）とグラフ（echarts）で約 2.5 MB（gzip 後 0.7 MB）,
  };
});

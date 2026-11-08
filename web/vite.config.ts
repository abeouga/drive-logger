import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { s3DataPlugin } from "./server/s3-data.ts";

const CACHE_DIR = path.resolve(import.meta.dirname, "cache");

// データの取り方（src/lib/dataSource.ts）。どれになるかは起動のしかたで決まる
//   dev    : npm run dev   … Vite の dev サーバーが S3（または cache/）から返す。ログインなし
//   hosted : npm run build … CloudFront で配る。ログインして /api/data/ から取る
type DataMode = "dev" | "hosted";

export default defineConfig(({ command, mode }) => {
  // .env.local を読む。第 3 引数 "" で VITE_ の付かない変数も読む（この値はブラウザには渡さない）
  const env = loadEnv(mode, process.cwd(), "");
  const dataMode: DataMode = command === "serve" ? "dev" : "hosted";
  return {
    plugins: [react(), tailwindcss(), s3DataPlugin(env, CACHE_DIR)],
    define: {
      __DATA_MODE__: JSON.stringify(dataMode),
    },
    // localhost だけで待ち受ける（host を変えると同じ Wi-Fi の端末から S3 の中身が見えてしまう）
    // cache/ は dev サーバーが S3 から取るたびに書き込むので監視しない（監視すると画面の再読み込みが連鎖する）
    server: { port: 5173, strictPort: true, watch: { ignored: ["**/cache/**", "**/dist/**"] } },
    preview: { port: 4173, strictPort: true },
    build: { chunkSizeWarningLimit: 3_000 }, // 地図（maplibre）とグラフ（echarts）で約 2.5 MB（gzip 後 0.7 MB）
  };
});

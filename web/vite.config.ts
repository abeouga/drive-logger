import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// 画面のデータは、いつもデータ API（/api/*）から読む（src/lib/dataSource.ts）。
//   npm run build    ：CloudFront で配る。/api/* は同じドメインのデータ API
//   npm run dev      ：Vite の dev サーバーが /api/* を公開版のドメイン（.env.development.local の API_ORIGIN）へ中継する。ログインは公開版と同じ Cognito
//   npm run dev:local：/api/* を手元で動かしたデータ API（uvicorn、http://localhost:8000）へ中継する。ログインしない
//                      （データ API を ALLOW_LOCAL_USER=true で動かす。手元の開発者は admin として扱われる。web/docs/local_dev.md）
//   npm run dev:test ：/api/* を test のドメイン（.env.testenv.local の API_ORIGIN）へ中継する。ログインは test の Cognito（同じファイル）
// 環境に依る値（ドメイン・ログインの設定）はコミットしない .local のファイルにだけ置く。scripts/start-dev.ps1 が Terraform の出力から作る（見本は .env.example）
export default defineConfig(({ mode, command, isPreview }) => {
  // .env.development.local などを読む。第 3 引数 "" で VITE_ の付かない変数も読む（この値はブラウザには渡さない）
  const env = loadEnv(mode, process.cwd(), "");
  const localApi = mode === "localapi";
  const apiOrigin = localApi ? env.LOCAL_API_ORIGIN || "http://localhost:8000" : env.API_ORIGIN;
  // 中継先が無いまま dev サーバーを起動しない（ビルド・preview・vitest（mode test）は中継を使わないので止めない）
  if (command === "serve" && !isPreview && mode !== "test" && !apiOrigin) {
    throw new Error(
      `API_ORIGIN がありません（mode ${mode}）。scripts/start-dev.ps1 で Terraform の出力から .env.${mode}.local を作るか、.env.example を見本に手で書いてください`,
    );
  }
  return {
    plugins: [react(), tailwindcss()],
    define: {
      __LOCAL_API__: JSON.stringify(localApi),
    },
    // localhost だけで待ち受ける（Cognito のログインの戻り先が http://localhost:5173/ だけを許しているため、ポートも固定）
    server: {
      port: 5173,
      strictPort: true,
      proxy: { "/api": { target: apiOrigin, changeOrigin: true, secure: !localApi } },
      watch: { ignored: ["**/dist/**"] },
    },
    preview: { port: 4173, strictPort: true },
    build: { chunkSizeWarningLimit: 3_000 }, // 地図（maplibre）とグラフ（echarts）で約 2.5 MB（gzip 後 0.7 MB）
  };
});

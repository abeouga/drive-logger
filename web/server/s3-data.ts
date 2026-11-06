// Vite の dev サーバーの中だけで動く（ブラウザには出ない）。
// /data/<ファイル名> を受けて、
//   DATA_SOURCE=s3    → s3://$S3_BUCKET/$S3_PREFIX<ファイル名> を ~/.aws のプロファイルで GetObject し、cache/ にも保存して返す
//                       S3 から取れないとき（認証切れ・回線なし）は cache/ にあればそれを返す（ヘッダーで知らせる）
//   DATA_SOURCE=cache → cache/ だけを返す
// AWS の認証情報・バケット名はブラウザに渡らない。バケットは非公開のまま、CORS も要らない。
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";
import { GetObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { fromIni } from "@aws-sdk/credential-providers";

export interface DataEnv {
  DATA_SOURCE?: string;
  AWS_PROFILE?: string;
  AWS_REGION?: string;
  S3_BUCKET?: string;
  S3_PREFIX?: string;
}

// 英数字と _ . - だけ。先頭のドットは不可（.. や隠しファイルを防ぐ）。サブフォルダーも不可
export const SAFE_NAME = /^[A-Za-z0-9_][A-Za-z0-9_.-]*$/;

const TYPES: Record<string, string> = {
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
};

export function contentType(name: string): string | null {
  return TYPES[path.extname(name).toLowerCase()] ?? null;
}

function send(res: ServerResponse, status: number, body: string | Uint8Array, type = "text/plain; charset=utf-8", extra: Record<string, string> = {}) {
  res.statusCode = status;
  res.setHeader("Content-Type", type);
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Content-Type-Options", "nosniff");
  for (const [k, v] of Object.entries(extra)) res.setHeader(k, v);
  res.end(body);
}

export function s3DataPlugin(env: DataEnv, cacheDir: string): Plugin {
  const source = (env.DATA_SOURCE ?? "s3").toLowerCase();
  const prefix = env.S3_PREFIX ?? "app/v1/";
  let client: S3Client | null = null;

  const getS3 = () => {
    client ??= new S3Client({
      region: env.AWS_REGION ?? "ap-northeast-1",
      credentials: fromIni({ profile: env.AWS_PROFILE ?? "ct125-logger" }),
      maxAttempts: 2,
    });
    return client;
  };

  async function fromS3(name: string): Promise<Uint8Array> {
    const out = await getS3().send(new GetObjectCommand({ Bucket: env.S3_BUCKET, Key: `${prefix}${name}` }));
    if (!out.Body) throw new Error("S3 の応答に中身がありません");
    // ストリームは必ず読み切る（読まないと接続が残る）
    const bytes = await out.Body.transformToByteArray();
    await mkdir(cacheDir, { recursive: true });
    await writeFile(path.join(cacheDir, name), bytes);
    return bytes;
  }

  async function handle(req: IncomingMessage, res: ServerResponse) {
    if (req.method !== "GET" && req.method !== "HEAD") return send(res, 405, "GET だけ受け付けます");
    // connect の use("/data") で前置きは外れている。クエリは無視
    const name = decodeURIComponent((req.url ?? "/").split("?")[0].replace(/^\/+/, ""));
    const type = contentType(name);
    if (!SAFE_NAME.test(name) || !type) return send(res, 400, `ファイル名が不正です：${name.slice(0, 80)}`);
    const cached = path.join(cacheDir, name);

    if (source === "cache") {
      try {
        return send(res, 200, await readFile(cached), type, { "X-Data-Source": "cache" });
      } catch {
        return send(res, 404, `cache/${name} がありません（scripts/pull-data.ps1 で S3 から取ってきてください）`);
      }
    }

    try {
      return send(res, 200, await fromS3(name), type, { "X-Data-Source": "s3" });
    } catch (e) {
      const err = e as { name?: string; message?: string; $metadata?: { httpStatusCode?: number } };
      const notFound = err.name === "NoSuchKey" || err.$metadata?.httpStatusCode === 404;
      try {
        const body = await readFile(cached);
        console.warn(`[s3-data] S3 から ${name} を取れなかったので cache/ を返します：${err.name ?? ""} ${err.message ?? ""}`);
        return send(res, 200, body, type, { "X-Data-Source": "cache-fallback" });
      } catch {
        if (notFound) return send(res, 404, `s3://${env.S3_BUCKET}/${prefix}${name} がありません（ct125-logger で export --upload）`);
        console.error(`[s3-data] ${name}: ${err.name ?? ""} ${err.message ?? ""}`);
        return send(res, 502, `S3 から取得できませんでした（${err.name ?? "エラー"}）。AWS の認証（プロファイル ${env.AWS_PROFILE ?? "ct125-logger"}）を確認してください`);
      }
    }
  }

  return {
    name: "ct125-s3-data",
    apply: "serve",
    configResolved() {
      if (source !== "s3" && source !== "cache") throw new Error(`DATA_SOURCE は s3 か cache です（今は ${source}）`);
      if (source === "s3" && (!env.S3_BUCKET || env.S3_BUCKET.includes("<"))) {
        throw new Error(".env.local の S3_BUCKET が未設定です（.env.example を参照）。S3 を使わないなら DATA_SOURCE=cache");
      }
    },
    configureServer(server) {
      const where = source === "s3" ? `s3://${env.S3_BUCKET}/${prefix}（プロファイル ${env.AWS_PROFILE ?? "ct125-logger"}）` : "cache/";
      server.config.logger.info(`  データの出どころ: ${where}`);
      server.middlewares.use("/data", (req, res) => {
        handle(req, res).catch((e) => send(res, 500, String(e)));
      });
    },
  };
}

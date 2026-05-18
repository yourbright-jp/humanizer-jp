/**
 * jp-ai-tells-corpus crawler Worker.
 *
 * エンドポイント:
 *   POST /crawl/wikipedia          R2 上の 2021-12 dump から N 記事抽出 → D1
 *   POST /crawl/hatena             docs/seed_hatena_blogs.txt を読んで巡回 → D1
 *   POST /crawl/note               同上
 *   POST /crawl/qiita              Qiita API 直叩き → D1
 *   GET  /progress                 v_progress view を返す
 *
 * 全エンドポイントは ?limit=N でその回の取得上限を指定可能。
 *
 * Browser Run / D1 / R2 のバインディングは wrangler.toml 参照。
 */
import { crawlHatena } from "./sources/hatena";
import { crawlNote } from "./sources/note";
import { crawlQiita } from "./sources/qiita";
import { crawlWikipedia } from "./sources/wikipedia";
import { embedBatch } from "./embed";

export interface Env {
  DB: D1Database;
  BROWSER: Fetcher;       // Browser Run binding
  AI: Ai;                 // Workers AI binding (Phase 4)
  DUMPS: R2Bucket;        // Wikipedia dump 置き場
  USER_AGENT: string;
  DATE_MIN: string;
  DATE_MAX: string;
}

interface CrawlResult {
  source: string;
  inserted: number;
  skipped: number;
  failed: number;
  duration_ms: number;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const limit = Number(url.searchParams.get("limit") ?? "100");

    if (req.method === "GET" && url.pathname === "/progress") {
      const row = await env.DB.prepare("SELECT * FROM v_progress").first();
      const emb = await env.DB.prepare(
        "SELECT source_table, COUNT(*) AS n FROM sentence_embeddings GROUP BY source_table",
      ).all();
      return Response.json({ ...row, embeddings: emb.results });
    }

    if (req.method !== "POST") {
      return new Response("method not allowed", { status: 405 });
    }

    const t0 = Date.now();
    let result: CrawlResult;
    switch (url.pathname) {
      case "/crawl/wikipedia":
        result = await crawlWikipedia(env, limit);
        break;
      case "/crawl/hatena":
        result = await crawlHatena(env, limit);
        break;
      case "/crawl/note":
        result = await crawlNote(env, limit);
        break;
      case "/crawl/qiita":
        result = await crawlQiita(env, limit);
        break;
      case "/embed/clean":
        result = await embedBatch(env, "clean_articles", limit);
        break;
      case "/embed/ai":
        result = await embedBatch(env, "ai_articles", limit);
        break;
      default:
        return new Response("not found", { status: 404 });
    }
    result.duration_ms = Date.now() - t0;
    return Response.json(result);
  },
} satisfies ExportedHandler<Env>;

/** 共通: clean_articles への idempotent INSERT */
export async function upsertCleanArticle(
  env: Env,
  article: {
    id: string;
    source: string;
    url: string;
    title: string;
    text: string;
    published_at: string;
  },
): Promise<"inserted" | "skipped"> {
  if (article.text.length < 1500) return "skipped";
  const r = await env.DB.prepare(
    `INSERT OR IGNORE INTO clean_articles (id, source, url, title, text, published_at, char_count)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      article.id,
      article.source,
      article.url,
      article.title,
      article.text,
      article.published_at,
      article.text.length,
    )
    .run();
  return r.meta.changes && r.meta.changes > 0 ? "inserted" : "skipped";
}

/** id: md5(url)[:16] — Web Crypto で計算 */
export async function urlId(url: string): Promise<string> {
  const buf = new TextEncoder().encode(url);
  const hash = await crypto.subtle.digest("MD5", buf).catch(async () => {
    // Web Crypto MD5 が無い環境向け fallback (SHA-1 で代替)
    return crypto.subtle.digest("SHA-1", buf);
  });
  return [...new Uint8Array(hash)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16);
}

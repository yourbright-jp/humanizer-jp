/**
 * 最小構成の Phase 4 埋め込み専用 Worker。
 * crawler 本体 (index.ts) は Browser Run / R2 バインディングを要求するため、
 * 埋め込みだけを回したい場合はこの entry を wrangler.embed.toml で起動する。
 *
 *   POST /embed/clean?limit=N
 *   POST /embed/ai?limit=N
 *   GET  /progress
 */
import { embedBatch } from "./embed";

export interface Env {
  DB: D1Database;
  AI: Ai;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const limit = Number(url.searchParams.get("limit") ?? "50");

    if (req.method === "GET" && url.pathname === "/progress") {
      const emb = await env.DB.prepare(
        "SELECT source_table, COUNT(*) AS n FROM sentence_embeddings GROUP BY source_table",
      ).all();
      const todo = await env.DB.prepare(
        "SELECT (SELECT COUNT(*) FROM v_clean_to_embed) AS clean_todo," +
          " (SELECT COUNT(*) FROM v_ai_to_embed) AS ai_todo",
      ).first();
      return Response.json({ embeddings: emb.results, ...todo });
    }

    if (req.method !== "POST") {
      return new Response("method not allowed", { status: 405 });
    }

    const t0 = Date.now();
    let result;
    switch (url.pathname) {
      case "/embed/clean":
        result = await embedBatch(env as any, "clean_articles", limit);
        break;
      case "/embed/ai":
        result = await embedBatch(env as any, "ai_articles", limit);
        break;
      default:
        return new Response("not found", { status: 404 });
    }
    result.duration_ms = Date.now() - t0;
    return Response.json(result);
  },
} satisfies ExportedHandler<Env>;

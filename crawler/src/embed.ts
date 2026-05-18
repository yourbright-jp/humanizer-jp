/**
 * Phase 4: 文単位埋め込みを Workers AI (BGE-M3) で生成し D1 に保存。
 *
 * エンドポイント:
 *   POST /embed/clean?limit=N    clean_articles から N 記事分を embed
 *   POST /embed/ai?limit=N       ai_articles から N 記事分を embed
 *
 * モデル:
 *   @cf/baai/bge-m3 (1024 dim, 多言語、日本語性能良好)
 *
 * 1 記事の処理:
 *   1. text を文に split (。/!/?/！/？)
 *   2. 各文 (20 字以上) を 1 batch で Workers AI に投げる
 *      → Workers AI の text input は配列で渡せるので 1 call で複数文 OK
 *   3. 各文の embedding を Float32Array(1024).buffer として D1 に INSERT
 *
 * べき等:
 *   UNIQUE(source_table, source_id, sentence_idx, model_id) で防衛。
 *   INSERT OR IGNORE で重複を弾く。
 */
import { Env } from "./index";

const MODEL_ID = "@cf/baai/bge-m3";
const MIN_SENT_LEN = 20;
const MAX_SENT_LEN = 512;          // BGE-M3 のトークン上限を char proxy で
const SENT_SPLIT = /[。．!?！？]+/;

interface EmbedResult {
  source: string;
  inserted: number;       // 文単位
  skipped: number;
  failed: number;
  duration_ms: number;
}

export async function embedBatch(
  env: Env,
  table: "clean_articles" | "ai_articles",
  limit: number,
): Promise<EmbedResult> {
  const view = table === "clean_articles" ? "v_clean_to_embed" : "v_ai_to_embed";
  const rows = await env.DB.prepare(`SELECT id, text FROM ${view} LIMIT ?`)
    .bind(limit)
    .all<{ id: string | number; text: string }>();

  let inserted = 0;
  let skipped = 0;
  let failed = 0;

  for (const row of rows.results ?? []) {
    const sentences = splitSentences(row.text);
    if (sentences.length === 0) {
      skipped++;
      continue;
    }
    try {
      // Workers AI は配列入力で複数文を一度に embed できる
      const res = (await env.AI.run(MODEL_ID, {
        text: sentences.map((s) => s.text),
      })) as { data: number[][] };

      const stmt = env.DB.prepare(
        `INSERT OR IGNORE INTO sentence_embeddings
         (source_table, source_id, sentence_idx, sentence_text, embedding, model_id)
         VALUES (?, ?, ?, ?, ?, ?)`,
      );

      for (let i = 0; i < sentences.length; i++) {
        const vec = res.data[i];
        if (!vec) continue;
        const buf = new Float32Array(vec).buffer;
        const r = await stmt
          .bind(
            table,
            String(row.id),
            sentences[i]!.idx,
            sentences[i]!.text,
            buf,
            MODEL_ID,
          )
          .run();
        if (r.meta.changes && r.meta.changes > 0) inserted++;
        else skipped++;
      }
    } catch (e) {
      failed++;
    }
  }

  return { source: table, inserted, skipped, failed, duration_ms: 0 };
}

/** 文 split + 長さフィルタ。記事内の元 index を保持する。 */
export function splitSentences(text: string): { idx: number; text: string }[] {
  const out: { idx: number; text: string }[] = [];
  const raw = text.split(SENT_SPLIT);
  for (let i = 0; i < raw.length; i++) {
    const s = (raw[i] ?? "").trim();
    if (s.length < MIN_SENT_LEN) continue;
    out.push({ idx: i, text: s.slice(0, MAX_SENT_LEN) });
  }
  return out;
}

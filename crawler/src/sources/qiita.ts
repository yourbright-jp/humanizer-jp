/**
 * Qiita 2015-2021 巡回。
 *
 * Qiita は公式 REST API があるので Browser Run は不要。
 *   GET https://qiita.com/api/v2/items?query=created%3A%3C2022-06-30&page=N&per_page=100
 *
 * 認証:
 *   - 無認証: 60 req/h (足りない)
 *   - personal access token: 1000 req/h (env.QIITA_TOKEN に設定)
 *
 * 戦略:
 *   - いいね数 ≥ 5 で品質下限
 *   - 本文 1500 字以上
 *   - 公開日 2015-01-01 〜 2022-06-30
 */
import { Env, upsertCleanArticle, urlId } from "../index";

const SOURCE = "qiita";
const API = "https://qiita.com/api/v2/items";

interface QiitaItem {
  id: string;
  title: string;
  body: string;            // markdown
  url: string;
  created_at: string;
  likes_count: number;
}

export async function crawlQiita(
  env: Env,
  limit: number,
): Promise<{ source: string; inserted: number; skipped: number; failed: number; duration_ms: number }> {
  const headers: Record<string, string> = { "User-Agent": env.USER_AGENT };
  // QIITA_TOKEN は wrangler secret put QIITA_TOKEN で設定。
  // env.QIITA_TOKEN は string | undefined となるので存在チェック
  const token = (env as unknown as { QIITA_TOKEN?: string }).QIITA_TOKEN;
  if (token) headers.Authorization = `Bearer ${token}`;

  let inserted = 0;
  let skipped = 0;
  let failed = 0;
  // ページングで limit 件数集まるまで
  for (let page = 1; page <= 50; page++) {
    if (inserted >= limit) break;
    const query = `created:<2022-07-01+created:>2014-12-31+stocks:>=5`;
    const url = `${API}?query=${encodeURIComponent(query)}&page=${page}&per_page=20`;
    try {
      const r = await fetch(url, { headers });
      if (!r.ok) {
        failed++;
        await sleep(2000);
        continue;
      }
      const items = (await r.json()) as QiitaItem[];
      if (!items.length) break;
      for (const item of items) {
        if (inserted >= limit) break;
        if (item.likes_count < 5) {
          skipped++;
          continue;
        }
        if (item.body.length < 1500) {
          skipped++;
          continue;
        }
        const published = item.created_at.slice(0, 10);
        if (published < env.DATE_MIN || published > env.DATE_MAX) {
          skipped++;
          continue;
        }
        const id = await urlId(item.url);
        const result = await upsertCleanArticle(env, {
          id,
          source: SOURCE,
          url: item.url,
          title: item.title,
          text: stripMarkdown(item.body),
          published_at: published,
        });
        if (result === "inserted") inserted++;
        else skipped++;
      }
    } catch (e) {
      failed++;
      await sleep(2000);
    }
    await sleep(500);
  }

  return { source: SOURCE, inserted, skipped, failed, duration_ms: 0 };
}

/** Qiita 本文の Markdown を粗く plain text に */
function stripMarkdown(md: string): string {
  return md
    .replace(/```[\s\S]*?```/g, "")          // code fence
    .replace(/`[^`]+`/g, "")                 // inline code
    .replace(/!\[[^\]]*\]\([^)]+\)/g, "")    // image
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1") // link → text
    .replace(/^#+\s+/gm, "")                 // heading marker
    .replace(/^\s*[-*+]\s+/gm, "")           // bullet marker
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * はてなブログ 2018-2021 巡回。
 *
 * 戦略:
 *   - docs/seed_hatena_blogs.txt の中身は wrangler 経由で読めないので、
 *     wrangler.toml の vars または KV に事前 push しておく
 *     (この scaffold では env.HATENA_SEED_URLS = "url1,url2,..." を想定)
 *   - 各 blog の /archive/YYYY/MM (2018-01 〜 2022-06) を Browser Run で取得
 *   - エントリリンク → 各記事ページを Browser Run で取得
 *   - <time datetime="..."> から公開日を確認、DATE_MIN〜DATE_MAX 範囲のみ採用
 *   - 本文 1500 字以上、コードブロック比率 < 30%、画像のみ記事を除外
 *
 * Browser Run の使い方:
 *   1) Quick Actions HTTP API:
 *        POST https://api.cloudflare.com/.../browser-run/quick-actions/markdown
 *        { "url": "...", "wait_for": "networkidle" }
 *      → markdown 取得が一発でできる。これが一番楽
 *   2) Worker 内で @cloudflare/puppeteer を起動して page.evaluate
 *      → 細かい操作が要る場合
 *
 * 当面は Quick Actions markdown を使う方針 (実装最短)。
 */
import { Env, upsertCleanArticle, urlId } from "../index";

const SOURCE = "hatena";

interface CrawlResult {
  source: string;
  inserted: number;
  skipped: number;
  failed: number;
  duration_ms: number;
}

export async function crawlHatena(env: Env, limit: number): Promise<CrawlResult> {
  // TODO(crawler):
  //   1) seed URL list の取り込み方を決める (env vars / KV / hardcoded)
  //   2) /archive/YYYY/MM ループ
  //   3) entry link の抽出
  //   4) 各記事を Browser Run で fetch
  //   5) <time> 検証 + 本文抽出 + upsertCleanArticle
  //
  // 開発順序:
  //   - まず 1 ブログ × 1 月で end-to-end が回ることを確認
  //   - 次に seed list 全体に拡大
  //   - rate limit: 同一 host への連続アクセス間 2 秒
  return { source: SOURCE, inserted: 0, skipped: 0, failed: 0, duration_ms: 0 };
}

/** Browser Run Quick Actions markdown 取得 (HTTP API ラッパ) */
export async function fetchAsMarkdown(env: Env, url: string): Promise<string | null> {
  // Browser binding 経由の RPC は SDK によって書き方が異なる。
  // 現状の標準はおそらく:
  //   const browser = await puppeteer.launch(env.BROWSER);
  //   const page = await browser.newPage();
  //   await page.goto(url, { waitUntil: "networkidle0" });
  //   return await page.content();
  //
  // Quick Actions エンドポイントを fetch する場合:
  //   const r = await fetch("https://api.cloudflare.com/.../browser-run/quick-actions/markdown", {
  //     method: "POST",
  //     headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
  //     body: JSON.stringify({ url }),
  //   });
  //   return (await r.json()).result.markdown;
  return null;
}

// 使用予定:
export const _markUnused = { urlId, upsertCleanArticle, SOURCE };

/**
 * note.com 2018-2021 巡回。
 *
 * 戦略:
 *   - docs/seed_note_creators.txt の handle 一覧を seed として
 *   - https://note.com/{handle}/all のクリエイターページから記事一覧を取得
 *     (note の公開 API は限定的なので Browser Run で HTML 取得 + scroll)
 *   - 各記事 https://note.com/{handle}/n/{id} を Browser Run で取得
 *   - 投稿日が DATE_MIN〜DATE_MAX 範囲内のもののみ採用
 *   - 本文 1500 字以上
 *
 * 落とし穴:
 *   - note は SPA で無限スクロール。Browser Run の Puppeteer で scrollIntoView ループ必須
 *   - 著者の自己宣伝記事 (有料 note) はメタデータで弾く
 */
import { Env, upsertCleanArticle, urlId } from "../index";

const SOURCE = "note";

export async function crawlNote(
  env: Env,
  limit: number,
): Promise<{ source: string; inserted: number; skipped: number; failed: number; duration_ms: number }> {
  // TODO(crawler):
  //   1) seed handle 一覧の取得
  //   2) クリエイターページから記事 URL 抽出 (Puppeteer scroll loop)
  //   3) 各記事を Browser Run で fetch、公開日 + 本文を抽出
  //   4) upsertCleanArticle
  return { source: SOURCE, inserted: 0, skipped: 0, failed: 0, duration_ms: 0 };
}

export const _markUnused = { urlId, upsertCleanArticle, SOURCE };

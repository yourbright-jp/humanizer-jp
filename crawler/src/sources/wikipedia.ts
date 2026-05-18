/**
 * Wikipedia 2021-12 dump からの抽出。
 *
 * 前提:
 *   R2 bucket "jp-ai-tells-dumps" に jawiki-20211201-pages-articles.xml.bz2 を置く
 *   (gz/bz2 のままでも OK、ストリーミング展開する)
 *
 * 戦略:
 *   - dump を stream で読み、<page> ブロック単位で parse
 *   - namespace=0 (本記事), redirect なし, 本文 1500 字以上を採用
 *   - Wikitext は `mwparserfromhell` 相当の処理を Worker で書くのは重い:
 *     軽量に [[link]] / {{template}} / refs を正規表現で除去するだけにする
 *   - target 数に達したら止める
 *
 * NOTE: 本格的な Wikitext → plain text 変換が必要なら別途オフライン処理に分離
 *       (Worker で 30 秒 CPU 制限あり)。当面は粗い変換で OK。
 */
import { Env, upsertCleanArticle, urlId } from "../index";

const DUMP_KEY = "jawiki-20211201-pages-articles.xml.bz2";
const SOURCE = "wikipedia";

export async function crawlWikipedia(
  env: Env,
  limit: number,
): Promise<{ source: string; inserted: number; skipped: number; failed: number; duration_ms: number }> {
  const obj = await env.DUMPS.get(DUMP_KEY);
  if (!obj) {
    throw new Error(
      `R2 object ${DUMP_KEY} not found. Upload jawiki-20211201-pages-articles.xml.bz2 first.`,
    );
  }

  // TODO(crawler): ストリーミング bz2 展開 + XML SAX parse の実装。
  //   - Workers では bzip2 ネイティブ展開はサポート外。事前にローカルで bz2 → xml.gz に変換し
  //     gzip を Worker の DecompressionStream で展開するのが現実的。
  //   - もしくは: ローカル node スクリプトで dump を pre-parse して D1 に直接 INSERT する
  //     (これが一番速い。Worker は使わず scripts/local/wikipedia_to_d1.ts を別途用意)
  //
  // 当面 stub:
  return {
    source: SOURCE,
    inserted: 0,
    skipped: 0,
    failed: 0,
    duration_ms: 0,
  };
}

/** 内部使用: Wikitext → plain text の粗い変換 */
export function wikitextToPlain(wt: string): string {
  return wt
    .replace(/<ref[^>]*>[\s\S]*?<\/ref>/g, "")
    .replace(/<ref[^/]*\/>/g, "")
    .replace(/\{\{[^{}]*\}\}/g, "")
    .replace(/\[\[(?:[^\]|]*\|)?([^\]]+)\]\]/g, "$1")
    .replace(/'''([^']+)'''/g, "$1")
    .replace(/''([^']+)''/g, "$1")
    .replace(/^=+\s*([^=]+?)\s*=+\s*$/gm, "$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

// 使用予定 (将来 stub を埋めるとき):
export const _markUnused = { urlId, upsertCleanArticle, SOURCE };

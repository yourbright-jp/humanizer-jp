"""タイポグラフィ・記号・構造に関する文書レベルメトリクスを集計する。

メトリクス (記事 1 本あたりの率 or 平均):
    - em_dash_per_1k_chars        : "—" の出現率
    - ellipsis_per_1k_chars       : "…" "・・・" 出現率
    - fullwidth_paren_pair_per_1k : 「」『』（）の対数
    - bold_marker_per_1k          : "**" マークアップ (note 等) 数
    - list_bullet_lines_ratio     : 行頭が "- " "・" "* " の比率
    - heading_lines_ratio         : 行頭が "#" の比率
    - mean_paragraph_chars        : 段落あたり平均文字数
    - kanji_ratio                 : 漢字 / 全文字 (記号除く)
    - passive_rate                : 「られ」「れた」末尾の出現率 (粗い proxy)
    - char_count                  : 記事文字数 (長さ feature)

出力:
    data/analysis/doc_metrics_{bucket}.json
        [{"id", ...metrics}, ...]
    data/analysis/doc_metrics_summary.json
        各 bucket の mean / median / std を bucket × metric で table 化

長さ自体を AI tell の feature として扱うため char_count もそのまま出す。
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path

from _corpus import ANALYSIS_DIR, BUCKETS_SQL, iter_doc  # type: ignore[import-not-found]

KANJI_RE = re.compile(r"[一-鿿々]")
NON_PUNCT_RE = re.compile(r"[一-鿿ぁ-ゖァ-ヺA-Za-z0-9]")
PARA_SPLIT = re.compile(r"\n\s*\n")
EMDASH_RE = re.compile(r"—")
ELLIPSIS_RE = re.compile(r"…|・・・|\.\.\.")
FW_PAREN_RE = re.compile(r"[「『（]")
BOLD_RE = re.compile(r"\*\*[^*\n]+\*\*")
PASSIVE_TAIL_RE = re.compile(r"(られ|れて|れた|られて|られた|れる|られる)[。.\s]")


def doc_metrics(text: str) -> dict:
    n = len(text)
    if n == 0:
        return {}
    kanji = len(KANJI_RE.findall(text))
    nonpunct = len(NON_PUNCT_RE.findall(text))
    lines = text.split("\n")
    bullet = sum(1 for ln in lines if re.match(r"\s*(-|\*|・)\s", ln))
    heading = sum(1 for ln in lines if re.match(r"\s*#{1,6}\s", ln))
    paras = [p for p in PARA_SPLIT.split(text) if p.strip()]
    return {
        "char_count": n,
        "em_dash_per_1k": len(EMDASH_RE.findall(text)) / n * 1000,
        "ellipsis_per_1k": len(ELLIPSIS_RE.findall(text)) / n * 1000,
        "fullwidth_paren_per_1k": len(FW_PAREN_RE.findall(text)) / n * 1000,
        "bold_per_1k": len(BOLD_RE.findall(text)) / n * 1000,
        "list_bullet_lines_ratio": bullet / max(len(lines), 1),
        "heading_lines_ratio": heading / max(len(lines), 1),
        "mean_paragraph_chars": statistics.mean(len(p) for p in paras) if paras else 0,
        "n_paragraphs": len(paras),
        "kanji_ratio": kanji / max(nonpunct, 1),
        "passive_rate_per_1k": len(PASSIVE_TAIL_RE.findall(text)) / n * 1000,
    }


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {}
    keys = [k for k in rows[0] if k != "id"]
    out: dict = {}
    for k in keys:
        vals = [r[k] for r in rows if k in r and r[k] is not None]
        if not vals:
            continue
        out[k] = {
            "mean": round(statistics.mean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "stdev": round(statistics.pstdev(vals), 4) if len(vals) > 1 else 0.0,
            "n": len(vals),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buckets", nargs="+", default=list(BUCKETS_SQL), choices=list(BUCKETS_SQL))
    args = ap.parse_args()

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    summary: dict = {}
    for bucket in args.buckets:
        rows = []
        for obj in iter_doc(bucket):
            m = doc_metrics(obj.get("text", ""))
            if not m:
                continue
            m["id"] = obj.get("id", "?")
            rows.append(m)
        out = ANALYSIS_DIR / f"doc_metrics_{bucket}.json"
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        summary[bucket] = summarize(rows)
        print(f"{bucket}: {len(rows)} docs → {out}")

    s = ANALYSIS_DIR / "doc_metrics_summary.json"
    s.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary → {s}")


if __name__ == "__main__":
    main()

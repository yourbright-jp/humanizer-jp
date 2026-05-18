"""n-gram 対数尤度比で「AI 側で頻度上昇」する語彙を抽出する。

理論:
    Dunning (1993) の log-likelihood ratio。2x2 contingency table:

                     bucket_A    bucket_B
        target term:    a           b
        其他全 token:   c-a         d-b

    G2 = 2 * (a * log(a / E_a) + b * log(b / E_b))   (a>0, b>0)
       E_a = c * (a + b) / (c + d)
       E_b = d * (a + b) / (c + d)

    G2 は χ² 分布 (df=1) で近似。p<0.0001 → G2 > 15.13。

    効果量: ratio = (a/c) / (b/d) — AI 側相対頻度 / human 側相対頻度。
    採用閾値: G2 > 15.13 かつ ratio > 3.0。

出力:
    data/analysis/loglikelihood_{n}gram_{bucket}_vs_clean.json
        [{"ngram", "ai_count", "clean_count", "ai_per_1k", "clean_per_1k",
          "G2", "ratio", "rank"}, ...]
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from _corpus import (  # type: ignore[import-not-found]
    ANALYSIS_DIR,
    iter_text,
    ngrams,
    tokenize,
)


def count_ngrams(bucket: str, n: int) -> tuple[Counter, int]:
    c: Counter = Counter()
    total = 0
    for text in iter_text(bucket):
        toks = tokenize(text)
        for g in ngrams(toks, n):
            c[g] += 1
            total += 1
    return c, total


def g2(a: int, b: int, c_total: int, d_total: int) -> float:
    if a == 0 and b == 0:
        return 0.0
    expected_a = c_total * (a + b) / (c_total + d_total)
    expected_b = d_total * (a + b) / (c_total + d_total)
    val = 0.0
    if a > 0 and expected_a > 0:
        val += a * math.log(a / expected_a)
    if b > 0 and expected_b > 0:
        val += b * math.log(b / expected_b)
    return 2.0 * val


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2, help="n-gram size (1/2/3)")
    ap.add_argument("--ai-bucket", default="ai_claude", choices=["ai_claude"])
    ap.add_argument("--min-count", type=int, default=10, help="AI 側最小出現数")
    ap.add_argument("--g2-thresh", type=float, default=15.13)
    ap.add_argument("--ratio-thresh", type=float, default=3.0)
    ap.add_argument("--top", type=int, default=500)
    args = ap.parse_args()

    print(f"counting {args.n}-grams: clean ...")
    clean_counts, clean_total = count_ngrams("clean", args.n)
    print(f"  {len(clean_counts)} types, {clean_total} tokens")

    print(f"counting {args.n}-grams: {args.ai_bucket} ...")
    ai_counts, ai_total = count_ngrams(args.ai_bucket, args.n)
    print(f"  {len(ai_counts)} types, {ai_total} tokens")

    rows = []
    for ng, ai_c in ai_counts.items():
        if ai_c < args.min_count:
            continue
        cl_c = clean_counts.get(ng, 0)
        ai_per = ai_c / ai_total * 1000
        cl_per = cl_c / clean_total * 1000 if clean_total else 0.0
        if cl_per == 0:
            ratio = float("inf")
        else:
            ratio = ai_per / cl_per
        if ratio < args.ratio_thresh:
            continue
        score = g2(ai_c, cl_c, ai_total, clean_total)
        if score < args.g2_thresh:
            continue
        rows.append(
            {
                "ngram": "".join(ng) if args.n > 1 else ng[0],
                "tokens": list(ng),
                "ai_count": ai_c,
                "clean_count": cl_c,
                "ai_per_1k": round(ai_per, 4),
                "clean_per_1k": round(cl_per, 4),
                "G2": round(score, 2),
                "ratio": None if math.isinf(ratio) else round(ratio, 2),
            }
        )

    rows.sort(key=lambda r: r["G2"], reverse=True)
    rows = rows[: args.top]
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    out = ANALYSIS_DIR / f"loglikelihood_{args.n}gram_{args.ai_bucket}_vs_clean.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(rows)} rows → {out}")


if __name__ == "__main__":
    main()

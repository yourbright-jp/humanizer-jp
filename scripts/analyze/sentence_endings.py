"""文末パターンの分布差を抽出する。

戦略:
    1. テキストを 。/!/?/！/？ で sentence split
    2. 各 sentence の **末尾 4 文字** を「文末 token」として集計
       (sudachi 終止形より単純で AI 臭の検出に十分機能する)
    3. clean vs ai_bucket で出現率を比較し log-likelihood + ratio で sort

なぜ surface 文末:
    sudachi の終止形だけだと「することができる」「することができます」のような
    冗長文末を一括りにしてしまい、敬体 / 常体差や定型句的な冗長性が消える。

出力:
    data/analysis/sentence_endings_{bucket}_vs_clean.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter

from _corpus import ANALYSIS_DIR, iter_text  # type: ignore[import-not-found]
from loglikelihood import g2  # type: ignore[import-not-found]

SENT_SPLIT = re.compile(r"[。．!?！？]+")


def iter_sentence_tails(bucket: str, tail_len: int) -> Counter:
    c: Counter = Counter()
    total = 0
    for text in iter_text(bucket):
        for sent in SENT_SPLIT.split(text):
            s = sent.strip()
            if len(s) < tail_len:
                continue
            tail = s[-tail_len:]
            c[tail] += 1
            total += 1
    c["__total__"] = total
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai-bucket", default="ai_claude", choices=["ai_claude"])
    ap.add_argument("--tail-len", type=int, default=4)
    ap.add_argument("--min-count", type=int, default=10)
    ap.add_argument("--g2-thresh", type=float, default=15.13)
    ap.add_argument("--ratio-thresh", type=float, default=3.0)
    ap.add_argument("--top", type=int, default=300)
    args = ap.parse_args()

    print(f"counting tail-{args.tail_len}: clean ...")
    clean_c = iter_sentence_tails("clean", args.tail_len)
    clean_total = clean_c.pop("__total__")

    print(f"counting tail-{args.tail_len}: {args.ai_bucket} ...")
    ai_c = iter_sentence_tails(args.ai_bucket, args.tail_len)
    ai_total = ai_c.pop("__total__")

    rows = []
    for tail, ac in ai_c.items():
        if ac < args.min_count:
            continue
        cc = clean_c.get(tail, 0)
        ai_per = ac / ai_total * 1000
        cl_per = cc / clean_total * 1000 if clean_total else 0.0
        ratio = float("inf") if cl_per == 0 else ai_per / cl_per
        if ratio < args.ratio_thresh:
            continue
        score = g2(ac, cc, ai_total, clean_total)
        if score < args.g2_thresh:
            continue
        rows.append(
            {
                "tail": tail,
                "ai_count": ac,
                "clean_count": cc,
                "ai_per_1k_sentences": round(ai_per, 4),
                "clean_per_1k_sentences": round(cl_per, 4),
                "G2": round(score, 2),
                "ratio": None if math.isinf(ratio) else round(ratio, 2),
            }
        )
    rows.sort(key=lambda r: r["G2"], reverse=True)
    rows = rows[: args.top]
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    out = ANALYSIS_DIR / f"sentence_endings_{args.ai_bucket}_vs_clean.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(rows)} rows → {out}")


if __name__ == "__main__":
    main()

"""loglikelihood / sentence_endings / punctuation の結果を統合し、
最終成果物 data/analysis/ai_tells.json を出力する (v2: 単一モデル運用)。

v2 でのスコープ縮小:
    - 3 モデル投票による「general vs model_specific」分類は廃止
    - 検出された tell はすべて「Opus 4.7 tell」として扱う
    - 将来 Gemini / Codex を追加する余地は残す (model_specific_tells.json は引き続き出すが当面空)

依存:
    事前に以下を走らせる:
        python scripts/analyze/loglikelihood.py --n 1
        python scripts/analyze/loglikelihood.py --n 2
        python scripts/analyze/loglikelihood.py --n 3
        python scripts/analyze/sentence_endings.py
        python scripts/analyze/punctuation.py

出力:
    data/analysis/ai_tells.json
        {
          "method": {"g2_thresh", "ratio_thresh", "model": "claude-opus-4-7"},
          "doc_metrics_summary": {clean: {...}, ai_claude: {...}},
          "vocabulary_tells": {
              "1gram": [{ngram, ai_count, clean_count, ai_per_1k, clean_per_1k, G2, ratio, rank}, ...],
              "2gram": [...],
              "3gram": [...]
          },
          "sentence_ending_tells": [...]
        }
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _corpus import ANALYSIS_DIR  # type: ignore[import-not-found]

AI_BUCKET = "ai_claude"
MODEL_ID = "claude-opus-4-7"


def load_or_empty(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ngrams", type=int, nargs="+", default=[1, 2, 3])
    args = ap.parse_args()

    vocab: dict[str, list[dict]] = {}
    for n in args.ngrams:
        p = ANALYSIS_DIR / f"loglikelihood_{n}gram_{AI_BUCKET}_vs_clean.json"
        vocab[f"{n}gram"] = load_or_empty(p)

    endings = load_or_empty(ANALYSIS_DIR / f"sentence_endings_{AI_BUCKET}_vs_clean.json")

    # Phase 4: paraphrase クラスタ (embedding ベース)
    paraphrase_clusters = load_or_empty(ANALYSIS_DIR / "paraphrase_clusters.json")

    doc_summary_path = ANALYSIS_DIR / "doc_metrics_summary.json"
    doc_summary = (
        json.loads(doc_summary_path.read_text(encoding="utf-8"))
        if doc_summary_path.exists()
        else {}
    )

    final = {
        "method": {
            "g2_thresh": 15.13,
            "ratio_thresh": 3.0,
            "min_count": 10,
            "ai_bucket": AI_BUCKET,
            "model_id": MODEL_ID,
            "scope": (
                "v2 単一モデル運用。検出された tell はすべて Opus 4.7 由来として扱う。"
                "「AI 一般 tell」と「モデル固有」の段階分離は v2 では未実装。"
            ),
            "phases": {
                "1-3_frequency": "loglikelihood + sentence_endings + punctuation",
                "4_paraphrase_clustering": "BGE-M3 文埋め込み + HDBSCAN クラスタ → AI 偏向クラスタ抽出",
            },
        },
        "doc_metrics_summary": doc_summary,
        "vocabulary_tells": vocab,
        "sentence_ending_tells": endings,
        "paraphrase_tells": paraphrase_clusters,
    }

    out = ANALYSIS_DIR / "ai_tells.json"
    out.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")

    vocab_counts = {k: len(v) for k, v in vocab.items()}
    print(
        f"ai_tells.json: vocabulary={vocab_counts}, "
        f"sentence_endings={len(endings)}, paraphrase_clusters={len(paraphrase_clusters)}"
    )


if __name__ == "__main__":
    main()

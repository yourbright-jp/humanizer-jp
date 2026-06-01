"""Phase 4: 文単位埋め込みを HDBSCAN でクラスタリングし、
AI 偏向クラスタを「言い換え系 AI tell」として抽出する。

データソース:
    D1.sentence_embeddings (Worker /embed/clean + /embed/ai で生成済み)
    wrangler d1 export 経由でローカル SQLite に dump 済みの前提。

処理:
    1. sentence_embeddings から source_table 別に embedding を読み取り (BLOB → np.float32[1024])
    2. HDBSCAN で全体クラスタリング (min_cluster_size 推奨 = 10, metric='cosine')
       - cosine 用に L2-normalize してから euclidean で実行
    3. 各クラスタの AI/human 比を集計
    4. AI 比 >= 75% + cluster size >= 10 を「言い換え系 AI tell クラスタ」として出力
    5. クラスタの代表文 (centroid に最も近い文) を 3 個 sample
    6. ranking して data/analysis/paraphrase_clusters.json に保存

出力スキーマ:
    [
      {
        "cluster_id": 17,
        "size": 45,
        "ai_count": 42,
        "clean_count": 3,
        "ai_ratio": 0.933,
        "representative_sentences": ["...", "...", "..."],
        "ai_per_1k_ai_sentences": ...,
        "clean_per_1k_clean_sentences": ...,
        "lift": ai_ratio / clean_ratio
      },
      ...
    ]

extract_tells.py は paraphrase_clusters.json を merge して
ai_tells.json の "paraphrase_tells" 列に挿入する。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import struct
from collections import Counter
from pathlib import Path

from _corpus import ANALYSIS_DIR, connect  # type: ignore[import-not-found]

EMB_DIM = 1024


def load_embeddings(min_count: int = 0) -> tuple[list[dict], "np.ndarray"]:
    """sentence_embeddings 全件を読み、(meta_list, vectors) を返す。"""
    import numpy as np  # local import (重いので)

    rows: list[dict] = []
    vecs: list[bytes] = []
    with connect() as con:
        con.row_factory = sqlite3.Row
        for r in con.execute(
            "SELECT id, source_table, source_id, sentence_idx, sentence_text, embedding "
            "FROM sentence_embeddings"
        ):
            rows.append(
                {
                    "id": r["id"],
                    "source_table": r["source_table"],
                    "source_id": r["source_id"],
                    "sentence_idx": r["sentence_idx"],
                    "sentence_text": r["sentence_text"],
                }
            )
            vecs.append(r["embedding"])
    if not vecs:
        return [], np.zeros((0, EMB_DIM), dtype=np.float32)
    # BLOB は Float32Array.buffer なので little-endian f32 として読む
    arr = np.frombuffer(b"".join(vecs), dtype=np.float32).reshape(-1, EMB_DIM)
    return rows, arr


def l2_normalize(x):
    import numpy as np

    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return x / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-cluster-size", type=int, default=10)
    ap.add_argument("--ai-ratio-thresh", type=float, default=0.75)
    ap.add_argument("--lift-thresh", type=float, default=3.0)
    ap.add_argument("--samples", type=int, default=3, help="代表文サンプル数")
    ap.add_argument(
        "--pca-dim",
        type=int,
        default=50,
        help="HDBSCAN 前に PCA で次元削減 (0=無効)。1024d 生ベクトルは spatial tree が"
        " 効かず数万点で実用外になるため、cosine 構造を保つ PCA で前処理する。",
    )
    args = ap.parse_args()

    try:
        import numpy as np
        import hdbscan  # type: ignore
    except ImportError as e:
        raise SystemExit(
            f"hdbscan + numpy が必要: pip install hdbscan numpy. ({e})"
        )

    print("loading embeddings ...")
    meta, vecs = load_embeddings()
    if len(meta) == 0:
        print("no embeddings found. run /embed/clean + /embed/ai first.")
        return
    print(f"  {len(meta)} sentences, dim={vecs.shape[1]}")

    vecs = vecs.astype(np.float32)
    # 高次元 (1024d) のままだと HDBSCAN の空間木が機能せず数万点で実用外。
    # cosine 構造をほぼ保ったまま PCA で削減してからクラスタリングする。
    if args.pca_dim and vecs.shape[1] > args.pca_dim:
        from sklearn.decomposition import PCA

        print(f"  PCA {vecs.shape[1]}d -> {args.pca_dim}d ...")
        pca = PCA(n_components=args.pca_dim, svd_solver="randomized", random_state=0)
        vecs = pca.fit_transform(vecs).astype(np.float32)
        evr = float(pca.explained_variance_ratio_.sum())
        print(f"  explained variance ratio (sum) = {evr:.3f}")

    # cosine 距離は L2 正規化後の euclidean に等しい
    vecs_norm = l2_normalize(vecs)

    print(f"clustering (HDBSCAN min_cluster_size={args.min_cluster_size}) ...")
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=args.min_cluster_size,
        metric="euclidean",
        core_dist_n_jobs=-1,
    )
    labels = clusterer.fit_predict(vecs_norm)

    # 集計
    n_clean = sum(1 for m in meta if m["source_table"] == "clean_articles")
    n_ai = sum(1 for m in meta if m["source_table"] == "ai_articles")
    print(f"  sentences: clean={n_clean}, ai={n_ai}")
    print(f"  found {labels.max() + 1} clusters (label -1 = noise = {(labels == -1).sum()})")

    clusters: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        if lab < 0:
            continue
        clusters.setdefault(int(lab), []).append(i)

    rows = []
    for cid, idxs in clusters.items():
        c_count = sum(1 for i in idxs if meta[i]["source_table"] == "clean_articles")
        a_count = sum(1 for i in idxs if meta[i]["source_table"] == "ai_articles")
        size = c_count + a_count
        ai_ratio = a_count / size if size else 0
        if ai_ratio < args.ai_ratio_thresh:
            continue
        ai_per_1k = (a_count / n_ai * 1000) if n_ai else 0
        clean_per_1k = (c_count / n_clean * 1000) if n_clean else 0
        lift = (ai_per_1k / clean_per_1k) if clean_per_1k > 0 else float("inf")
        if lift < args.lift_thresh:
            continue

        # 代表文: cluster centroid に最も近い文を args.samples 個
        cluster_vecs = vecs_norm[idxs]
        centroid = cluster_vecs.mean(axis=0)
        centroid /= max(np.linalg.norm(centroid), 1e-9)
        sims = cluster_vecs @ centroid
        top = sims.argsort()[::-1][: args.samples]
        rep = [meta[idxs[int(t)]]["sentence_text"] for t in top]

        rows.append(
            {
                "cluster_id": cid,
                "size": size,
                "ai_count": a_count,
                "clean_count": c_count,
                "ai_ratio": round(ai_ratio, 4),
                "ai_per_1k_ai_sentences": round(ai_per_1k, 3),
                "clean_per_1k_clean_sentences": round(clean_per_1k, 3),
                "lift": None if lift == float("inf") else round(lift, 2),
                "representative_sentences": rep,
            }
        )

    rows.sort(key=lambda r: (r["ai_count"], r["lift"] or 0), reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    out = ANALYSIS_DIR / "paraphrase_clusters.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(rows)} ai-biased clusters → {out}")


if __name__ == "__main__":
    main()

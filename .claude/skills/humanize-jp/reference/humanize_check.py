#!/usr/bin/env python3
"""日本語テキストの「AIらしさ」を計量診断するスクリプト。

humanizer-jp の検証(docs/findings_verification.md)で確定した頑健な指標だけを使う。
最重要は「文長の均一性(変動係数 CV)」で、これ単体が AI 記事の 99% を人間中央値から
分離した唯一の汎用指紋。語彙・談話のクセは補助シグナル。

使い方:
    python3 humanize_check.py path/to/text.txt
    cat text.md | python3 humanize_check.py -
依存なし(標準ライブラリのみ。形態素解析は使わず文字ベースで概算)。
"""
from __future__ import annotations

import re
import sys
import statistics as st

# 人間 / AI のベンチマーク中央値(docs/findings_verification.md より)
BENCH = {
    "sent_len_cv": {"human": 0.81, "ai": 0.55, "good": ">= 0.70", "dir": "high"},
    "period_per_1k": {"human": 12.0, "ai": 19.5, "good": "<= 14", "dir": "low"},
    "comma_per_sent": {"human": 0.0, "ai": 1.0, "good": "混在(0 の文も作る)", "dir": "low"},
    "hiragana_ratio": {"human": 0.30, "ai": 0.48, "good": "<= 0.42", "dir": "low"},
}

# 確定した語彙・文末・談話の AI tell(出れば強い補助シグナル)
TELL_PATTERNS = {
    "整理(する/すると)": r"整理(する|すると|して)",
    "〜しておきたい/おきます": r"してお(き|こ)(たい|ます|う)",
    "地味": r"地味",
    "一方(で)〔文頭〕": r"(^|\n|。)\s*一方",
    "つまり〔文頭〕": r"(^|\n|。)\s*つまり",
    "本記事では/この記事では": r"(本記事|この記事)で(は|も)",
    "〜といえます/といえるでしょう": r"といえ(ます|るでしょう|よう)",
    "高い水準で〜": r"高い水準",
    "〜ではないでしょうか": r"ではないでしょうか",
}


def sentences(text: str) -> list[str]:
    # コードブロック・Markdown 記号を除いて地の文だけ評価
    t = re.sub(r"```.*?```", "", text, flags=re.S)
    t = re.sub(r"`[^`]*`", "", t)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"[*_>|]", "", t)
    parts = re.split(r"(?<=[。！？])", t)
    return [s.strip() for s in parts if len(s.strip()) >= 2]


def char_class_ratios(text: str) -> dict:
    chars = [c for c in text if not c.isspace()]
    n = len(chars) or 1
    hira = sum(1 for c in chars if "぀" <= c <= "ゟ")
    kanji = sum(1 for c in chars if "一" <= c <= "鿿")
    kata = sum(1 for c in chars if "゠" <= c <= "ヿ")
    return {"hiragana_ratio": hira / n, "kanji_ratio": kanji / n, "katakana_ratio": kata / n}


def analyze(text: str) -> None:
    ss = sentences(text)
    if len(ss) < 3:
        print("⚠ 文が少なすぎて診断できません(3文以上が必要)。")
        return
    lengths = [len(s) for s in ss]
    mean_len = sum(lengths) / len(lengths)
    cv = st.pstdev(lengths) / mean_len if mean_len else 0.0
    n_chars = len(re.sub(r"\s", "", text)) or 1
    period = (text.count("。")) / n_chars * 1000
    comma_per_sent = text.count("、") / len(ss)
    ratios = char_class_ratios(text)

    metrics = {
        "sent_len_cv": cv,
        "period_per_1k": period,
        "comma_per_sent": comma_per_sent,
        "hiragana_ratio": ratios["hiragana_ratio"],
    }

    print("=" * 56)
    print(" 文体メトリクス(人間 ⇄ AI のどちら寄りか)")
    print("=" * 56)
    print(f"{'指標':<22}{'値':>8}{'人間':>8}{'AI':>8}   目標")
    print("-" * 56)
    flags = []
    for key, val in metrics.items():
        b = BENCH[key]
        ai_side = (val >= (b["human"] + b["ai"]) / 2) if b["dir"] == "high" else (
            val >= (b["human"] + b["ai"]) / 2
        )
        # dir=high: 値が低い=AI寄り。dir=low: 値が高い=AI寄り。
        if b["dir"] == "high":
            is_ai = val < (b["human"] + b["ai"]) / 2
        else:
            is_ai = val > (b["human"] + b["ai"]) / 2
        mark = "🤖AI寄り" if is_ai else "🧑人間寄り"
        print(f"{key:<22}{val:>8.2f}{b['human']:>8.2f}{b['ai']:>8.2f}   {b['good']}  {mark}")
        if is_ai:
            flags.append(key)
    print()

    # 最重要シグナル
    print(f"▶ 文長: 平均 {mean_len:.0f}字 / 範囲 {min(lengths)}–{max(lengths)}字 / CV {cv:.2f}")
    if cv < 0.70:
        short = sum(1 for x in lengths if x < mean_len * 0.6)
        long = sum(1 for x in lengths if x > mean_len * 1.5)
        print(f"  ⚠ 文の長さが均一すぎます(最重要指紋)。短い文(<{mean_len*0.6:.0f}字)={short} / "
              f"長い文(>{mean_len*1.5:.0f}字)={long}。")
        print("  → 一文を切る / つなぐ、体言止めや短い相づち文を混ぜて緩急をつける。")
    else:
        print("  ✓ 文長のばらつきは人間的(CV >= 0.70)。")
    print()

    # 語彙・談話 tell
    print("=" * 56)
    print(" 語彙・談話の AI tell(出現箇所)")
    print("=" * 56)
    hit_any = False
    for name, pat in TELL_PATTERNS.items():
        c = len(re.findall(pat, text))
        if c:
            hit_any = True
            print(f"  ⚠ {name}: {c}回")
    if not hit_any:
        print("  ✓ 顕著な tell 語句は検出されませんでした。")
    print()

    score = len(flags) + (1 if cv < 0.70 else 0)
    verdict = ["🧑 かなり人間的", "やや AI 寄り", "AI 寄り", "🤖 明確に AI 寄り"][min(score, 3)]
    print(f"総合: {verdict}(該当フラグ {score} 件)")
    print("詳細な根拠は docs/findings_verification.md を参照。")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    arg = sys.argv[1]
    text = sys.stdin.read() if arg == "-" else open(arg, encoding="utf-8").read()
    analyze(text)


if __name__ == "__main__":
    main()

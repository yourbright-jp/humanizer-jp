# AI 文体特徴 (AI tells) 検証レポート (v2)

`docs/findings.md` で抽出された日本語 AI tell を、7 つの解析アングル(各々に独立した反証検証 verdict 付き)で再測定・査読した結果の統合レポート。対象は human 側 `clean_articles` 1,105 本 / AI 側 `ai_articles` (model=claude) 1,105 本、文埋め込み 98,328 文 (@cf/baai/bge-m3, 1024d)。

---

## 1. 要旨

- **頑健に確定した tell は「計量文体」と「語彙ヘッジ/配慮表現」に集中する。** 最強は**文長均一性 (sentence-length CV)**:AI 中央値 0.549 vs human 0.81、rb≈−0.82、AI 記事の 99% が human 中央値を下回り、Markdown 除去・記事長 1500–3000字マッチ後も rb=−0.79 で生き残る(全 tell 中で最も頑健)。
- 語彙では **けれど (15.9×, DF 21%)・地味 (23.1×, DF 18%)・整理 (register マッチ後も 7.5×, DF 29%)・だけ (DF 81%)**、文末では **ておきたい (DF 8%, human ほぼ皆無)**、配慮表現 **ておきます/ておきたい (register マッチ後 2.5–3.0×)** が Markdown 除去後も残る本物の言語的 tell。
- **三点リーダ「…」は AI tell ではなく human tell(逆方向)**:AI は human ブログの約 1/4 しか使わない。複数アングルで一致。
- **`docs/findings.md` §1 で看板にしていた構造系 tell(太字 ×368, 見出し ×206, 箇条書き ×123, `だ。\n\n` ×125, 平均段落長 ×0.08)はすべて収集アーティファクトに格下げ**。Markdown 記号は human 側がプレーン化されているため、`\n\n`・短段落は「human 抽出時に段落境界が破壊された」ことの裏返しで、AI 言語スタイルの証拠にならない。
- **政体 (です/ます) 密度・漢字率・全体 bigram 反復率も tell ではない**(register/ジャンル/記事長の交絡)。

---

## 2. 交絡の決着 — Markdown 収集差はどこまで切り分けられたか

markdown-confound / concentration-df アングルが定量的に決着させた。結論は「**findings.md の警告(AI に Markdown がある)よりも、human 側の段落破壊の方が本質的な交絡**」である。

- **Markdown 記号系 tell(##, 太字 `**`, `- ` 箇条書き, バッククォート)** は AI-DF 11–74% と広く分布するが、定義上 human プレーンテキストには存在し得ない(human-DF 0–4%)。markdown-strip 要件を満たせず**全件アーティファクト確定**。
- **`\n\n` / 短段落終端 (`。\n\n`, `だ。\n\n` 等)** は「`\n\n` は Markdown 記号でない」ため strip では消えず数値は残る(`。\n\n` 比 6.0×, `だ。\n\n` 139.9×)。しかし decisive な per-source 追跡で否定:human の `。\n\n` 5,194 件は **100% qiita 由来**(wikipedia=0, hatena=0, note=0)。per-source `\n\n`/1k は wiki 0.00 / hatena 0.00 / note 0.00 / **qiita 11.85 ≒ AI-strip 12.79**。さらに mean_paragraph_chars は note 105 / qiita 100 が AI 92 とほぼ同一。**段落構造を保存できた human ソースは AI と区別不能**で、差は純粋に抽出器依存。→ **UNVERIFIABLE / アーティファクト確定**。
- human の `\n\n` 密度は中央値 0.0/1k(半数超の human 文書に空行段落なし)。これが「平均段落長 human 1,193字」を膨らませた正体。
- **逆に強化された交絡耐性**:kanji_ratio と passive_rate は strip 後にむしろ上昇(kanji 1.13→1.22×)。これは「Markdown/コードを除いて地の文が濃縮された」ためで、Markdown アーティファクト仮説とは逆。ただし kanji_ratio は §4 で別途否定(ジャンル反転)。

**切り分けの到達点**:純粋な Markdown 記号 tell と段落構造 tell は完全にアーティファクトと判定でき、地の文の語彙・文長・文末・談話接続詞 tell はそれと独立に評価できる状態まで分離された。残る根治不能な交絡は「human 側 4 ソース中 3 ソースが段落境界を喪失」という収集設計の問題(§6)。

---

## 3. 頑健な AI tell(確定)

複数アングル + 反証を生き残ったもの。Markdown 除去耐性のある計量・語彙・文末・談話 tell を看板とする。

### A. 計量文体(漢字仮名率・語彙多様性・文長分散)— 最も頑健

| tell | AI vs human | 効果量 / DF | 交絡耐性 |
|---|---|---|---|
| **文長 CV(均一性)** | AI 中央値 0.549 vs human 0.81 | rb=−0.82, p<1e-89, **DF 99%** | strip 後 0.549、長さマッチ (1500–3000字) でも rb=−0.79。wiki(0.73)blog(0.81)双方を下回る。**全 tell 中最強** |
| **句点密度(短文多用)** | AI 19.5 vs human 12.0 /1k字 | rb=+0.69, **DF 98%** | 。/. のみカウントで Markdown 不感。wiki・blog 双方超え |
| **文長絶対分散 (std/IQR)** | std AI 20.9 vs human 29.8 | rb=−0.54 | strip 不感。両ジャンル下回り、均一性を独立に裏付け |
| **ひらがな率** | AI 0.483 vs human 0.30 | rb=+0.60, **DF 98%** | 文字種のみで Markdown 除外。wiki(0.28)blog(0.35)双方超え。register 寄りの注意は残す |
| **読点/文** | AI 中央値 1.0 vs human 0.0 | rb=+0.53, **DF 80%** | 、のみ。両ジャンル超え |

例:AI は「多く・短く・等長の」文を、読点を最低 1 つ入れて並べる。これが計量上の最大の指紋。

### B. 語彙ヘッジ・評価語(1-gram, Markdown 不感)

| 語 | AI vs human 倍率 | DF / 1105 | register マッチ後 |
|---|---|---|---|
| **地味** | 23.1× (G²=390.6) | 18% | vs blog 15.3×、within-register 22.3× — 強いが低 DF の二次信号 |
| **けれど** | 15.9× (G²=642.9) | 21% | within-register 5.29×(findings の 2.32× は過小、実は deflate していない)。top-10 記事 13.8% で非集中 |
| **整理** | 6.0× (G²=449.5) | 29% | **within-register 7.5×(register マッチで強化)**。最も信頼できる語彙 tell |
| **少し** | 4.2× (G²=608.4) | 45% | within-register 1.95× — register でかなり弱化 |
| **みる(〜してみる)** | 3.9× (G²=437.3) | 40% | strip 耐性あり |
| **だけ** | 3.65× (G²=1679.8) | **81%** | 最も普遍的だが within-register 1.65× で弱化、human-DF も 48% と高め |

→ 「整理」「地味」「けれど」が看板。「だけ/少し」は DF は広いが register 交絡で弱化(二次信号)。

### C. 文末・配慮表現

| tell | AI vs human | DF | register マッチ後 |
|---|---|---|---|
| **ておきたい(単独文末)** | human ほぼ皆無(blog 0.019/1k, wiki 0) | DF 8% (88/1105) | 50×超。raw 含有でも AI 172 doc vs wiki 1 / blog 19。中央値 1 hit/doc で非集中。**この角度で最もクリーンな tell** |
| **ておきます/ておきたい(配慮前置き)** | vs blog 3.5× | DF 29% | **within-register 2.5–3.0×** で生存(decisive test 通過) |
| はずです / のだろう / てほしい | vs blog 2.8–4.3× | DF 8–12% | 「human に皆無」は誤り(human 12–52 doc に存在)。modest な二次信号 |

注:findings.md の「ておきたい 121×」は wiki(0)を分母にした見かけ倍率。honest な基準は対 blog で、それでも明確に AI 偏向。**ておきたい (family ではなく単独)** を信頼する。

### D. 談話構造(prose 接続詞・自己言及)

| tell | AI vs blog | DF | 備考 |
|---|---|---|---|
| **一方/一方で(対比)** | 4.2× (vs wiki 1.7×) | 29% | 全 prose、Markdown 隣接ゼロを確認。**談話 tell の最強** |
| **本記事では/この記事では(自己言及)** | 3.3–4.1× | 7–11% | wiki ≒0、blog 超え |
| **つまり(言い換え)** | 2.7× (vs wiki 10×) | 23% | 両ジャンル超え、広 DF |
| CTA クローザ(ぜひ+てほしい/ください) | closer で 5× over blog | 20% | how-to ジャンル交絡あり(medium) |
| まず(列挙開始) | vs blog 1.6×(DF 50% ≒ blog 51%) | 51% | ジャンル交絡で弱、二次 |

### E. 意味クラスタ(埋め込み)— 低カバレッジだが Markdown-free

| クラスタ | AI 近傍率 | Markdown 隣接 | カバレッジ |
|---|---|---|---|
| **c40 伝記謙遜枕**(「○○という名前を知っている人は、いまではそう多くないかもしれません」) | top-30 0.93–0.97 | 1–2/30 のみ | AI ~26 doc, human 2(0 ではない) |
| **c35 評価まとめ**(「異なる領域を行き来して…といえます」) | 1.00 | 0/30 | size 20 |
| **c34 高評価ヘッジ**(「高い水準で実現されている」) | 0.88 | 0/30 | size 11(やや noisy) |
| **といえるでしょう** | 近傍 0.76 | prose | AI 18 / human 1 |

→ 意味クラスタは「節レベル定型」を捉えるが全て低カバレッジ(18–26 doc)。high precision / low recall。

---

## 4. 収集アーティファクトに格下げ/弱化したもの

findings.md で強調されていたが、交絡・少数記事集中・ジャンル差で説明できると判明:

- **構造系 §1 看板 tell 全滅**:太字 `**` (×368)・見出し (×206)・箇条書き (×123)・`だ。\n\n` (×125)・平均段落長 (×0.08)。Markdown 記号は human プレーンテキストに存在不能、`\n\n` は qiita 以外の human ソースでゼロ → **収集アーティファクト確定**。
- **em dash `—` (findings ×7.8)**:倍率は strip 後も 8.2× で再現するが、**DF わずか 6.5%(72/1105)、上位 10 記事が全 404 件の 42.8%、上位 5% 記事に 93%**。低 base-rate・少数記事集中で **weakened**。
- **政体 (です/ます) 密度**:AI 224.9/1k < blog 267.0/1k(human ブログの方が高い)。register-mixing も AI 0.255 ≒ blog 0.261 とほぼ同一 → **tell でない(register アーティファクト)**。
- **漢字率 (findings ×1.1)**:ジャンルで方向反転(AI 0.278 は wiki 0.369 と blog 0.187 の間。vs wiki rb=−0.39, vs blog +0.61)→ **単独 tell として不可、demote**。
- **全体 bigram 反復率**:方向は「AI が少ない」で正しいが、記事長交絡で 1000 token cap 後 rb −0.46→−0.31 に縮小 → **weakened(中程度・長さ依存)**。
- **のだろう**:within-register で 0.84×(無上昇)、within-register DF 0.01 → **register マッチで実質否定**。
- **広義「のではないでしょうか」**:AI 0.640/1k ≦ blog 0.650/1k(blog の方が高い)→ **AI-distinctive 否定**。狭い「多い+のではないでしょうか」collocation のみ低 DF で残る。
- **NEGATIVE「AI は三部構成/recap マシン」(findings の暗黙前提への反証)**:方向は正しい(AI は recap が blog より少ない)が **誇張**。robust な文末抽出では recap-closer AI 20% vs blog 29%(findings の 7% vs 42% は壊れた段落分割器の artifact)、full tri-part は AI 6% > blog 2%(AI の方が高い)→ **weakened**。
- **意味クラスタ c14 Tips / c55 構成予告 / c21 箇条書き定義 / c15 コード**:近傍の 25–28/30 が Markdown 接頭辞。c55 は human も同内容を 91/1105 で書く(findings の 6 は過小)→ **アーティファクト確定**、lift 37× は膨張。
- **「human-DF = 0」系の主張**:c40・c14 の human ゼロは過小プローブの artifact(実測 c40 human 2, c14 human 9)。倍率・絶対ゼロ主張は割引が必要。

---

## 5. 各アングルの信頼度評価

verdict の result を集計(confirmed / weakened / reclassified-artifact / refuted)。

| アングル | confirmed | weakened | reclassified-artifact | 主な訂正 |
|---|---|---|---|---|
| markdown-confound | 5 | 1 (em dash) | 2 (`\n\n`, 段落長) | human `。\n\n` は 100% qiita 由来 |
| genre-control | 6 | 2 (地味系, のだろう) | 1 (em dash) | 「78.6% polite」再現不能(実 36.5%)、のだろう は register で否定 |
| concentration-df | 2 | 1 (lexical 1-gram) | 5 (Markdown 系) | ひと DF 過大(human 17.2→9.1%)、便利は lift 不足が真因 |
| sentence-endings-hedging | 3 | 3 (family/meta/rhetorical) | 0 | family/meta を 25–40% 過大計上、「human 皆無」は偽 |
| stylometric-distributions | 7 | 1 (bigram 反復) | 0 | 多くが findings より強い数値。bigram は長さ交絡 |
| discourse-structure | 5 | 2 (recap negative) | 0 | recap-closer ギャップ誇張(7%/42% → 20%/29%) |
| semantic-clusters | 4 | 1 (cliche 一般化) | 2 (構造系クラスタ) | human-DF 0 主張は偽、c55 lift 膨張 |
| **合計** | **32** | **11** | **12** | refuted: 0 |

**総評**:refuted(完全否定)はゼロ。元 findings の方向はほぼ honest だが、(a) wiki を分母にした見かけ倍率の誇張、(b) family/meta 集計の 25–40% 過大、(c) human-DF=0 の過小プローブ、(d) 構造系 tell の交絡見落とし、が系統的な弱点。reclassified-artifact 12 件は全て Markdown / 段落 / 構造クラスタで、§4 と整合。

---

## 6. 残る限界と次の検証(v3 案)

1. **単一モデル問題**:本コーパスは Claude Opus 系のみ。「AI 一般の tell」と「Claude 固有の癖」(整理・ておきたい・地味・けれど の偏愛は Claude のトーン由来の可能性)が未分離。**v3 で GPT/Gemini 等を同一プロンプトで生成**し、モデル横断で残る tell だけを「AI 一般 tell」に昇格すべき。
2. **human 側 Markdown 欠如の根治**:現状最大の交絡は「human 4 ソース中 wiki/hatena/note の段落境界が抽出時に破壊」(qiita のみ保存、しかも qiita は AI と区別不能)。**human 側も Markdown 構造を保持して再収集**(あるいは AI 側を逆にプレーン化して両側を揃える)ことで、`\n\n`・段落長・見出し系を初めて公平に検証できる。現状これらは検証不能。
3. **PCA 寄与率の低さ**:Phase 4 の PCA 50 次元は累積寄与率 0.403。微細な言い換え差を取りこぼしている可能性。意味クラスタは全て低カバレッジ(18–26 doc)であり、min_cluster_size やクラスタリング手法を変えた感度分析が必要。
4. **register の明示的マッチング**:多くの語彙 tell(だけ・少し・という・のではないでしょうか)は register(AI=政体ブログ寄り, wiki=常体)を揃えると大幅に縮小する。v3 では **政体/常体を揃えた上での測定を標準化**し、wiki を分母にした見かけ倍率の報告を禁止する。
5. **DF 閾値の制度化**:em dash・はずです・のだろう・意味クラスタは DF < 12% の低カバレッジ。「high precision / low recall 信号」と「汎用 tell」を分けて報告する基準を設ける(本検証では DF 99% の文長均一性のみが真の汎用 tell)。
6. **集中度の正しい指標**:naive な「上位 5% 記事が >50% を占める」テストは zero-count 記事が 85% の状況で偽陽性を量産する。single-article max share / median nonzero count を標準とする(concentration-df アングルの方法論的貢献)。

---

*検証スクリプト群は各アングルの verdict に記載(/tmp/verify_*.py)。本レポートは findings.md (v1) を置き換えるものではなく、その各主張の信頼度を付与する査読層である。*

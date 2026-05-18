# methodology (v2)

このドキュメントは README §「アーキテクチャ」「クリーン側 corpus」「AI 側 corpus」「パターン抽出」を実装レベルで詳述する。判断の根拠と落とし穴対策に重点を置く。

## 0. v2 でのスコープ縮小

v1 (3 モデル投票) → v2 (Opus 4.7 単独 + CLI /loop 駆動 + Cloudflare スタック) への変更点:

| 観点 | v1 | v2 |
|---|---|---|
| AI 生成モデル | Opus 4.7 + GPT-5.5 + Gemini 2.1 | **Opus 4.7 のみ** |
| 生成手段 | Anthropic / OpenAI / Google SDK | **Claude Code `/loop` (CLI セッション)** |
| クロール | Python httpx + BeautifulSoup | **Cloudflare Browser Run (Worker)** |
| ストレージ | `data/*.json` | **Cloudflare D1** |
| 一般 tell の検出 | 3 モデル投票で 2/3 以上 | **不可** (Opus tell として扱う) |

スコープ縮小の正当化: API コスト 0 化と実装速度を優先。Opus 単独でも 1 モデル vs 1000 人間記事の差分は十分大きいので、まず「Opus tell」を確定し、後から Gemini/Codex を `ai_articles.model` 列追加で増設できる設計。

## 1. なぜこの設計か (動機は v1 から不変)

xmachine 側の `context/ja/jp-naturalness.md` にある AI tell 30 リストは出典がなく、検証も「人間が使わない」を 50 記事 corpus で測ったに留まる (n=50, 著者 31 名)。本リポジトリは:

1. クリーン側 1000 記事 (2022-06 以前の日本語、AI 汚染なし)
2. AI 側 1000 記事 (Opus 4.7 が同一トピックで生成)
3. 対数尤度比 + 効果量による統計検定

の 3 点で「**統計的に有意 / 効果量も大きい**」tell だけを採用する。

## 2. クリーン側 corpus サンプリング

| ソース | 目標 | 戦略 |
|---|---|---|
| Wikipedia 2021-12 dump | 400 | ランダム抽出。本文 1500 字以上、stub を除外 |
| はてなブログ 2018-2021 | 300 | `docs/seed_hatena_blogs.txt` のブログから `/archive/YYYY/MM` 巡回 |
| note 2018-2021 | 200 | `docs/seed_note_creators.txt` のクリエイター × 公開日フィルタ |
| Qiita 2015-2021 | 100 | タグ別最新 + いいね数 ≥ 5 で品質下限 |

### 落とし穴: ブログ体を意図的に多くする

Wikipedia だけで埋めると「百科事典 vs AI ブログ」の **domain 差** を AI tell と誤検出する。ブログ体 (敬体・常体混在) を 600/1000 で意図的に多めにする。

### SEO 系定型句の取り扱い

「結論から言うと」「いかがでしたか」など SEO ブログ定型句を含む clean 記事も意図的に含める。これにより AI tell と「形式的書き手 tell」を分離できる。

### Seed 選定方針

- 2018-2021 にコンスタントに投稿
- 個人の文体が出ているもの (企業オウンドメディアは除外)
- AI 汚染がないことを Wayback Machine で目視確認
- ジャンル: 旅行 / 育児 / 技術 / 読書 / エッセイ / 仕事 / 食 で散らす

## 3. AI 側 corpus 生成 (Claude Code /loop)

### 2 段階設計

**Phase 1: 要約生成 (`prompts` テーブル埋め)**
- 各 clean_article の冒頭 800 字を Opus に投げて 60-100 字の中立要約
- 要約自体に Opus tell が混入するが、prompt 部分は分析対象外なので OK

**Phase 2: 記事生成 (`ai_articles` テーブル埋め)**
- prompt (title + 要約) を Opus に投げて記事本文を生成
- これが分析対象

Phase 1 と Phase 2 は別々の `/loop` セッションで走らせる (依存関係順に Phase 1 → Phase 2)。

### プロンプト形式 (確定: (C) title + 一文要約)

```
以下のテーマで日本語の記事 (note / ブログ風) を書いてください。
タイトル: {title}
概要: {summary}
```

#### なぜ「続き生成」(A) でなく「title+summary」(C) か

clean 記事の冒頭そのままを渡すと AI が冒頭の文体に **同期** してしまい、AI tell が薄まる。title+summary 形式なら AI は自分のデフォルト文体で書き始める。

#### なぜ「title のみ」(B) でなく (C) か

title だけだと AI は一般論を書き、トピック粒度が clean と乖離する。一文要約を渡せばトピック内容は揃い、文体だけが純粋に比較できる。

### トーン指示・字数指示を入れない原則

「人間風に書け」「自然な日本語で」「AI 臭を消せ」「N 文字で書け」は **すべて禁止**。理由:

1. 現実の AI 利用シーンの大部分を反映しない (普通のユーザは指示を入れない)
2. 「人間風」プロンプトで生成した corpus を分析しても、得られるのは「人間風プロンプトで隠せない AI tell」であり、本来の AI tell より狭くなる
3. 字数指示で長さを揃えると、**冗長性そのものが AI tell** であるという事実を消してしまう

### /loop の駆動

`loop/claude_loop.md` に Claude Code セッションに貼り付ける /loop プロンプトを置く。実行手順:

```bash
# Phase 1
claude
> /loop --interval 30s
> (loop/claude_loop.md の Phase 1 プロンプトを貼る)

# Phase 2 (Phase 1 完了後)
claude  # 別セッション
> /loop --interval 60s
> (loop/claude_loop.md の Phase 2 プロンプトを貼る)
```

D1 アクセスは Claude Code セッション内の Bash で `wrangler d1 execute` を直接呼ぶ。

## 4. 統計的検定

### 採用閾値 (v1 から不変)

| 指標 | 閾値 | 根拠 |
|---|---|---|
| Log-Likelihood G² | > 15.13 | χ² 分布 df=1 で p < 0.0001 |
| Effect ratio | > 3.0 | 「3 倍以上 AI 側で出やすい」を minimum bar に |
| AI 側 raw count | ≥ 10 | 低頻度誤差を弾く |

G² + ratio の **AND 条件** を必須にする。

### n-gram スケール

- unigram (n=1): 単語レベル AI 臭 (抽象名詞の偏り)
- bigram (n=2): 句レベル (「することで」「という形で」)
- trigram (n=3): 定型表現 (「することができ」「重要なポイント」)
- char 4-gram tail: 文末パターン (「ましょう」「ですよね」)

### 単一モデル運用での留意点

v1 では「3/3 → 強い AI 一般 tell」と分類できたが、v2 ではこの段階分離ができない。検出 tell はすべて「**Opus 4.7 tell**」として扱う。将来モデル追加時:

```sql
ALTER TABLE ai_articles ADD COLUMN model TEXT;  -- 既に存在
-- 新モデル分を INSERT INTO ai_articles(model='gemini', ...);
-- 分析側で model 列で GROUP BY すれば多モデル比較が後から可能
```

### Phase 4: 言い換えクラスタ (embedding ベース)

surface n-gram で取れる tell は「同じ文字列で頻出する」型に限られる。実用上、AI には **同義言い換えの過剰生成** がある:

```
「結論として申し上げますと」
「結論を述べますと」
「結論を申し上げると」
「最終的に申し上げますと」
```

これらは個別の n-gram count が閾値割れだが、**意味的に同一クラスタを形成**する。 embedding 空間でクラスタリングすればこの種の tell が引っかかる。

**実装:**

1. 文単位埋め込み: Cloudflare Workers AI の `@cf/baai/bge-m3` (1024d, 多言語、日本語性能良好)
2. Worker `POST /embed/clean` `POST /embed/ai` がそれぞれの table から未処理を取って Workers AI に投げ、D1.sentence_embeddings BLOB に保存
3. D1 export 後、`scripts/analyze/cluster_paraphrases.py` が:
   - 全 sentence_embedding を numpy 配列に reconstitute
   - L2 正規化 → HDBSCAN (`min_cluster_size=10`) で euclidean クラスタリング (cosine 等価)
   - 各クラスタの AI/human 比 + lift を集計
   - AI ratio ≥ 75% かつ lift ≥ 3× のクラスタを抽出
   - 代表文 3 個 (centroid 最近傍) をサンプル付与
4. `extract_tells.py` が `ai_tells.json` の `paraphrase_tells` 列に merge

**閾値の根拠:**

| 閾値 | 値 | 理由 |
|---|---|---|
| min_cluster_size | 10 | HDBSCAN の noise を弾く下限。1000 記事 × 30 文 ≈ 30k 文に対する 0.03% |
| ai_ratio | ≥ 0.75 | クラスタの 3/4 以上が AI 側なら AI 偏向クラスタと判定 |
| lift | ≥ 3.0 | surface 側の ratio_thresh と整合 |

**注意:** embedding は文の意味を捉えるが **文体 (tone)** も部分的に拾うので、敬体/常体差や口語/文語差がクラスタ境界を作ることがある。clean corpus にブログ体・常体・SEO 系を意図的に散らすことで、ここでも domain artifact を緩和する (Phase 3 と同じ対策で済む)。

## 5. データフロー (v2)

```
Wikipedia 2021 dump (CC BY-SA)
        │
        ▼
[Cloudflare Worker: crawler] ──── Browser Run (hatena/note)
        │                               │
        │                               │
        ▼                               ▼
   D1.clean_articles  ◄──────────────────┘
        │
        ▼
[Claude Code /loop: Phase 1 summarize]
        │
        ▼
   D1.prompts
        │
        ▼
[Claude Code /loop: Phase 2 generate]
        │
        ▼
   D1.ai_articles
        │
        ▼
[Worker POST /embed/clean + /embed/ai] (Workers AI BGE-M3)
        │
        ▼
   D1.sentence_embeddings (BLOB)
        │
        ▼
[wrangler d1 export] ── data/d1_export/corpus.sqlite
        │
        ▼
[scripts/analyze/loglikelihood + sentence_endings + punctuation]   # Phase 3
[scripts/analyze/cluster_paraphrases]                              # Phase 4
        │
        ▼
[scripts/analyze/extract_tells]
        │
        ▼
   data/analysis/ai_tells.json
```

## 6. 落とし穴と対策

| 落とし穴 | 対策 |
|---|---|
| トピック交絡 | clean → prompt → AI で **同一 prompt** を 1:1 で投げる |
| 長さ偏差 | char_count を feature にする (truncate しない) |
| SEO 定型句混同 | SEO ブログを意図的に clean に含める |
| 敬体 / 常体差を AI tell と誤検出 | clean に常体 (Wikipedia) と敬体 (hatena/note) 両方含める |
| Opus 固有のクセを「AI 一般」と誤標榜 | v2 では「Opus tell」と明示。将来追加で検証 |
| /loop セッション中断時の重複生成 | `INSERT OR IGNORE` + `UNIQUE(prompt_id, model)` 制約 |
| Browser Run の rate limit | hatena/note は連続アクセス間 2 秒 sleep を Worker 内で実装 |
| Wikipedia dump サイズ | dump は R2 に置いて Worker から stream で読む (gitignore) |

## 7. xmachine への取り込み

完成した `data/analysis/ai_tells.json` は次の 3 列で xmachine 側 `context/ja/jp-naturalness.md` の AI tell リスト置換に使う:

- `pattern` (regex or n-gram)
- `evidence` (`per_1k_ai`, `per_1k_clean`, `G2`, `ratio`)
- `provenance` (`model='claude-opus-4-7'`, corpus_version)

旧 30 リストのうちエビデンスに残ったものは保持。残らなかったものは **削除** または **個人意見** タグで分離する。

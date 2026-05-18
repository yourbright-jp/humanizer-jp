# jp-ai-tells-corpus

エビデンスベースで「日本語 AI 臭」のパターンを抽出するためのコーパスと分析パイプライン。

## 目的

LLM (現スコープでは Claude Opus 4.7) が生成する日本語テキストに固有のパターン (AI tell) を、統計的に有意な差分として **実データから抽出する**。出典なしの手作業 regex リストではなく、対数尤度比 + 効果量を併記した一覧を出す。

成果物は xmachine の `context/ja/jp-naturalness.md` の AI tell リスト置換 / 補強として import される。

## アーキテクチャ (v2)

```
┌─────────────────────────┐         ┌────────────────────────┐
│ Cloudflare Browser Run  │         │ Claude Code /loop      │
│  - Wikipedia 2021 dump  │         │  - Opus 4.7 ヘッドレス │
│  - hatena 2018-2021     │  ──┐    │  - prompts を 1 件読み │
│  - note 2018-2021       │    │    │  - 記事生成           │
│  - Qiita 2015-2021      │    │    │  - 結果を ai_articles │
│                         │    │    │    に INSERT          │
└──────────┬──────────────┘    │    └───────────┬────────────┘
           │ INSERT            │                │ INSERT
           ▼                   │                ▼
        ┌──────────────────────▼───────────────────┐
        │           Cloudflare D1                  │
        │  clean_articles / prompts / ai_articles  │
        └──────────────────────┬───────────────────┘
                               │ wrangler d1 export
                               ▼
                       ┌───────────────────┐
                       │ scripts/analyze/  │
                       │  (Python, local)  │
                       └───────────────────┘
```

| Layer | 採用技術 | 備考 |
|---|---|---|
| クロール | Cloudflare Browser Run | Quick Actions HTTP API or Puppeteer-on-Workers |
| ストレージ | Cloudflare D1 | clean / prompts / ai_articles の 3 テーブル |
| AI 生成 | Claude Code (Opus 4.7) を `/loop` で起動 | API 直叩きはしない |
| 分析 | Python (D1 export → ローカル SQLite) | 既存の scripts/analyze/ を再利用 |

### v1 (API 直接) からの主な変更

| 観点 | v1 | v2 |
|---|---|---|
| 生成モデル | Opus 4.7 + GPT-5.5 + Gemini 2.1 (3 モデル投票) | **Opus 4.7 のみ** (スコープ縮小) |
| 生成手段 | Anthropic / OpenAI / Google SDK | Claude Code `/loop` (CLI セッション) |
| 収集手段 | Python httpx + BeautifulSoup | Cloudflare Browser Run |
| ストレージ | `data/*.json` | Cloudflare D1 |

スコープ縮小の帰結:
- 「3 モデル投票で AI 一般 tell vs モデル固有 tell」の分離は **不可**。検出される tell はすべて「Opus tell」として扱う (将来 Gemini/Codex を追加する余地は残す)
- API コストはほぼゼロ (Claude Code のサブスク枠を使う、Browser Run は無料枠 + 従量で月数百円程度)

## クリーン側 corpus (n = 1000)

ChatGPT 一般公開 (2022-11-30) 前の日本語テキストを集める。安全マージン込みで **2022-06 以前**。

| ソース | 文体 | 目標 | 取得手段 |
|---|---|---|---|
| Wikipedia 日本語版 2021-12 dump | 百科事典体 (常体) | 400 | Wikimedia 公式 dump → Browser Run の必要なし。Worker から R2 経由でロード |
| はてなブログ 2018-2021 | ブログ体 (敬体混在) | 300 | Browser Run Puppeteer (`/archive/YYYY/MM`) |
| note 2018-2021 | エッセイ体 (敬体) | 200 | Browser Run Puppeteer (creator page) |
| Qiita 2015-2021 | 技術ブログ (敬体) | 100 | Qiita API (JSON 直接、Browser Run 不要) |

ブログ体重視は意図的。Wikipedia だけだと「百科事典 vs AI ブログ」の domain 差を AI tell と誤検出する。SEO 系ブログも意図的に含めて「AI 固有 tell」と「形式的書き手 tell」を分離する。

## AI 側 corpus (n = 1000)

clean 側の各記事から **`title` + `一文要約`** を抽出して prompt 化 (採用方式 (C))。Claude Code セッションで `/loop` を起動し Opus 4.7 がそれを 1 件ずつ消化する。

### 2 段階 /loop

**Phase 1 (要約)**: `clean_articles` を読んで `prompts` を埋める
```
1. 未要約の clean_article を 1 件取得 (LEFT JOIN prompts WHERE p.id IS NULL LIMIT 1)
2. text の冒頭 800 字から 60-100 字の中立要約を生成
3. INSERT INTO prompts(id, source, title, summary, prompt, generated_at)
```

**Phase 2 (記事生成)**: `prompts` を読んで `ai_articles` を埋める
```
1. 未生成の prompt を 1 件取得 (LEFT JOIN ai_articles WHERE model='claude' AND a.id IS NULL LIMIT 1)
2. prompt 本文を Opus 4.7 が処理 → 日本語記事生成
3. INSERT INTO ai_articles(prompt_id, model='claude', text, char_count, generated_at)
```

### 生成プロンプト原則

```
以下のテーマで日本語の記事 (note / ブログ風) を書いてください。
タイトル: {title}
概要: {summary}
```

- 「人間風に書け」「AI 臭を消せ」「N 字で書け」などのトーン / 字数指示は **入れない**
- 素のデフォルト assistant トーンで生成する (これが現実に流通している AI 文体)
- 長さは feature 化する (truncate しない)

詳細は [docs/methodology.md](docs/methodology.md) と [loop/claude_loop.md](loop/claude_loop.md)。

## D1 スキーマ

`schemas/d1_schema.sql` に定義。3 テーブル:

- `clean_articles` — Browser Run で収集した human-written 原本
- `prompts` — clean_articles から導いた title + summary
- `ai_articles` — Claude Code /loop で生成した記事 (将来モデル追加時は `model` 列で識別)

## パターン抽出

### Phase 3: 頻度ベース統計 (surface パターン)

統計的有意性の閾値: **対数尤度比 G² > 15.13 (p < 0.0001)** + **AI 側頻度が human 側の 3 倍以上**。

| 観点 | 抽出単位 | スクリプト |
|---|---|---|
| 語彙 AI 臭 | unigram / bigram / trigram 頻度差 | `scripts/analyze/loglikelihood.py` |
| 文末パターン | 文末 4-char n-gram 分布 | `scripts/analyze/sentence_endings.py` |
| タイポグラフィ / 構造 | em dash / 三点リーダ / 段落長 / 漢字率 / 受身率 / 字数 | `scripts/analyze/punctuation.py` |

データソース: `wrangler d1 export jp-ai-tells --output corpus.sql` でローカルに pull → `sqlite3` で読む。Python 側は標準ライブラリ `sqlite3` で OK。

### Phase 4: 言い換えクラスタ (embedding ベース)

surface n-gram では検出できない **言い換え系 AI tell** (たとえば「結論として申し上げますと」「結論を述べますと」「最終的に申し上げますと」が個別には閾値割れだが意味的に同一クラスタ) を捕捉する。

| ステップ | 実装場所 |
|---|---|
| 文単位埋め込み生成 (BGE-M3, 1024d) | `crawler/src/embed.ts` — Worker `POST /embed/clean` `POST /embed/ai` |
| 埋め込み保存 | D1.sentence_embeddings (BLOB) |
| HDBSCAN クラスタリング + AI 偏向クラスタ抽出 | `scripts/analyze/cluster_paraphrases.py` |
| ai_tells.json への merge | `scripts/analyze/extract_tells.py` |

採用基準: cluster size ≥ 10、AI 比 ≥ 75%、lift ≥ 3×。各クラスタには centroid に近い代表文を 3 サンプル付与し、xmachine 側でそのまま「言い換え系 AI tell」として参照できる形式で出力する。

## ディレクトリ構造

```
jp-ai-tells-corpus/
├── README.md                          # 本ファイル
├── pyproject.toml
├── .env.example
├── .gitignore
├── docs/
│   ├── methodology.md                 # 詳細手法
│   ├── seed_hatena_blogs.txt          # (要 manual curation)
│   └── seed_note_creators.txt         # (要 manual curation)
├── schemas/
│   └── d1_schema.sql                  # D1 テーブル定義
├── crawler/                           # Cloudflare Worker (Browser Run + Workers AI + D1)
│   ├── wrangler.toml
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── index.ts                   # fetch handler + cron entry
│       ├── embed.ts                   # Phase 4: BGE-M3 文埋め込み
│       └── sources/
│           ├── wikipedia.ts
│           ├── hatena.ts
│           ├── note.ts
│           └── qiita.ts
├── loop/
│   └── claude_loop.md                 # Claude Code /loop プロンプト template
├── scripts/
│   └── analyze/
│       ├── _corpus.py                 # D1 export を読むラッパ
│       ├── loglikelihood.py           # Phase 3
│       ├── sentence_endings.py        # Phase 3
│       ├── punctuation.py             # Phase 3
│       ├── cluster_paraphrases.py     # Phase 4 (HDBSCAN)
│       └── extract_tells.py           # 全 phase の統合出力
└── data/
    └── d1_export/                     # wrangler d1 export 結果置き場 (gitignore)
```

## コスト見積もり

| 項目 | 内訳 | 金額 |
|---|---|---|
| Wikipedia 2021 dump 取得 | 1 回ダウンロード | 0 円 |
| Cloudflare Browser Run | ~600 記事 × ~5 秒 = 50 分 | 無料枠内 |
| Cloudflare D1 | < 200MB / 数百万 row | 無料枠内 |
| Workers AI (BGE-M3 embedding) | ~30k 文 × 1 call | $0.011 / 1k token (現価格) |
| Claude Code /loop (Opus 4.7) | サブスク枠で消化 | $0 (サブスク前提) |
| **合計** | | **~¥500 程度** |

## 成果物

1. `data/analysis/ai_tells.json` — エビデンス付き AI tell リスト (各項目に AI 側出現率 / human 側出現率 / log-likelihood / effect size を付与)
2. `docs/findings.md` — 抽出結果の human-readable サマリ

## 残作業 (次セッション以降)

1. **seed 手動キュレーション** — はてな 30-50 ブログ、note 20-30 クリエイター
2. **Cloudflare アカウント設定** — D1 / R2 / Browser Run / Workers AI 有効化 + wrangler init
3. **crawler Worker 実装** — sources/{wikipedia,hatena,note,qiita}.ts の中身
4. **/loop 起動 (Phase 1: 要約)** — `claude /loop` セッションで prompts テーブル埋める
5. **/loop 起動 (Phase 2: 記事生成)** — 同上で ai_articles 埋める
6. **Worker /embed/clean + /embed/ai** — Phase 4 の埋め込みを生成
7. **分析パイプライン** — D1 export → loglikelihood / sentence_endings / punctuation / cluster_paraphrases → extract_tells

## ライセンス

MIT (コード) / CC BY-SA (Wikipedia 由来データ) / 個別利用規約 (note/hatena/qiita)

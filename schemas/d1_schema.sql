-- jp-ai-tells-corpus D1 schema (v2)
--
-- Cloudflare D1 (SQLite-compatible). Apply with:
--   wrangler d1 execute jp-ai-tells --file schemas/d1_schema.sql
--   wrangler d1 execute jp-ai-tells --file schemas/d1_schema.sql --remote
--
-- 設計原則:
--   - id は decade-stable. clean_articles の元 URL の md5[:16] を使う
--   - prompts.id = clean_articles.id で 1:1 リンク
--   - ai_articles は (prompt_id, model) で UNIQUE。多モデル追加時は model 列で増やすだけ
--   - text は SQLite の TEXT 上限 (~1GB) なのでサイズは気にしない
--   - 全 timestamp は ISO 8601 文字列で統一 (SQLite に native datetime はない)

CREATE TABLE IF NOT EXISTS clean_articles (
    id           TEXT PRIMARY KEY,             -- md5(url)[:16]
    source       TEXT NOT NULL,                -- wikipedia | hatena | note | qiita
    url          TEXT NOT NULL,
    title        TEXT NOT NULL,
    text         TEXT NOT NULL,
    published_at TEXT NOT NULL,                -- ISO date "YYYY-MM-DD"
    char_count   INTEGER NOT NULL,
    crawled_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_clean_source ON clean_articles(source);
CREATE INDEX IF NOT EXISTS idx_clean_published ON clean_articles(published_at);

CREATE TABLE IF NOT EXISTS prompts (
    id           TEXT PRIMARY KEY,             -- = clean_articles.id
    source       TEXT NOT NULL,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,                -- 60-100 字の中立要約
    prompt       TEXT NOT NULL,                -- 「以下のテーマで...」の完成形
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (id) REFERENCES clean_articles(id)
);

CREATE TABLE IF NOT EXISTS ai_articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id    TEXT NOT NULL,
    model        TEXT NOT NULL,                -- claude | gemini | codex (現状 claude のみ)
    text         TEXT NOT NULL,
    char_count   INTEGER NOT NULL,
    meta         TEXT,                         -- JSON: { stop_reason, model_id, session_id, ... }
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(prompt_id, model),
    FOREIGN KEY (prompt_id) REFERENCES prompts(id)
);

CREATE INDEX IF NOT EXISTS idx_ai_model ON ai_articles(model);
CREATE INDEX IF NOT EXISTS idx_ai_prompt ON ai_articles(prompt_id);

-- Phase 4: 文単位埋め込み
--   source_table = 'clean_articles' | 'ai_articles'
--   source_id    = clean_articles.id (TEXT)
--                  or ai_articles.id を str 化 (両者を同じ列で扱う)
--   embedding    = float32 × 1024 (BGE-M3 出力) を ArrayBuffer として格納
--                  ※ D1 の BLOB 上限は 1MB だが 4KB なので余裕
--   model_id     = '@cf/baai/bge-m3' 等の Workers AI モデル ID
--
-- 後工程: Python の cluster_paraphrases.py が D1 export からこの BLOB を読み取り、
-- numpy で復元して HDBSCAN にかける。
CREATE TABLE IF NOT EXISTS sentence_embeddings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table  TEXT NOT NULL,                 -- 'clean_articles' | 'ai_articles'
    source_id     TEXT NOT NULL,
    sentence_idx  INTEGER NOT NULL,              -- 記事内の何文目か (0-origin)
    sentence_text TEXT NOT NULL,
    embedding     BLOB NOT NULL,                 -- Float32Array(1024) の ArrayBuffer
    model_id      TEXT NOT NULL,
    generated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_table, source_id, sentence_idx, model_id)
);

CREATE INDEX IF NOT EXISTS idx_emb_source ON sentence_embeddings(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_emb_model ON sentence_embeddings(model_id);

-- 進捗確認に便利な view
CREATE VIEW IF NOT EXISTS v_progress AS
SELECT
    (SELECT COUNT(*) FROM clean_articles)                                      AS clean_total,
    (SELECT COUNT(*) FROM clean_articles WHERE source = 'wikipedia')           AS clean_wikipedia,
    (SELECT COUNT(*) FROM clean_articles WHERE source = 'hatena')              AS clean_hatena,
    (SELECT COUNT(*) FROM clean_articles WHERE source = 'note')                AS clean_note,
    (SELECT COUNT(*) FROM clean_articles WHERE source = 'qiita')               AS clean_qiita,
    (SELECT COUNT(*) FROM prompts)                                             AS prompts_total,
    (SELECT COUNT(*) FROM ai_articles WHERE model = 'claude')                  AS ai_claude;

-- 次に処理すべき clean_article (Phase 1 用)
CREATE VIEW IF NOT EXISTS v_next_to_summarize AS
SELECT c.*
FROM clean_articles c
LEFT JOIN prompts p ON p.id = c.id
WHERE p.id IS NULL
ORDER BY c.crawled_at ASC;

-- 次に処理すべき prompt (Phase 2 用、model 別)
CREATE VIEW IF NOT EXISTS v_next_to_generate_claude AS
SELECT p.*
FROM prompts p
LEFT JOIN ai_articles a ON a.prompt_id = p.id AND a.model = 'claude'
WHERE a.id IS NULL
ORDER BY p.generated_at ASC;

-- Phase 4 用: 埋め込み未生成の clean_article
CREATE VIEW IF NOT EXISTS v_clean_to_embed AS
SELECT c.id, c.text
FROM clean_articles c
LEFT JOIN (
    SELECT DISTINCT source_id FROM sentence_embeddings
    WHERE source_table = 'clean_articles'
) e ON e.source_id = c.id
WHERE e.source_id IS NULL;

-- Phase 4 用: 埋め込み未生成の ai_article
CREATE VIEW IF NOT EXISTS v_ai_to_embed AS
SELECT a.id, a.text
FROM ai_articles a
LEFT JOIN (
    SELECT DISTINCT source_id FROM sentence_embeddings
    WHERE source_table = 'ai_articles'
) e ON e.source_id = CAST(a.id AS TEXT)
WHERE e.source_id IS NULL;

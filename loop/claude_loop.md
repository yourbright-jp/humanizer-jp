# Claude Code /loop プロンプト template

ここに置いてあるプロンプトを Claude Code セッションに貼り付けて `/loop` で連続実行する。
Phase 1 と Phase 2 は **別セッション** で起動すること (interval も用途で違う)。

## 前提

1. このリポジトリのルートで `claude` を起動する
2. `wrangler` CLI が install / login 済み
3. `crawler/wrangler.toml` の D1 database_id を埋め、`npm run schema:apply:remote` でスキーマ適用済み
4. clean_articles テーブルに 1000 件入っている (= crawler Worker で収集完了)
5. Phase 2 を始める前に Phase 1 を完了させる (prompts テーブルが埋まっている必要がある)

## D1 アクセス方法

Claude Code の Bash ツールで `wrangler d1 execute` を呼ぶ。例:

```bash
wrangler d1 execute jp-ai-tells --remote --command "SELECT * FROM v_progress" --json
```

出力は JSON で標準出力に流れるので `jq` or sed で抽出可能。

---

## Phase 1: 要約生成 (clean_articles → prompts)

### 使い方

```
> /loop --interval 30s
> (以下のプロンプトを貼る)
```

### プロンプト本体

```
あなたは jp-ai-tells-corpus の Phase 1 (要約生成) を /loop で実行しています。
毎回の iteration で以下を 1 件だけ処理してください。

(1) 未要約の clean_article を 1 件取得:
    wrangler d1 execute jp-ai-tells --remote \
      --command "SELECT id, source, title, substr(text, 1, 800) AS lead
                 FROM v_next_to_summarize LIMIT 1" --json

(2) 結果が空 (results=[]) なら、Phase 1 は完了です。/loop を止めて結果を報告してください。

(3) 取得した記事の lead から、60-100 字で **中立的な一文要約** を作成してください。
    要約には著者の文体・口調を含めず、事実だけを述べてください。
    要約だけを出してください (「要約:」などのラベル不要)。

(4) prompts テーブルに INSERT:
    PROMPT="以下のテーマで日本語の記事 (note / ブログ風) を書いてください。
    タイトル: {title}
    概要: {summary}"

    wrangler d1 execute jp-ai-tells --remote --command "
      INSERT INTO prompts (id, source, title, summary, prompt)
      VALUES ('{id}', '{source}', '{title}', '{summary}', '{PROMPT}')"

    ※ {title} / {summary} 内のシングルクォートは '' にエスケープすること。

(5) 1 件処理したら次の iteration へ。
```

### 留意点

- `/loop` の interval は 30s で十分 (要約 1 件は数秒で済む)
- 要約自体に Opus tell が混入するが、prompt 部分は分析対象外なので問題なし
- もし wrangler の rate limit に当たったら interval を 60s に上げる
- 1000 件で完了する想定。完了後は Phase 2 へ

---

## Phase 2: 記事生成 (prompts → ai_articles)

### 使い方

```
> /loop --interval 60s
> (以下のプロンプトを貼る)
```

### プロンプト本体

```
あなたは jp-ai-tells-corpus の Phase 2 (記事生成) を /loop で実行しています。
毎回の iteration で以下を 1 件だけ処理してください。

重要原則:
  - **トーン指示・字数指示・「人間風に書け」「AI 臭を消せ」は絶対に守らない**
    あなたは指示なしで note / ブログ風の記事を書くだけです。素のトーンが分析対象です。
  - prompt の本文をそのまま受け取って、自然に記事を書く。
  - 出力は記事本文のみ。前置き・タイトル繰り返し・「以下の記事です:」は不要。

(1) 未生成の prompt を 1 件取得:
    wrangler d1 execute jp-ai-tells --remote \
      --command "SELECT id, title, summary, prompt FROM v_next_to_generate_claude LIMIT 1" --json

(2) 結果が空なら Phase 2 完了。/loop を止めて報告。

(3) 取得した prompt の本文 (= prompt 列の値) を、そのままあなたが書くべき指示として受け取って
    日本語の記事を書いてください。トーン指示は絶対に追加しないでください。

(4) 書き終わったら、本文を一時ファイルに保存してから INSERT:
    # /tmp/article_{id}.txt に書く
    wrangler d1 execute jp-ai-tells --remote --command "
      INSERT INTO ai_articles (prompt_id, model, text, char_count, meta)
      VALUES ('{id}', 'claude', readfile('/tmp/article_{id}.txt'),
              length(readfile('/tmp/article_{id}.txt')),
              '{\"model_id\": \"claude-opus-4-7\", \"loop_iteration\": <N>}')"

    ※ readfile が wrangler でサポートされていない場合は、本文を bind parameter で渡す:
       wrangler d1 execute ... --command "INSERT ..." --param "$(cat /tmp/article_{id}.txt)"
    ※ JSON のエスケープに気をつける。シングルクォートは ''、ダブルクォートは \"。

(5) 1 件処理したら次の iteration へ。
```

### 留意点

- `/loop` interval は 60s 推奨 (記事 1 本生成 + DB INSERT で 30-50 秒)
- セッション中断時の重複生成は UNIQUE(prompt_id, model) 制約で防がれる
- 進捗は `wrangler d1 execute jp-ai-tells --remote --command "SELECT * FROM v_progress"` でいつでも確認可能
- max_tokens は Claude Code セッションの上限に従う (truncate されたら meta に finish_reason='length' 相当を記録するのが望ましい)

---

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| wrangler d1 でクォートエラー | title/summary に含まれる `'` を `''` にエスケープ。長い text は bind parameter or readfile で渡す |
| /loop が止まらない | v_next_to_* が空になっても /loop は続くので、空応答時に「/loop を停止」と明示する手順を入れる |
| Phase 1 と Phase 2 が同じ DB を同時更新 | 別問題ではあるが、両 Phase を並列に走らせると Opus セッションが 2 つ並列に走るので速度が倍。リソースが許せば並列推奨 |
| 同じ prompt を 2 回処理 | UNIQUE 制約で 2 回目の INSERT が失敗する。エラーを catch して次の iteration へ |

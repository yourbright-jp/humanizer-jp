"""分析スクリプトが共通で使う corpus 読み込み + トークナイザ。

データソース: D1 export を SQLite ファイルとしてローカルに pull したもの。
    wrangler d1 export jp-ai-tells --remote --output data/d1_export/corpus.sql
    sqlite3 data/d1_export/corpus.sqlite < data/d1_export/corpus.sql

または直接:
    wrangler d1 export jp-ai-tells --remote --no-schema --output data/d1_export/corpus.dump
    (json モードでも可、好みで)

このモジュールは sqlite3 ファイル想定。

corpus バケット定義:
    - clean        : clean_articles 全体
    - clean_wiki   : clean_articles WHERE source='wikipedia'
    - clean_blog   : clean_articles WHERE source IN ('hatena','note','qiita')
    - ai_claude    : ai_articles WHERE model='claude'

形態素トークナイザ: SudachiPy mode C。
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "d1_export" / "corpus.sqlite"
ANALYSIS_DIR = ROOT / "data" / "analysis"


def db_path() -> Path:
    """環境変数 CORPUS_DB_PATH で override 可能。"""
    env = os.environ.get("CORPUS_DB_PATH")
    return Path(env) if env else DEFAULT_DB


def connect() -> sqlite3.Connection:
    p = db_path()
    if not p.exists():
        raise FileNotFoundError(
            f"{p} not found. Run `wrangler d1 export jp-ai-tells --remote --output ...`"
            f" first, then `sqlite3 {p} < ...`."
        )
    return sqlite3.connect(p)


BUCKETS_SQL: dict[str, str] = {
    "clean": "SELECT text FROM clean_articles",
    "clean_wiki": "SELECT text FROM clean_articles WHERE source='wikipedia'",
    "clean_blog": "SELECT text FROM clean_articles WHERE source IN ('hatena','note','qiita')",
    "ai_claude": "SELECT text FROM ai_articles WHERE model='claude'",
}


def iter_text(bucket: str) -> Iterator[str]:
    if bucket not in BUCKETS_SQL:
        raise KeyError(f"unknown bucket: {bucket}. choose from {list(BUCKETS_SQL)}")
    with connect() as con:
        for (text,) in con.execute(BUCKETS_SQL[bucket]):
            if text:
                yield text


def iter_doc(bucket: str) -> Iterator[dict]:
    """記事 1 件分の dict を返す版 (id, title, text, char_count を含む)。"""
    if bucket == "clean":
        sql = "SELECT id, title, text, char_count FROM clean_articles"
    elif bucket == "clean_wiki":
        sql = "SELECT id, title, text, char_count FROM clean_articles WHERE source='wikipedia'"
    elif bucket == "clean_blog":
        sql = (
            "SELECT id, title, text, char_count FROM clean_articles "
            "WHERE source IN ('hatena','note','qiita')"
        )
    elif bucket == "ai_claude":
        sql = (
            "SELECT a.prompt_id AS id, p.title AS title, a.text AS text, a.char_count AS char_count "
            "FROM ai_articles a JOIN prompts p ON p.id = a.prompt_id WHERE a.model='claude'"
        )
    else:
        raise KeyError(bucket)
    with connect() as con:
        con.row_factory = sqlite3.Row
        for row in con.execute(sql):
            yield dict(row)


_tokenizer = None


def tokenize(text: str) -> list[str]:
    global _tokenizer
    if _tokenizer is None:
        from sudachipy import dictionary, tokenizer  # type: ignore

        _tokenizer = (dictionary.Dictionary().create(), tokenizer.Tokenizer.SplitMode.C)
    tok, mode = _tokenizer
    return [m.surface() for m in tok.tokenize(text, mode)]


def ngrams(tokens: Iterable[str], n: int) -> Iterator[tuple[str, ...]]:
    buf: list[str] = []
    for t in tokens:
        buf.append(t)
        if len(buf) > n:
            buf.pop(0)
        if len(buf) == n:
            yield tuple(buf)


def char_ngrams(text: str, n: int) -> Iterator[str]:
    for i in range(len(text) - n + 1):
        yield text[i : i + n]

-- Live source graph storage (plans/source-graph.md, phase 1 / D2).
-- Keyed by canonical domain, article URL and deterministic story key so re-running the same
-- input updates rows in place without changing counts.

CREATE TABLE graph_ingested_stories (
    story_key   TEXT PRIMARY KEY NOT NULL,
    updated_at  TEXT NOT NULL
) STRICT;

CREATE TABLE graph_outlets (
    domain         TEXT PRIMARY KEY NOT NULL,
    operator       TEXT NOT NULL,
    outlet_type    TEXT,
    country        TEXT,
    known_network  TEXT
) STRICT;

CREATE TABLE graph_articles (
    url           TEXT PRIMARY KEY NOT NULL,
    outlet        TEXT NOT NULL REFERENCES graph_outlets(domain) ON DELETE CASCADE,
    title         TEXT,
    published_at  TEXT,
    language      TEXT,
    analysed      INTEGER NOT NULL DEFAULT 0,
    fact_check    INTEGER NOT NULL DEFAULT 0,
    embedding     BLOB
) STRICT;

CREATE INDEX graph_articles_outlet ON graph_articles (outlet);

CREATE TABLE graph_article_ids (
    article_url  TEXT NOT NULL REFERENCES graph_articles(url) ON DELETE CASCADE,
    tracking_id  TEXT NOT NULL,
    kind         TEXT NOT NULL,
    PRIMARY KEY (article_url, tracking_id)
) STRICT;

CREATE INDEX graph_article_ids_tid ON graph_article_ids (tracking_id);

CREATE TABLE graph_article_links (
    article_url    TEXT NOT NULL REFERENCES graph_articles(url) ON DELETE CASCADE,
    source_outlet  TEXT NOT NULL,
    target_outlet  TEXT NOT NULL,
    story_key      TEXT NOT NULL,
    PRIMARY KEY (article_url, target_outlet)
) STRICT;

CREATE TABLE graph_ties (
    a         TEXT NOT NULL,
    b         TEXT NOT NULL,
    kind      TEXT NOT NULL,
    key_a     TEXT NOT NULL,
    key_b     TEXT NOT NULL,
    evidence  TEXT NOT NULL,
    PRIMARY KEY (a, b, kind, key_a, key_b)
) STRICT;

CREATE INDEX graph_ties_pair ON graph_ties (a, b);

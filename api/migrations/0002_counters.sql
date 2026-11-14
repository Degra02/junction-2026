-- Usage counters for GET /api/stats; they survive restarts, unlike in-memory counters.
CREATE TABLE counters (
    name   TEXT PRIMARY KEY NOT NULL,
    value  INTEGER NOT NULL
) STRICT;

INSERT INTO counters (name, value) VALUES ('submissions', 0), ('cache_hits', 0);

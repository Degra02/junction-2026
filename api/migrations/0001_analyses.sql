-- One row per analysis; the full record is stored as JSON (the contract type `Analysis`).
CREATE TABLE analyses (
    id          TEXT PRIMARY KEY NOT NULL,
    input_hash  TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    record      TEXT NOT NULL
) STRICT;

CREATE INDEX analyses_input_hash ON analyses (input_hash, created_at);
CREATE INDEX analyses_status ON analyses (status);

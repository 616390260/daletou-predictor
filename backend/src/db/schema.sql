-- 大乐透数据库 schema

CREATE TABLE IF NOT EXISTS draws (
    issue       TEXT PRIMARY KEY,
    draw_date   TEXT NOT NULL,
    front       TEXT NOT NULL,
    back        TEXT NOT NULL,
    sales       INTEGER DEFAULT 0,
    pool        INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_draws_date ON draws(draw_date);

CREATE TABLE IF NOT EXISTS predictions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    issue       TEXT NOT NULL,
    model       TEXT NOT NULL,
    ticket_idx  INTEGER NOT NULL,
    front       TEXT NOT NULL,
    back        TEXT NOT NULL,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(issue, model, ticket_idx)
);

CREATE INDEX IF NOT EXISTS idx_pred_issue ON predictions(issue);
CREATE INDEX IF NOT EXISTS idx_pred_model ON predictions(model);

CREATE TABLE IF NOT EXISTS results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    issue           TEXT NOT NULL,
    model           TEXT NOT NULL,
    ticket_idx      INTEGER NOT NULL,
    front_hit       INTEGER NOT NULL,
    back_hit        INTEGER NOT NULL,
    prize_level     TEXT,
    prize_amount    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(issue, model, ticket_idx)
);

CREATE INDEX IF NOT EXISTS idx_res_issue ON results(issue);
CREATE INDEX IF NOT EXISTS idx_res_model ON results(model);

-- QiymətRadar sxemi (init.sql yalnız boş bazada işləyir; db.migrate() də eyni cədvəlləri IF NOT EXISTS ilə yaradır)

CREATE TABLE IF NOT EXISTS scrape_runs (
    id SERIAL PRIMARY KEY,
    site TEXT NOT NULL,
    strategy TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'error', 'blocked')),
    items INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    seconds REAL NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    site TEXT NOT NULL,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    first_seen TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (site, slug)
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    run_id INTEGER NOT NULL REFERENCES scrape_runs(id),
    price NUMERIC(12, 2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'AZN',
    in_stock BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_snap_product ON price_snapshots (product_id, run_id);
CREATE INDEX IF NOT EXISTS idx_snap_run ON price_snapshots (run_id);

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    kind TEXT NOT NULL,                  -- pdf-text | pdf-scan | image | text
    method TEXT NOT NULL,                -- pypdf | ocr | given
    extractor TEXT NOT NULL,             -- regex | local | claude
    status TEXT NOT NULL CHECK (status IN ('ok', 'needs_review')),
    data JSONB NOT NULL DEFAULT '{}',
    issues JSONB NOT NULL DEFAULT '[]',
    text_chars INTEGER NOT NULL DEFAULT 0,
    seconds REAL NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    text TEXT NOT NULL,
    stats JSONB NOT NULL DEFAULT '{}',
    source TEXT NOT NULL,                -- claude | template
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id SERIAL PRIMARY KEY,
    label TEXT NOT NULL,
    summary JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

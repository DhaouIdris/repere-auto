CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE listings(
 id TEXT PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL,
 group_id TEXT NOT NULL, duplicate_basis TEXT NOT NULL,
 price_cents INTEGER CHECK(price_cents IS NULL OR price_cents>0),
 payload TEXT NOT NULL CHECK(json_valid(payload)),
 rights_reference TEXT NOT NULL,
 first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, last_price_change TEXT,
 UNIQUE(source,source_id)
);
CREATE INDEX group_idx ON listings(group_id);
CREATE TABLE price_history(
 event_id INTEGER PRIMARY KEY, listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
 observed_at TEXT NOT NULL, price_cents INTEGER NOT NULL CHECK(price_cents>0)
);
CREATE TABLE searches(
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
 filters TEXT NOT NULL CHECK(json_valid(filters)), created_at TEXT NOT NULL
);
CREATE TABLE source_status(
 source TEXT PRIMARY KEY,last_attempt TEXT,last_success TEXT,imported INTEGER NOT NULL DEFAULT 0,
 failures INTEGER NOT NULL DEFAULT 0,last_error TEXT
);
CREATE TABLE outbox(
 id TEXT PRIMARY KEY, search_id TEXT NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
 group_id TEXT NOT NULL, event_key TEXT NOT NULL,
 payload TEXT NOT NULL CHECK(json_valid(payload)),
 state TEXT NOT NULL CHECK(state IN ('pending','inflight','sent','failed')),
 attempts INTEGER NOT NULL DEFAULT 0, due_at TEXT NOT NULL, created_at TEXT NOT NULL,
 lease_until TEXT, sent_at TEXT, last_error TEXT,
 UNIQUE(search_id,group_id,event_key)
);
CREATE INDEX outbox_due_idx ON outbox(state,due_at);
CREATE TABLE metrics(key TEXT PRIMARY KEY,value INTEGER NOT NULL DEFAULT 0);
CREATE TABLE login_attempts(client TEXT PRIMARY KEY,window INTEGER NOT NULL,count INTEGER NOT NULL);

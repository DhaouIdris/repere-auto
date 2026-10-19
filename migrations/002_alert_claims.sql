ALTER TABLE outbox RENAME TO outbox_v1;
DROP INDEX outbox_due_idx;
CREATE TABLE outbox(
 id TEXT PRIMARY KEY, search_id TEXT NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
 group_id TEXT NOT NULL, event_key TEXT NOT NULL,
 payload TEXT NOT NULL CHECK(json_valid(payload)),
 state TEXT NOT NULL CHECK(state IN ('pending','inflight','sent','failed','cancelled')),
 attempts INTEGER NOT NULL DEFAULT 0, due_at TEXT NOT NULL, created_at TEXT NOT NULL,
 lease_until TEXT, sent_at TEXT, last_error TEXT, lease_token TEXT,
 UNIQUE(search_id,group_id,event_key)
);
INSERT INTO outbox(id,search_id,group_id,event_key,payload,state,attempts,due_at,created_at,lease_until,sent_at,last_error)
SELECT id,search_id,group_id,event_key,payload,
 CASE WHEN state='inflight' THEN 'failed' ELSE state END,
 attempts,due_at,created_at,NULL,sent_at,
 CASE WHEN state='inflight' THEN 'Migration : résultat de livraison ambigu, contrôle manuel requis' ELSE last_error END
FROM outbox_v1;
DROP TABLE outbox_v1;
CREATE INDEX outbox_due_idx ON outbox(state,due_at);

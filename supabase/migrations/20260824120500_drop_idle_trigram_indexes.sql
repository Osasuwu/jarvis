-- Osasuwu/jarvis#1645 — drop the two trigram indexes the planner never picks.
--
-- Both existed only in the live database; neither was ever declared in
-- mcp-memory/schema.sql, so this migration also closes that drift for the one
-- index worth keeping.
--
--   idx_memories_content_trgm      12 MB       3 lifetime scans  -> drop
--   idx_memories_description_trgm  2.4 MB      7 lifetime scans  -> drop
--   idx_memories_name_trgm         1.2 MB  3,161 lifetime scans  -> KEEP
--
-- The two dropped indexes were meant to serve the `ilike` fallback branch of
-- recall (mcp-memory/handlers/memory.py), but a sequential scan over 680 pages
-- is cheaper than a GIN probe on this table, so the planner never chose them.
-- They still paid full insert cost on all 124k UPDATEs. The `name` index is
-- left in place precisely because the planner does choose it.
--
-- CONCURRENTLY is deliberately not used: it cannot run inside the transaction
-- the migration runner wraps around this file, and these indexes are 12 MB and
-- 2.4 MB on a 149 MB database — the ACCESS EXCLUSIVE lock is momentary.
--
-- Revert:
--   create index idx_memories_content_trgm on memories using gin(content gin_trgm_ops);
--   create index idx_memories_description_trgm on memories using gin(description gin_trgm_ops);

drop index if exists idx_memories_content_trgm;
drop index if exists idx_memories_description_trgm;

-- Declared here so a fresh instance built from migration history gets the one
-- trigram index that carries its weight.
create extension if not exists pg_trgm;
create index if not exists idx_memories_name_trgm on memories using gin(name gin_trgm_ops);

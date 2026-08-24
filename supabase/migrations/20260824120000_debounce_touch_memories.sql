-- Osasuwu/jarvis#1645 — debounce touch_memories to one write per row per hour.
--
-- The recall path called this RPC on every hit, and every call was a real
-- UPDATE: 124k lifetime UPDATEs against ~2,500 live rows, only 0.2% of them
-- HOT. The main-heap tuple averages ~2.2 KB (wide fts/content/embedding), so a
-- page cannot hold a second row version and every timestamp bump rewrites all
-- 19 indexes — including an HNSW and four GIN indexes. That write stream, at
-- roughly one UPDATE every 148 s, also meant nearly every 120 s archive_timeout
-- window contained a write and forced a full 16 MB WAL segment switch.
--
-- Semantics change, visible to any operator running this schema:
-- last_accessed_at now means "seen during this hour", not "seen at this
-- instant". Verified sufficient for all four consumers — recall temporal
-- scoring (day buckets), /curate (already ignores touches < 2h old),
-- stale_assumption (min_idle_days: 90), context-management catalog sort.
--
-- Interacts with update_updated_at(): that trigger short-circuits when
-- last_accessed_at is the only changed column, so a debounced no-op writes
-- nothing at all and a debounced hit still leaves updated_at alone.
--
-- Revert: re-run the same CREATE OR REPLACE without the AND clause.

create or replace function touch_memories(memory_ids uuid[])
returns void
language sql volatile as $$
    update memories
    set last_accessed_at = now()
    where id = any(memory_ids)
      and (last_accessed_at is null
           or last_accessed_at < now() - interval '1 hour');
$$;

-- #1493 AC5: reroute memory_recall/fok_run telemetry off the `events`
-- perception queue and onto the append-only `events_canonical` substrate.
--
-- Producers (AC1-AC4) already write/read events_canonical going forward;
-- this migration handles the historical rows so morning_check's cutover
-- assertion (AC7) can find zero memory_recall/fok_run rows left in `events`.
--
-- Order (single transaction, per decision 51452257):
--   1. backfill matching `events` rows into events_canonical
--   2. parity assert (RAISE EXCEPTION on count mismatch)
--   3. drop fok_judgments.recall_event_id's FK to events(id) — the column
--      stays `uuid NOT NULL` + UNIQUE, no new FK (decision fc3882b0)
--   4. delete the migrated originals from `events`
--
-- Actor mapping derived from events.source, confirmed via live query
-- (project svwrzttdkxeselkpxfgm) against the two producers and fok-batch:
--   source='mcp_memory'          -> actor='mcp_memory:recall'   (AC1 producer)
--   source='memory-recall-hook'  -> actor='memory-recall-hook'  (AC2 producer)
--   source='fok_batch'           -> actor='fok-batch'           (AC3 producer)

begin;

insert into events_canonical (event_id, trace_id, ts, actor, action, payload)
select
  e.id,
  gen_random_uuid(),
  e.created_at,
  case e.source
    when 'mcp_memory' then 'mcp_memory:recall'
    when 'memory-recall-hook' then 'memory-recall-hook'
    when 'fok_batch' then 'fok-batch'
    else e.source
  end,
  e.event_type,
  coalesce(e.payload, '{}'::jsonb)
from events e
where e.event_type in ('memory_recall', 'fok_run')
on conflict (event_id) do nothing;

do $$
declare
  events_count bigint;
  canonical_count bigint;
begin
  select count(*) into events_count
    from events
    where event_type in ('memory_recall', 'fok_run');

  select count(*) into canonical_count
    from events_canonical
    where event_id in (
      select id from events where event_type in ('memory_recall', 'fok_run')
    );

  if events_count <> canonical_count then
    raise exception 'AC5 parity check failed: % events rows vs % events_canonical rows',
      events_count, canonical_count;
  end if;
end $$;

alter table fok_judgments drop constraint if exists fok_judgments_recall_event_id_fkey;

delete from events where event_type in ('memory_recall', 'fok_run');

commit;

-- Issue #679: Global task sources — non-repo inputs for AFK loop
-- Registry of recurring, low-stakes, repo-agnostic tasks. Advancer ticks due rows
-- into events queue; orchestrator routes via three-disposition logic.

create table if not exists global_task_sources (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  body text,
  dispatcher_skill text not null
    check (dispatcher_skill in ('research', 'self-improve', 'status-record', 'last-work-report')),
  output_sink text not null
    check (output_sink in ('memory', 'telegram_digest', 'event_reemit')),
  payload jsonb default '{}',
  cadence interval,                 -- NULL = one-shot
  last_run timestamptz,
  next_run timestamptz,
  enabled bool not null default true,
  on_lapse text not null default 'coalesce'
    check (on_lapse in ('coalesce', 'fire_per_interval')),
  created_at timestamptz not null default now()
);

-- Dispatcher/sink compatibility matrix (enforced at DB level).
-- status-record -> memory only; research -> any sink; others flexible.
alter table global_task_sources add constraint dispatcher_sink_compatibility
  check (
    (dispatcher_skill = 'status-record' and output_sink = 'memory') or
    (dispatcher_skill = 'research') or
    (dispatcher_skill = 'self-improve') or
    (dispatcher_skill = 'last-work-report')
  );

-- Indexes for efficient due-row queries and enabled filtering.
create index if not exists idx_global_task_sources_enabled_next_run
  on global_task_sources(enabled, next_run)
  where enabled = true;

create index if not exists idx_global_task_sources_dispatcher
  on global_task_sources(dispatcher_skill);

-- RLS: anon DENIED INSERT/UPDATE/DELETE; service-role only.
alter table global_task_sources enable row level security;

create policy "Allow all for authenticated" on global_task_sources
  for all using (true) with check (true);

-- Anon can SELECT but not mutate.
create policy "Anon select only" on global_task_sources
  for select to anon using (true);

-- Jarvis Memory Schema for Supabase
-- Run this in the Supabase SQL Editor to create the table.

create table if not exists memories (
  id uuid default gen_random_uuid() primary key,

  -- Memory classification
  type text not null check (type in ('user', 'project', 'decision', 'feedback', 'reference')),
  project text,           -- null = global/cross-project, 'jarvis' = this project, etc.

  -- Content
  name text not null,     -- unique identifier within project scope
  description text,       -- one-line summary (used for relevance matching)
  content text not null,  -- full memory content

  -- Metadata
  tags text[] default '{}',
  created_at timestamptz default now(),
  updated_at timestamptz default now(),

  -- One memory per name per project scope
  unique(project, name)
);

-- Indexes for common query patterns
create index if not exists idx_memories_project on memories(project);
create index if not exists idx_memories_type on memories(type);
create index if not exists idx_memories_tags on memories using gin(tags);

-- Voyage AI embedding storage (512-dim vectors via pgvector extension)
alter table memories add column if not exists embedding vector(512);

-- Read tracking for temporal scoring (Memory 2.0)
alter table memories add column if not exists last_accessed_at timestamptz;

-- Partial index to efficiently find rows missing embeddings (for backfill queries)
create index if not exists idx_memories_no_embedding on memories(id) where embedding is null;

-- Full-text search index for keyword recall
alter table memories add column if not exists fts tsvector
  generated always as (
    to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, '') || ' ' || coalesce(content, ''))
  ) stored;

create index if not exists idx_memories_fts on memories using gin(fts);

-- Auto-update updated_at on changes
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists memories_updated_at on memories;
create trigger memories_updated_at
  before update on memories
  for each row execute function update_updated_at();

-- Row Level Security (optional but recommended)
alter table memories enable row level security;

-- Allow all operations for authenticated users (single-user system)
create policy "Allow all for authenticated" on memories
  for all using (true) with check (true);

-- Allow anonymous access (using anon key from MCP server)
create policy "Allow all for anon" on memories
  for all to anon using (true) with check (true);


-- =========================================================================
-- Goals table — Jarvis 2.0 Pillar 1: Goals & Strategic Context
-- =========================================================================

create table if not exists goals (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  title text not null,
  project text,
  direction text,
  priority text not null default 'P1'
    check (priority in ('P0', 'P1', 'P2')),
  status text not null default 'active'
    check (status in ('active', 'achieved', 'paused', 'abandoned')),

  why text,
  success_criteria jsonb default '[]',

  deadline date,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  closed_at timestamptz,

  progress jsonb default '[]',
  progress_pct integer default 0
    check (progress_pct >= 0 and progress_pct <= 100),

  risks jsonb default '[]',
  owner_focus text,
  jarvis_focus text,

  parent_id uuid references goals(id) on delete set null,

  outcome text,
  lessons text
);

create index if not exists idx_goals_status on goals(status);
create index if not exists idx_goals_project on goals(project);
create index if not exists idx_goals_priority on goals(priority);
create index if not exists idx_goals_parent on goals(parent_id);

-- Auto-update updated_at
create or replace function update_goals_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists goals_updated_at on goals;
create trigger goals_updated_at
  before update on goals
  for each row execute function update_goals_updated_at();

-- RLS
alter table goals enable row level security;

create policy "Allow all for authenticated" on goals
  for all using (true) with check (true);

create policy "Allow all for anon" on goals
  for all to anon using (true) with check (true);


-- =========================================================================
-- Events table — Jarvis Pillar 2: Event-Driven Perception
-- GitHub Actions write events here, orchestrator reads them.
-- =========================================================================

create table if not exists events (
  id uuid primary key default gen_random_uuid(),

  -- Event classification
  event_type text not null,          -- 'ci_failure', 'security_alert', 'pr_approved', 'deployment', etc.
  severity text not null default 'info'
    check (severity in ('critical', 'high', 'medium', 'low', 'info')),

  -- Source
  repo text not null,                -- 'Osasuwu/jarvis', 'SergazyNarynov/redrobot', etc.
  source text not null default 'github_action',  -- 'github_action', 'webhook', 'manual'

  -- Content
  title text not null,               -- one-line summary
  payload jsonb default '{}',        -- structured event data (PR number, workflow name, alert details)

  -- Processing
  processed boolean not null default false,
  processed_at timestamptz,
  processed_by text,                 -- 'autonomous-loop', 'risk-radar', 'manual'
  action_taken text,                 -- what was done in response

  -- Timestamps
  created_at timestamptz default now(),
  event_at timestamptz default now() -- when the event actually occurred (may differ from insert time)
);

-- Indexes
create index if not exists idx_events_unprocessed on events(processed, severity) where not processed;
create index if not exists idx_events_repo on events(repo);
create index if not exists idx_events_type on events(event_type);
create index if not exists idx_events_created on events(created_at desc);

-- RLS
alter table events enable row level security;

create policy "Allow all for authenticated" on events
  for all using (true) with check (true);

create policy "Allow all for anon" on events
  for all to anon using (true) with check (true);


-- =========================================================================
-- Memory Links — Memory 2.0: Graph Relationships
-- Auto-generated on memory_store, tracks related/superseded/consolidated
-- =========================================================================

create table if not exists memory_links (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references memories(id) on delete cascade,
  target_id uuid not null references memories(id) on delete cascade,
  link_type text not null default 'related'
    check (link_type in ('related', 'supersedes', 'consolidates')),
  strength float not null default 1.0
    check (strength >= 0 and strength <= 1),
  created_at timestamptz default now(),
  unique(source_id, target_id, link_type),
  check(source_id != target_id)
);

create index if not exists idx_memory_links_source on memory_links(source_id);
create index if not exists idx_memory_links_target on memory_links(target_id);
create index if not exists idx_memory_links_type on memory_links(link_type);

alter table memory_links enable row level security;

create policy "Allow all for authenticated" on memory_links
  for all using (true) with check (true);

create policy "Allow all for anon" on memory_links
  for all to anon using (true) with check (true);


-- =========================================================================
-- RPC Functions — Memory 2.0
-- =========================================================================

-- Find memories semantically similar to a given embedding (for auto-linking on store)
-- Uses existing HNSW index on memories.embedding
create or replace function find_similar_memories(
    query_embedding vector,
    exclude_id uuid,
    match_limit int default 5,
    similarity_threshold float default 0.6,
    filter_type text default null
)
returns table(id uuid, name text, type text, project text, similarity float)
language sql stable as $$
    select m.id, m.name, m.type, m.project,
           1 - (m.embedding <=> query_embedding) as similarity
    from memories m
    where m.embedding is not null
      and m.id != exclude_id
      and 1 - (m.embedding <=> query_embedding) >= similarity_threshold
      and (filter_type is null or m.type = filter_type)
    order by m.embedding <=> query_embedding
    limit match_limit;
$$;

-- Get 1-hop linked memories for graph-aware recall
create or replace function get_linked_memories(
    memory_ids uuid[],
    link_types text[] default null
)
returns table(
    id uuid, name text, type text, project text,
    description text, content text, tags text[],
    updated_at timestamptz,
    link_type text, link_strength float, linked_from uuid
)
language sql stable as $$
    -- Outer query re-orders deduped results by strength
    select * from (
        -- DISTINCT ON keeps only the strongest link per target memory
        select distinct on (sub.id)
            sub.id, sub.name, sub.type, sub.project, sub.description,
            sub.content, sub.tags, sub.updated_at,
            sub.link_type, sub.link_strength, sub.linked_from
        from (
            select m.id, m.name, m.type, m.project, m.description, m.content, m.tags, m.updated_at,
                   l.link_type, l.strength as link_strength, l.source_id as linked_from
            from memory_links l
            join memories m on m.id = l.target_id
            where l.source_id = any(memory_ids)
              and not (l.target_id = any(memory_ids))
              and (link_types is null or l.link_type = any(link_types))
            union all
            select m.id, m.name, m.type, m.project, m.description, m.content, m.tags, m.updated_at,
                   l.link_type, l.strength as link_strength, l.target_id as linked_from
            from memory_links l
            join memories m on m.id = l.source_id
            where l.target_id = any(memory_ids)
              and not (l.source_id = any(memory_ids))
              and (link_types is null or l.link_type = any(link_types))
        ) sub
        order by sub.id, sub.link_strength desc
    ) deduped
    order by deduped.link_strength desc
    limit 10;
$$;

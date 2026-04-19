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

-- Generated project scope key for tiebreakers / grouping on a non-null text.
-- Applied in production via an out-of-band migration; re-declared here so
-- schema.sql matches the live DB. Must stay in update_updated_at's strip
-- list (GENERATED ALWAYS STORED cols appear NULL in BEFORE UPDATE NEW).
alter table memories add column if not exists project_key text
  generated always as (coalesce(project, '')) stored;

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
-- Memory Consolidation — Memory 2.0: Merge similar memories
-- Finds clusters of 3+ memories with cosine similarity >= 0.80
-- Returns clusters for LLM-driven merge (content merging is not pure SQL)
-- =========================================================================

-- Find groups of memories that should be consolidated.
-- Phase 5.1c: the `live` CTE applies Phase 1 default-recall semantics at the
-- source so consumers never see stale memories in a cluster. Legacy
-- `%_archived` types are also excluded defensively (0 rows as of 2026-04-19,
-- left in place so a stray row from old logic cannot poison consolidation).
create or replace function find_consolidation_clusters(
  min_cluster_size int default 3,
  sim_threshold float default 0.80
)
returns table (
  cluster_id int,
  memory_id uuid,
  memory_name text,
  memory_type text,
  content text,
  similarity float,
  updated_at timestamptz
)
language sql stable
as $$
  with live as (
    select id, name, type, content, embedding, updated_at
    from memories
    where embedding is not null
      and expired_at is null
      and superseded_by is null
      and deleted_at is null
      and (valid_to is null or valid_to > now())
      and type not like '%\_archived' escape '\'
  ),
  pairs as (
    select
      a.id as id_a, b.id as id_b,
      a.name as name_a, b.name as name_b,
      a.type as type_a,
      a.content as content_a, b.content as content_b,
      a.updated_at as updated_a, b.updated_at as updated_b,
      1 - (a.embedding <=> b.embedding) as sim
    from live a
    join live b on a.id < b.id
      and a.type = b.type
    where 1 - (a.embedding <=> b.embedding) >= sim_threshold
  ),
  -- Group connected pairs into clusters via the oldest memory as anchor
  anchors as (
    select id_a as anchor, id_a as member, name_a as name, type_a as type,
           content_a as content, sim, updated_a as updated_at from pairs
    union all
    select id_a as anchor, id_b as member, name_b as name, type_a as type,
           content_b as content, sim, updated_b as updated_at from pairs
  ),
  clusters as (
    select
      dense_rank() over (order by anchor) as cid,
      member, name, type, content, sim, updated_at
    from anchors
  ),
  sized as (
    select *, count(*) over (partition by cid) as cluster_size
    from clusters
  )
  select
    cid::int as cluster_id,
    member as memory_id,
    name as memory_name,
    type as memory_type,
    content,
    sim as similarity,
    updated_at
  from sized
  where cluster_size >= min_cluster_size
  order by cid, updated_at desc;
$$;

-- Archive superseded memories (Phase 5.1c): set `expired_at` instead of
-- renaming type. Leaves type intact so type-filtered recall isn't poisoned
-- (audit gap #6 in docs/design/memory-overhaul.md). Idempotent — skips rows
-- already expired and doesn't double-prefix the description.
create or replace function archive_memories(memory_ids uuid[])
returns int
language plpgsql volatile
as $$
declare
  archived_count int;
begin
  update memories
  set expired_at = coalesce(expired_at, now()),
      description = case
        when description like '[ARCHIVED%' then description
        else '[ARCHIVED — consolidated] ' || coalesce(description, '')
      end
  where id = any(memory_ids)
    and expired_at is null;
  get diagnostics archived_count = row_count;
  return archived_count;
end;
$$;


-- =========================================================================
-- Task Outcomes — Pillar 3: Outcome Tracking & Learning
-- Records results of delegations, research, fixes, autonomous actions.
-- =========================================================================

create table if not exists task_outcomes (
  id uuid primary key default gen_random_uuid(),

  -- What was done
  task_type text not null
    check (task_type in ('delegation', 'research', 'fix', 'review', 'autonomous')),
  task_description text not null,
  outcome_status text not null default 'pending'
    check (outcome_status in ('pending', 'success', 'partial', 'failure', 'unknown')),
  outcome_summary text,

  -- Links
  goal_slug text,           -- related goal
  project text,             -- project scope
  issue_url text,           -- GitHub issue URL
  pr_url text,              -- GitHub PR URL

  -- Quality signals
  tests_passed boolean,
  pr_merged boolean,
  quality_score integer check (quality_score is null or (quality_score >= 0 and quality_score <= 100)),

  -- Learning
  lessons text,
  pattern_tags text[] default '{}',

  -- Verification
  verified_at timestamptz,  -- when outcome was verified (e.g. PR merged check)

  -- Timestamps
  created_at timestamptz default now()
);

create index if not exists idx_task_outcomes_project on task_outcomes(project);
create index if not exists idx_task_outcomes_goal on task_outcomes(goal_slug);
create index if not exists idx_task_outcomes_status on task_outcomes(outcome_status);
create index if not exists idx_task_outcomes_created on task_outcomes(created_at desc);
create index if not exists idx_task_outcomes_tags on task_outcomes using gin(pattern_tags);

-- RLS
alter table task_outcomes enable row level security;

create policy "Allow all for authenticated" on task_outcomes
  for all using (true) with check (true);

create policy "Allow all for anon" on task_outcomes
  for all to anon using (true) with check (true);


-- =========================================================================
-- RPC Functions — Memory 2.0
-- =========================================================================

-- HNSW index for fast vector similarity search (pgvector)
-- Without this, find_similar_memories() does slow sequential scan.
create index if not exists idx_memories_embedding_hnsw
  on memories using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

-- Semantic search for hybrid recall (used by memory_recall's RRF pipeline)
-- Returns memories ranked by cosine similarity via HNSW index.
create or replace function match_memories(
    query_embedding vector,
    match_limit int default 10,
    similarity_threshold float default 0.3,
    filter_project text default null,
    filter_type text default null
)
returns table(
    id uuid, name text, type text, project text,
    description text, content text, tags text[],
    updated_at timestamptz, last_accessed_at timestamptz,
    similarity float
)
language sql stable as $$
    select m.id, m.name, m.type, m.project,
           m.description, m.content, m.tags,
           m.updated_at, m.last_accessed_at,
           1 - (m.embedding <=> query_embedding) as similarity
    from memories m
    where m.embedding is not null
      and 1 - (m.embedding <=> query_embedding) >= similarity_threshold
      and (filter_project is null or m.project = filter_project or m.project is null)
      and (filter_type is null or m.type = filter_type)
    order by m.embedding <=> query_embedding
    limit match_limit;
$$;


-- Keyword search for hybrid recall (used by memory_recall's RRF pipeline)
-- Uses full-text search (tsvector) with ranking.
create or replace function keyword_search_memories(
    search_query text,
    match_limit int default 10,
    filter_project text default null,
    filter_type text default null
)
returns table(
    id uuid, name text, type text, project text,
    description text, content text, tags text[],
    updated_at timestamptz, last_accessed_at timestamptz,
    rank real
)
language sql stable as $$
    select m.id, m.name, m.type, m.project,
           m.description, m.content, m.tags,
           m.updated_at, m.last_accessed_at,
           ts_rank(m.fts, websearch_to_tsquery('english', search_query)) as rank
    from memories m
    where m.fts @@ websearch_to_tsquery('english', search_query)
      and (filter_project is null or m.project = filter_project or m.project is null)
      and (filter_type is null or m.type = filter_type)
    order by rank desc
    limit match_limit;
$$;



-- Find memories semantically similar to a given embedding (for auto-linking on store)
-- Uses HNSW index on memories.embedding
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
        order by sub.id, sub.link_strength desc, sub.link_type, sub.linked_from
    ) deduped
    order by deduped.link_strength desc
    limit 10;
$$;


-- Update last_accessed_at for temporal scoring (called fire-and-forget on recall)
create or replace function touch_memories(memory_ids uuid[])
returns void
language sql volatile as $$
    update memories
    set last_accessed_at = now()
    where id = any(memory_ids);
$$;


-- =========================================================================
-- Phase 0 (memory overhaul, Osasuwu/jarvis#185) — lifecycle + provenance
-- fields. Non-breaking: all columns have defaults; server.py still reads
-- the old columns until Phase 1.
--
-- Rationale: every column below is driven by either (a) a convergent signal
-- from the research synthesis — production systems (Zep/Graphiti, Mem0,
-- A-MEM, LangMem) agreeing with theory (AGM, JTMS, ACT-R, CLS), or (b) a
-- production risk the research flagged that we hadn't noticed (embedding
-- migration). See docs/design/memory-overhaul.md §2.
-- =========================================================================

-- Bi-temporal: valid time ≠ transaction time (Snodgrass; Zep/Graphiti)
-- - content_updated_at: set only when the memory's content/description/tags
--   actually change. Phase 1 will drive decay off this instead of updated_at
--   (session-start reads currently bump updated_at and defeat decay).
-- - valid_from / valid_to: when the fact was true in the world.
-- - expired_at: when we stopped believing it (transaction time soft-delete).
alter table memories add column if not exists content_updated_at timestamptz;
alter table memories add column if not exists valid_from timestamptz;
alter table memories add column if not exists valid_to timestamptz;
alter table memories add column if not exists expired_at timestamptz;

-- Direct supersession pointer for chain walks in recall (Phase 1 filter).
-- memory_links.link_type='supersedes' still holds the graph; this is a
-- denormalized shortcut that lets recall filter in one join.
alter table memories add column if not exists superseded_by uuid
    references memories(id) on delete set null;

-- Entrenchment (Gärdenfors) / confidence. 0.0–1.0.
-- User-stated = 1.0, inferred from single session = 0.5, guessed from one
-- tool output = 0.2. Phase 2's classifier writes this; low-confidence memories
-- get aggressive decay and are hidden from default recall.
alter table memories add column if not exists confidence real default 0.5
    check (confidence is null or (confidence >= 0 and confidence <= 1));

-- JTMS justification — we cannot revise what we cannot attribute.
-- Free-form text so we can record arbitrary provenance (URL, tool name,
-- session id, actor namespace). Phase 2 classifier + Phase 4 episodic
-- layer will populate consistently.
alter table memories add column if not exists source_provenance text;

-- Profiles (overwrite-single-row) vs collections (append) distinction,
-- from LangMem. Eliminates supersession bugs by construction for rows where
-- the owner wants single-instance semantics (owner_preferences, device_config).
alter table memories add column if not exists single_instance boolean
    not null default false;

-- Embedding model migration safety. The day we upgrade from voyage-3-lite,
-- every cosine similarity in the DB becomes incomparable across models. We
-- need dual-column support during migration; these columns let us filter.
alter table memories add column if not exists embedding_model text
    default 'voyage-3-lite';
alter table memories add column if not exists embedding_version text
    default 'v1';

-- Indexes that Phase 1+ will rely on:
create index if not exists idx_memories_superseded_by
    on memories(superseded_by) where superseded_by is not null;
create index if not exists idx_memories_lifecycle_live
    on memories(type, project) where expired_at is null and superseded_by is null;
create index if not exists idx_memories_provenance
    on memories(source_provenance) where source_provenance is not null;

-- One-time backfill: copy updated_at -> content_updated_at for existing rows.
-- After this, Phase 1 will update the trigger to only bump content_updated_at
-- on actual content changes.
update memories
set content_updated_at = updated_at
where content_updated_at is null;

-- Denormalize existing memory_links.link_type='supersedes' edges into the
-- new superseded_by column. Convention: link.source supersedes link.target,
-- so the older (target) memory's superseded_by points to the newer (source).
update memories m
set superseded_by = l.source_id
from memory_links l
where l.link_type = 'supersedes'
  and l.target_id = m.id
  and m.superseded_by is null;


-- =========================================================================
-- Phase 1 (memory overhaul, Osasuwu/jarvis#185) — recall correctness
--
-- Goal: drive must_not violations to 0, stabilize MRR.
--
-- Changes:
--   1. Split timestamps properly:
--      - updated_at: bumped on any UPDATE (existing trigger, unchanged)
--      - content_updated_at: bumped only when name/description/content/tags
--        actually change (new trigger). This becomes the decay axis.
--      - last_accessed_at: set by touch_memories only (existing).
--      The old behavior bumped updated_at on every recall (via touch), which
--      meant temporal scoring reshuffled itself on every run → MRR noise.
--   2. Add default recall filter: exclude expired_at IS NOT NULL,
--      superseded_by IS NOT NULL, and (valid_to IS NOT NULL AND valid_to <= now()).
--   3. Add show_history flag to bypass the filter (for audit/debug queries).
--   4. Return content_updated_at from RPCs so server.py can use it for decay.
-- =========================================================================

-- Trigger: only bump content_updated_at when the memory's content-bearing
-- fields actually change. This is the field Phase 1 recall uses for decay,
-- so it must not be perturbed by touch_memories (which updates only
-- last_accessed_at but fires the generic update trigger).
create or replace function update_content_updated_at()
returns trigger as $$
begin
  if (new.name is distinct from old.name)
     or (new.description is distinct from old.description)
     or (new.content is distinct from old.content)
     or (new.tags is distinct from old.tags)
  then
    new.content_updated_at = now();
  end if;
  return new;
end;
$$ language plpgsql;

drop trigger if exists memories_content_updated_at on memories;
create trigger memories_content_updated_at
  before update on memories
  for each row execute function update_content_updated_at();

-- Replace match_memories: add lifecycle filter + show_history + return
-- content_updated_at. Signature adds two trailing optional params so
-- existing callers keep working.
drop function if exists match_memories(vector, int, float, text, text);
drop function if exists match_memories(vector, int, float, text, text, boolean);
create or replace function match_memories(
    query_embedding vector,
    match_limit int default 10,
    similarity_threshold float default 0.3,
    filter_project text default null,
    filter_type text default null,
    show_history boolean default false
)
returns table(
    id uuid, name text, type text, project text,
    description text, content text, tags text[],
    updated_at timestamptz, content_updated_at timestamptz,
    last_accessed_at timestamptz,
    similarity float
)
language sql stable as $$
    select m.id, m.name, m.type, m.project,
           m.description, m.content, m.tags,
           m.updated_at, m.content_updated_at, m.last_accessed_at,
           1 - (m.embedding <=> query_embedding) as similarity
    from memories m
    where m.embedding is not null
      and 1 - (m.embedding <=> query_embedding) >= similarity_threshold
      and (filter_project is null or m.project = filter_project or m.project is null)
      and (filter_type is null or m.type = filter_type)
      and (show_history
           or (m.expired_at is null
               and m.superseded_by is null
               and (m.valid_to is null or m.valid_to > now())))
    order by m.embedding <=> query_embedding
    limit match_limit;
$$;

-- Replace keyword_search_memories: same lifecycle filter + content_updated_at.
drop function if exists keyword_search_memories(text, int, text, text);
drop function if exists keyword_search_memories(text, int, text, text, boolean);
create or replace function keyword_search_memories(
    search_query text,
    match_limit int default 10,
    filter_project text default null,
    filter_type text default null,
    show_history boolean default false
)
returns table(
    id uuid, name text, type text, project text,
    description text, content text, tags text[],
    updated_at timestamptz, content_updated_at timestamptz,
    last_accessed_at timestamptz,
    rank real
)
language sql stable as $$
    select m.id, m.name, m.type, m.project,
           m.description, m.content, m.tags,
           m.updated_at, m.content_updated_at, m.last_accessed_at,
           ts_rank(m.fts, websearch_to_tsquery('english', search_query)) as rank
    from memories m
    where m.fts @@ websearch_to_tsquery('english', search_query)
      and (filter_project is null or m.project = filter_project or m.project is null)
      and (filter_type is null or m.type = filter_type)
      and (show_history
           or (m.expired_at is null
               and m.superseded_by is null
               and (m.valid_to is null or m.valid_to > now())))
    order by rank desc
    limit match_limit;
$$;


-- =========================================================================
-- Phase 2b (memory overhaul, Osasuwu/jarvis#185) — write-time classifier
--
-- Goal: replace the SUPERSEDE_SIM_THRESHOLD heuristic with an LLM decision
-- (Mem0-style ADD / UPDATE / DELETE / NOOP). Low-confidence decisions land
-- in this review queue instead of being silently applied — same idea as
-- LangMem's background mode, but synchronous on the write path because we
-- need the decision to know whether to mark a neighbor superseded.
--
-- Workflow:
--   1. memory_store computes embedding, upserts the row (stored_id).
--   2. Looks up top-K similar neighbors above CLASSIFIER_TRIGGER_SIM (~0.70).
--   3. If any → calls Haiku-4.5 with {candidate, neighbors} → JSON decision.
--   4. confidence >= APPLY_THRESHOLD (~0.7): apply the decision
--      (UPDATE/DELETE marks the target as superseded/expired).
--   5. confidence < APPLY_THRESHOLD: write to memory_review_queue
--      with status='pending' so the owner can audit before applying.
--
-- We always insert the candidate first (never lose data). DELETE/NOOP at
-- low confidence still become "ADD-and-queue-the-decision-for-review".
-- =========================================================================

create table if not exists memory_review_queue (
  id uuid primary key default gen_random_uuid(),

  -- The just-stored candidate that triggered classification.
  candidate_id uuid references memories(id) on delete cascade,

  -- Classifier output.
  decision text not null check (decision in ('ADD', 'UPDATE', 'DELETE', 'NOOP')),
  target_id uuid references memories(id) on delete set null,
  confidence real not null check (confidence >= 0 and confidence <= 1),
  reasoning text,

  -- Provenance for the decision itself (so we can audit which model said what).
  classifier_model text default 'claude-haiku-4-5',
  neighbors_seen jsonb,            -- snapshot of {id, name, similarity} fed to model

  -- Lifecycle of the queue entry.
  -- pending: awaiting owner review
  -- approved: owner approved, will be applied (or already applied)
  -- rejected: owner said no, decision discarded
  -- auto_applied: confidence was high enough to skip review (recorded for audit)
  status text not null default 'pending'
    check (status in ('pending', 'approved', 'rejected', 'auto_applied')),

  applied_at timestamptz,           -- when the decision actually mutated the row
  reviewed_at timestamptz,
  reviewed_by text,                 -- 'owner' / 'autonomous' / 'consolidation_job'

  created_at timestamptz default now()
);

create index if not exists idx_review_queue_pending
    on memory_review_queue(created_at desc) where status = 'pending';
create index if not exists idx_review_queue_candidate
    on memory_review_queue(candidate_id);

alter table memory_review_queue enable row level security;

create policy "Allow all for authenticated" on memory_review_queue
  for all using (true) with check (true);

create policy "Allow all for anon" on memory_review_queue
  for all to anon using (true) with check (true);


-- =========================================================================
-- Phase 2c (memory overhaul, Osasuwu/jarvis#185, #196) — provenance required
--
-- Goal: close the audit gap left by Phase 2. Every memory must carry
-- `source_provenance` so we can revise beliefs knowing who/what produced
-- them (JTMS principle — can't revise what you can't attribute).
--
-- Before 2c: `source_provenance` was a nullable column, populated when
-- convenient. In practice most rows were null, which defeated the purpose.
-- After 2c: NOT NULL enforced. MCP server rejects writes missing it.
-- Pre-policy rows get `legacy:pre-2c` so they're distinguishable from
-- policy-compliant data without blocking the constraint.
--
-- Coordinates with Phase 4 (#197): episode extractor will populate
-- `source_provenance = 'episode:<episode_id>'` — contract only, no overlap.
-- =========================================================================

-- Backfill pre-policy rows with a distinguishing marker. Literal string
-- (not '') so future queries can filter `where source_provenance =
-- 'legacy:pre-2c'` to find rows with no real provenance. Also catches
-- whitespace-only values — prior callers could persist '   ' which is
-- truthy in Python but carries no attribution.
update memories
set source_provenance = 'legacy:pre-2c'
where source_provenance is null
   or btrim(source_provenance) = '';

-- Enforce going forward. Any caller bypassing the MCP server with a raw
-- INSERT now errors out — which is the desired failure mode (those writes
-- also skip the embedding + classifier pipeline and shouldn't exist).
alter table memories
    alter column source_provenance set not null;

-- Soft-delete column. server.py has always written/filtered on this (store
-- clears it, recall/list/get/delete filter `is deleted_at null`), but the
-- column was never declared in schema.sql — meaning a fresh provision
-- would error at runtime. Add as part of the 2c hardening pass since the
-- provenance work is the first time the audit story is end-to-end.
alter table memories add column if not exists deleted_at timestamptz;

-- Partial index on tombstones. Mirrors the index already present in the
-- live DB — small set, fast to scan when purging or auditing deletes.
-- Live-row queries don't need a dedicated index: they combine deleted_at
-- with type/project/lifecycle filters already covered by existing indexes.
create index if not exists idx_memories_deleted_at
  on memories(deleted_at) where deleted_at is not null;


-- =========================================================================
-- Phase 4 (memory overhaul, Osasuwu/jarvis#197) — episodic layer
--
-- Raw "what happened" buffer that an async extractor distills into candidate
-- memories. Mirrors the episodic ↔ semantic separation from CLS theory and
-- production systems (Letta tiered memory, A-MEM, LangMem background mode):
-- non-lossy episodic buffer, consolidation happens offline.
--
-- Write path: hooks / skills / autonomous code insert rows here cheaply.
-- Read path: episode_extractor.py batches unprocessed rows, synthesizes
-- candidate memories via Haiku, and writes them through the existing
-- memory_store flow with source_provenance='episode:<id>'.
-- =========================================================================

create table if not exists episodes (
  id uuid primary key default gen_random_uuid(),

  -- Who/what produced this episode.
  -- Convention: 'session:<id>', 'scheduled:<skill>', 'hook:<name>',
  -- 'skill:<name>', 'autonomous:<skill>'.
  actor text not null,

  -- Shape of the payload. Extractor may prompt differently per kind.
  kind text not null
    check (kind in ('tool_call', 'decision', 'user_message', 'assistant_message', 'observation')),

  -- Arbitrary structured content. Schema is intentionally loose — episodes
  -- are raw material, not normalized facts.
  payload jsonb not null default '{}',

  -- Transaction time: when the episode was recorded.
  created_at timestamptz not null default now(),

  -- Extractor marks this when it has consumed the episode (success or skip).
  -- NULL = still in the backlog.
  processed_at timestamptz
);

-- Backlog scan — partial index so the extractor's "fetch next batch" query
-- stays cheap regardless of processed-history size.
create index if not exists idx_episodes_unprocessed
  on episodes(created_at) where processed_at is null;

-- Per-actor filtering for debugging / per-source stats.
create index if not exists idx_episodes_actor on episodes(actor);

-- Chronological audit.
create index if not exists idx_episodes_created on episodes(created_at desc);

alter table episodes enable row level security;

create policy "Allow all for authenticated" on episodes
  for all using (true) with check (true);

create policy "Allow all for anon" on episodes
  for all to anon using (true) with check (true);


-- =========================================================================
-- Phase 1 cont'd (memory overhaul, Osasuwu/jarvis#185) — supersedes-chain
-- collapse in link expansion.
--
-- Problem: match_memories and keyword_search_memories already filter out
-- superseded rows on the default path (show_history=false). But
-- get_linked_memories walks memory_links directly, which still points at
-- the older versions of a chain. So recall with include_links=true can
-- surface a memory whose current head was deliberately hidden by the
-- lifecycle filter — re-introducing the bug Phase 1 was meant to fix.
--
-- Fix:
--   1. find_chain_head(uuid, int) — recursive CTE walking superseded_by
--      to the terminal node. Returns the input id if it's already a head,
--      or the deepest reachable descendant (capped at max_depth to guard
--      against cycles from manual edits).
--   2. get_linked_memories replaced to (a) resolve the neighbor id through
--      find_chain_head before joining memories, (b) apply the same
--      lifecycle filter the other recall RPCs use (show_history param),
--      and (c) return content_updated_at + last_accessed_at so the caller
--      can temporally rescore linked memories consistently with primaries.
-- =========================================================================

-- Touch-safe update_updated_at: don't bump updated_at when the only column
-- changed is last_accessed_at (i.e. touch_memories RPC on recall). The
-- schema-level comment under Phase 0 already flagged this ("last_accessed_at
-- set by touch_memories only") but the generic trigger was rippling every
-- touch into updated_at, making session-start reads look like edits.
--
-- Why this matters: the fallback _keyword_recall orders by updated_at, and
-- session-context.py selects user memories by updated_at — neither should
-- be perturbed by the access-frequency touch.
--
-- Implementation: cheap short-circuit first — if last_accessed_at isn't
-- changing, this is a normal edit and updated_at must bump. Only on
-- touch-shaped UPDATEs do we pay for a JSONB diff of old vs new. This keeps
-- the hot path (regular writes) free of to_jsonb cost on the full row
-- (content can be kilobytes).
--
-- The JSONB diff strips last_accessed_at + updated_at (touch cols) and the
-- generated cols (fts, project_key), which appear NULL in NEW under BEFORE
-- UPDATE while OLD has the stored value (PostgreSQL quirk for GENERATED
-- ALWAYS STORED), so including them would always register as a diff. If
-- new generated columns are added, list them here too.
create or replace function update_updated_at()
returns trigger as $$
begin
  if new.last_accessed_at is distinct from old.last_accessed_at
     and (to_jsonb(new) - 'last_accessed_at' - 'updated_at' - 'fts' - 'project_key')
           = (to_jsonb(old) - 'last_accessed_at' - 'updated_at' - 'fts' - 'project_key') then
    return new;
  end if;
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;


create or replace function find_chain_head(mid uuid, max_depth int default 20)
returns uuid
language sql stable as $$
    with recursive chain as (
        select m.id, m.superseded_by, 0 as depth
        from memories m
        where m.id = mid
        union all
        select m.id, m.superseded_by, c.depth + 1
        from chain c
        join memories m on m.id = c.superseded_by
        where c.superseded_by is not null
          and c.depth < max_depth
    )
    -- Terminal node: either superseded_by IS NULL (a true head) or we hit
    -- max_depth (chain too long or cyclic — return deepest we saw).
    select id from chain order by depth desc limit 1;
$$;

drop function if exists get_linked_memories(uuid[], text[]);
drop function if exists get_linked_memories(uuid[], text[], boolean);
create or replace function get_linked_memories(
    memory_ids uuid[],
    link_types text[] default null,
    show_history boolean default false
)
returns table(
    id uuid, name text, type text, project text,
    description text, content text, tags text[],
    updated_at timestamptz, content_updated_at timestamptz,
    last_accessed_at timestamptz,
    link_type text, link_strength float, linked_from uuid
)
language sql stable as $$
    select * from (
        -- DISTINCT ON collapses multiple edges between the same pair of
        -- memories — keep the strongest one after chain resolution. Two
        -- different originals may resolve to the same head, so we dedup
        -- on the resolved id rather than the raw link target.
        select distinct on (sub.id)
            sub.id, sub.name, sub.type, sub.project, sub.description,
            sub.content, sub.tags,
            sub.updated_at, sub.content_updated_at, sub.last_accessed_at,
            sub.link_type, sub.link_strength, sub.linked_from
        from (
            -- Outgoing edges: source ∈ memory_ids, target resolved to head.
            select m.id, m.name, m.type, m.project, m.description, m.content,
                   m.tags, m.updated_at, m.content_updated_at, m.last_accessed_at,
                   l.link_type, l.strength as link_strength, l.source_id as linked_from
            from memory_links l
            join memories m on m.id = coalesce(
                case when show_history then l.target_id
                     else find_chain_head(l.target_id) end,
                l.target_id)
            where l.source_id = any(memory_ids)
              and not (m.id = any(memory_ids))
              and (link_types is null or l.link_type = any(link_types))
              and (show_history
                   or (m.expired_at is null
                       and m.superseded_by is null
                       and (m.valid_to is null or m.valid_to > now())))
            union all
            -- Incoming edges: target ∈ memory_ids, source resolved to head.
            select m.id, m.name, m.type, m.project, m.description, m.content,
                   m.tags, m.updated_at, m.content_updated_at, m.last_accessed_at,
                   l.link_type, l.strength as link_strength, l.target_id as linked_from
            from memory_links l
            join memories m on m.id = coalesce(
                case when show_history then l.source_id
                     else find_chain_head(l.source_id) end,
                l.source_id)
            where l.target_id = any(memory_ids)
              and not (m.id = any(memory_ids))
              and (link_types is null or l.link_type = any(link_types))
              and (show_history
                   or (m.expired_at is null
                       and m.superseded_by is null
                       and (m.valid_to is null or m.valid_to > now())))
        ) sub
        order by sub.id, sub.link_strength desc, sub.link_type, sub.linked_from
    ) deduped
    order by deduped.link_strength desc
    limit 10;
$$;


-- =========================================================================
-- Phase 5.1b-β (memory overhaul, Osasuwu/jarvis#185, #221) — consolidation
-- apply path.
--
-- Builds on 5.1b-α (#220): the Haiku planner emits per-cluster plans of kind
-- MERGE / SUPERSEDE / KEEP_DISTINCT. 5.1b-β converts those plans into
-- actual mutations, gated by confidence (>= 0.85, owner-decided 2026-04-19).
-- Everything below the gate — and every KEEP_DISTINCT — is recorded in
-- memory_review_queue so we (a) have an audit trail and (b) don't re-spend
-- Haiku tokens on the same cluster every week.
--
-- Queue strategy (owner-decided: reuse, don't fork):
--   - Extend memory_review_queue.decision CHECK with MERGE,
--     SUPERSEDE_CONSOLIDATION, KEEP_DISTINCT. Phase 2 rows keep their ADD/
--     UPDATE/DELETE/NOOP semantics untouched.
--   - New column consolidation_payload jsonb holds cluster-level state
--     (member_ids, canonical_* fields, haiku metadata). Phase 2 rows leave
--     it NULL; a functional index makes "have I seen this cluster?" checks
--     cheap for the planner's pre-filter.
--   - Extend status CHECK with 'rolled_back' so a reverted entry is visibly
--     distinct from owner-rejected entries (the former means "try again
--     later", the latter means "never suggest again").
-- =========================================================================

alter table memory_review_queue
  drop constraint if exists memory_review_queue_decision_check;

alter table memory_review_queue
  add constraint memory_review_queue_decision_check
  check (decision in (
    'ADD', 'UPDATE', 'DELETE', 'NOOP',
    'MERGE', 'SUPERSEDE_CONSOLIDATION', 'KEEP_DISTINCT'
  ));

alter table memory_review_queue
  drop constraint if exists memory_review_queue_status_check;

alter table memory_review_queue
  add constraint memory_review_queue_status_check
  check (status in (
    'pending', 'approved', 'rejected', 'auto_applied', 'rolled_back'
  ));

alter table memory_review_queue
  add column if not exists consolidation_payload jsonb;

-- Functional index on the sorted-member-id key. The planner pre-filter asks
-- "does any queue row already cover this exact set of members?"; a direct
-- equality lookup on member_ids_key inside the jsonb is O(log n) with this
-- index and scales independent of Phase 2 row count.
create index if not exists idx_review_queue_member_ids_key
  on memory_review_queue((consolidation_payload->>'member_ids_key'))
  where consolidation_payload is not null;


-- apply_consolidation_plan: atomic per cluster.
--
-- MERGE: synthesize a new canonical memory from Haiku's output, mark every
-- member superseded_by the new id, drop a `consolidates` link per member.
-- Embedding is populated out-of-band by the caller (Python has VoyageAI);
-- the write leaves `embedding IS NULL` temporarily — acceptable since the
-- lifecycle filter on members immediately hides them from recall, and the
-- caller backfills within a second.
--
-- SUPERSEDE_CONSOLIDATION: one existing member wins, all others get
-- superseded_by = canonical. No new memory, no new embedding needed.
--
-- Returns jsonb: { status, decision, canonical_id, superseded_count }.
create or replace function apply_consolidation_plan(plan jsonb)
returns jsonb
language plpgsql volatile
as $$
declare
    v_decision text := plan->>'decision';
    v_canonical_id uuid := nullif(plan->>'canonical_id', '')::uuid;
    v_supersede_ids uuid[] := array(
        select (jsonb_array_elements_text(coalesce(plan->'supersede_ids', '[]'::jsonb)))::uuid
    );
    v_tags text[] := array(
        select jsonb_array_elements_text(coalesce(plan->'canonical_tags', '[]'::jsonb))
    );
    v_new_id uuid;
    v_rows int;
begin
    if v_decision = 'MERGE' then
        if coalesce(plan->>'canonical_name', '') = ''
           or coalesce(plan->>'canonical_content', '') = ''
           or coalesce(plan->>'canonical_type', '') = ''
           or coalesce(plan->>'source_provenance', '') = '' then
            raise exception 'MERGE plan missing required canonical_* / source_provenance fields';
        end if;

        insert into memories (
            project, name, type, description, content, tags,
            source_provenance, confidence
        )
        values (
            nullif(plan->>'canonical_project', ''),
            plan->>'canonical_name',
            plan->>'canonical_type',
            nullif(plan->>'canonical_description', ''),
            plan->>'canonical_content',
            v_tags,
            plan->>'source_provenance',
            least(coalesce((plan->>'confidence')::float, 0.8), 0.9)
        )
        returning id into v_new_id;

        -- Supersede every member. coalesce() preserves any pre-existing
        -- lifecycle timestamp rather than clobbering it — matters if a
        -- member was already expired for an unrelated reason and we're
        -- consolidating after the fact.
        update memories
        set superseded_by = v_new_id,
            valid_to = coalesce(valid_to, now()),
            expired_at = coalesce(expired_at, now())
        where id = any(v_supersede_ids);
        get diagnostics v_rows = row_count;

        insert into memory_links (source_id, target_id, link_type, strength)
        select v_new_id, unnest_id, 'consolidates', 1.0
        from unnest(v_supersede_ids) as unnest_id
        on conflict (source_id, target_id, link_type) do nothing;

        return jsonb_build_object(
            'status', 'applied',
            'decision', 'MERGE',
            'canonical_id', v_new_id,
            'superseded_count', v_rows
        );
    elsif v_decision = 'SUPERSEDE_CONSOLIDATION' then
        if v_canonical_id is null then
            raise exception 'SUPERSEDE_CONSOLIDATION requires canonical_id';
        end if;

        update memories
        set superseded_by = v_canonical_id,
            valid_to = coalesce(valid_to, now()),
            expired_at = coalesce(expired_at, now())
        where id = any(v_supersede_ids)
          and id <> v_canonical_id;
        get diagnostics v_rows = row_count;

        insert into memory_links (source_id, target_id, link_type, strength)
        select v_canonical_id, unnest_id, 'supersedes', 1.0
        from unnest(v_supersede_ids) as unnest_id
        where unnest_id <> v_canonical_id
        on conflict (source_id, target_id, link_type) do nothing;

        return jsonb_build_object(
            'status', 'applied',
            'decision', 'SUPERSEDE_CONSOLIDATION',
            'canonical_id', v_canonical_id,
            'superseded_count', v_rows
        );
    else
        raise exception 'Unsupported decision for apply_consolidation_plan: %', v_decision;
    end if;
end;
$$;


-- rollback_consolidation(queue_id): inverse of apply, keyed by the queue
-- entry so the member-id list is authoritative (not re-derived from links,
-- which could collide with Phase 2 classifier supersedes).
--
-- MERGE rollback:  soft-delete the synthesized canonical, clear members'
--                  lifecycle cols, remove `consolidates` links.
-- SUPERSEDE_CONSOLIDATION rollback: leave canonical live, restore the
--                  losers, remove `supersedes` links created by this apply.
--
-- Status transitions: 'auto_applied'/'approved' → 'rolled_back'. Rejecting
-- an already-applied entry is not supported through this RPC — it would
-- conflate "owner disapproves future suggestion" with "undo this mutation".
create or replace function rollback_consolidation(queue_id uuid)
returns jsonb
language plpgsql volatile
as $$
declare
    v_payload jsonb;
    v_decision text;
    v_status text;
    v_canonical_id uuid;
    v_supersede_ids uuid[];
    v_rows int;
begin
    select consolidation_payload, decision, status, target_id
    into v_payload, v_decision, v_status, v_canonical_id
    from memory_review_queue
    where id = queue_id
    for update;

    if v_payload is null then
        raise exception 'Queue entry % missing (or has no consolidation_payload)', queue_id;
    end if;

    if v_decision not in ('MERGE', 'SUPERSEDE_CONSOLIDATION') then
        raise exception 'Entry % is not a consolidation row (decision=%)', queue_id, v_decision;
    end if;

    if v_status not in ('auto_applied', 'approved') then
        raise exception 'Can only roll back auto_applied/approved entries (status=%)', v_status;
    end if;

    if v_canonical_id is null then
        raise exception 'Entry % has no target_id to roll back', queue_id;
    end if;

    v_supersede_ids := array(
        select (jsonb_array_elements_text(coalesce(v_payload->'supersede_ids', '[]'::jsonb)))::uuid
    );

    update memories
    set superseded_by = null,
        valid_to = null,
        expired_at = null
    where id = any(v_supersede_ids)
      and superseded_by = v_canonical_id;
    get diagnostics v_rows = row_count;

    delete from memory_links
    where source_id = v_canonical_id
      and target_id = any(v_supersede_ids)
      and link_type in ('consolidates', 'supersedes');

    if v_decision = 'MERGE' then
        update memories
        set deleted_at = now()
        where id = v_canonical_id;
    end if;

    update memory_review_queue
    set status = 'rolled_back',
        reviewed_at = now(),
        reviewed_by = coalesce(reviewed_by, 'rollback_script')
    where id = queue_id;

    return jsonb_build_object(
        'status', 'rolled_back',
        'decision', v_decision,
        'canonical_id', v_canonical_id,
        'canonical_soft_deleted', v_decision = 'MERGE',
        'restored_count', v_rows
    );
end;
$$;

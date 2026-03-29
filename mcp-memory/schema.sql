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

-- Voyage AI embedding storage (optional — set VOYAGE_API_KEY to enable semantic search)
-- Stored as real[] (512 floats); similarity is computed in-process, no pgvector required.
alter table memories add column if not exists embedding real[];

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

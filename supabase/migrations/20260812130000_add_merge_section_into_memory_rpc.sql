-- Add atomic server-side merge_section function for memory_store (#1352)
-- Implements optimistic concurrency control via compare-and-swap on updated_at
-- Uses pg_advisory_xact_lock (transaction-scoped) for insert-race safety

create or replace function merge_section_into_memory_upsert(
  p_project text,
  p_name text,
  p_merged_content text,
  p_expected_updated_at timestamptz,
  p_description text default '',
  p_tags text[] default '{}',
  p_preserve_existing_description boolean default true,
  p_preserve_existing_tags boolean default true,
  -- #242 dual-embedding machinery: PRIMARY (voyage-3-lite, 512-dim) always
  -- present when embedding succeeded; SECONDARY (voyage-3, 1024-dim) only
  -- when EMBEDDING_MODEL_SECONDARY is configured. NULL means "no new
  -- embedding computed this call" — coalesce()'d against the existing row
  -- on UPDATE so a NULL never clobbers a previously-computed vector.
  p_embedding vector(512) default null,
  p_embedding_model text default null,
  p_embedding_version text default null,
  p_embedding_v2 vector(1024) default null,
  p_embedding_model_v2 text default null,
  p_embedding_version_v2 text default null
)
returns table (success boolean, memory_id uuid, conflict_reason text) as $$
declare
  v_id uuid;
  v_current_updated_at timestamptz;
  v_existing_description text;
  v_existing_tags text[];
  v_final_description text;
  v_final_tags text[];
  v_lock_id bigint;
begin
  -- Use transaction-scoped advisory lock for insert-race safety
  -- (when no existing row exists, multiple concurrent inserts could race)
  -- Hash the project and name into a lockid; use first 31 bits to fit into int
  v_lock_id := (hashtext(coalesce(p_project, '') || '::' || p_name)::bigint & x'7FFFFFFF'::bigint)::int;
  perform pg_advisory_xact_lock(v_lock_id);

  -- Fetch existing row to check for concurrent modification
  select id, updated_at, description, tags
    into v_id, v_current_updated_at, v_existing_description, v_existing_tags
    from memories
   where name = p_name
     and (project = p_project or (p_project is null and project is null))
     and deleted_at is null;

  -- Optimistic concurrency check: compare expected updated_at with current
  if v_id is not null then
    if v_current_updated_at is distinct from p_expected_updated_at then
      -- Concurrent modification detected — another session changed the row
      return query select false, null::uuid, 'merge_conflict: concurrent modification'::text;
      return;
    end if;
  end if;

  -- Decide on final description and tags
  v_final_description := case
    when v_id is not null and p_preserve_existing_description and v_existing_description is not null
    then v_existing_description
    else p_description
  end;

  v_final_tags := case
    when v_id is not null and p_preserve_existing_tags and v_existing_tags is not null
    then v_existing_tags
    else p_tags
  end;

  -- Upsert: update if exists, insert if not
  if v_id is not null then
    update memories
       set content = p_merged_content,
           description = v_final_description,
           tags = v_final_tags,
           updated_at = now(),
           embedding = coalesce(p_embedding, embedding),
           embedding_model = coalesce(p_embedding_model, embedding_model),
           embedding_version = coalesce(p_embedding_version, embedding_version),
           embedding_v2 = coalesce(p_embedding_v2, embedding_v2),
           embedding_model_v2 = coalesce(p_embedding_model_v2, embedding_model_v2),
           embedding_version_v2 = coalesce(p_embedding_version_v2, embedding_version_v2)
     where id = v_id;
  else
    insert into memories (
      project, name, content, description, tags, source_provenance,
      embedding, embedding_model, embedding_version,
      embedding_v2, embedding_model_v2, embedding_version_v2
    )
    values (
      p_project, p_name, p_merged_content, v_final_description, v_final_tags, 'rpc:merge_section',
      p_embedding, p_embedding_model, p_embedding_version,
      p_embedding_v2, p_embedding_model_v2, p_embedding_version_v2
    )
    returning memories.id into v_id;
  end if;

  return query select true, v_id, null::text;
end;
$$ language plpgsql security definer;

-- Grant RPC access
grant execute on function merge_section_into_memory_upsert to anon, authenticated;

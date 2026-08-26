-- Fix merge_section_into_memory_upsert 23505 on soft-deleted rows (#1714)
--
-- The existence-check SELECT in the base migration
-- (20260812130000_add_merge_section_into_memory_rpc.sql) filters
-- `deleted_at is null`, so a soft-deleted row at the same (project, name) is
-- treated as "not found" and the function falls into the INSERT branch,
-- which collides with the still-present unique(project, name) constraint on
-- the tombstone row (raw Postgres 23505).
--
-- Fix: drop that filter from the existence check so a soft-deleted row is
-- found and updated instead. Revival semantics are revive-fresh (decision
-- 84c5b737-1887-4c78-9d8b-e58dedac2b04, issue #1714 AC1-AC8): the revived
-- row's content is built from an empty base (already true — the merge
-- happens in Python against a fetch that excludes deleted_at rows too, see
-- handlers/memory.py's _fetch_and_remerge_section fix in the same PR) and
-- its prior description/tags are NOT preserved on revive, mirroring how the
-- plain (non-merge_section) memory_store upsert path already clobbers on
-- revive. `deleted_at` is cleared on the UPDATE branch so the row becomes
-- live again.
-- The base migration's function returned table(success, memory_id,
-- conflict_reason) — 3 OUT params. This version widens to 6 (adding revived,
-- expired_at, superseded_by). Postgres refuses to CREATE OR REPLACE a
-- function whose OUT-parameter-defined row type changed, so the old
-- signature must be dropped first.
drop function if exists merge_section_into_memory_upsert(
  text, text, text, timestamptz, text, text, text, text[],
  boolean, boolean, vector(512), text, text, vector(1024), text, text
);

create or replace function merge_section_into_memory_upsert(
  p_project text,
  p_name text,
  p_merged_content text,
  p_expected_updated_at timestamptz,
  p_type text default null,
  p_source_provenance text default 'rpc:merge_section',
  p_description text default '',
  p_tags text[] default '{}',
  p_preserve_existing_description boolean default true,
  p_preserve_existing_tags boolean default true,
  p_embedding vector(512) default null,
  p_embedding_model text default null,
  p_embedding_version text default null,
  p_embedding_v2 vector(1024) default null,
  p_embedding_model_v2 text default null,
  p_embedding_version_v2 text default null
)
returns table (
  success boolean,
  memory_id uuid,
  conflict_reason text,
  revived boolean,
  expired_at timestamptz,
  superseded_by uuid
) as $$
declare
  v_id uuid;
  v_current_updated_at timestamptz;
  v_existing_description text;
  v_existing_tags text[];
  v_existing_source_provenance text;
  v_existing_deleted_at timestamptz;
  v_existing_expired_at timestamptz;
  v_existing_superseded_by uuid;
  v_was_deleted boolean;
  v_final_description text;
  v_final_tags text[];
  v_lock_id bigint;
begin
  -- RLS parity check (unchanged from base migration) — see that file's
  -- comment for the full rationale.
  if auth.role() = 'anon'
     and (p_source_provenance is null or p_source_provenance not like 'sandcastle:%') then
    return query select false, null::uuid, 'forbidden: anon callers must use sandcastle:%-prefixed source_provenance'::text, null::boolean, null::timestamptz, null::uuid;
    return;
  end if;

  v_lock_id := (hashtext(coalesce(p_project, '') || '::' || p_name)::bigint & x'7FFFFFFF'::bigint)::int;
  perform pg_advisory_xact_lock(v_lock_id);

  -- #1714: dropped `and deleted_at is null` — a soft-deleted row at this
  -- (project, name) must be found here so it goes through UPDATE (revival)
  -- instead of falling through to INSERT and colliding with the
  -- unique(project, name) constraint the tombstone row still occupies.
  --
  -- Table-qualified (m.expired_at, m.superseded_by): this function's own
  -- RETURNS TABLE columns are named expired_at/superseded_by, which plpgsql
  -- exposes as variables in scope here — an unqualified select of the same-
  -- named memories columns raises "column reference is ambiguous".
  select m.id, m.updated_at, m.description, m.tags, m.source_provenance,
         m.deleted_at, m.expired_at, m.superseded_by
    into v_id, v_current_updated_at, v_existing_description, v_existing_tags, v_existing_source_provenance,
         v_existing_deleted_at, v_existing_expired_at, v_existing_superseded_by
    from memories m
   where m.name = p_name
     and (m.project = p_project or (p_project is null and m.project is null));

  v_was_deleted := v_id is not null and v_existing_deleted_at is not null;

  if v_id is not null and auth.role() = 'anon'
     and (v_existing_source_provenance is null or v_existing_source_provenance not like 'sandcastle:%') then
    return query select false, null::uuid, 'forbidden: anon callers may not modify a non-sandcastle-owned row'::text, null::boolean, null::timestamptz, null::uuid;
    return;
  end if;

  -- ceiling: memory_delete (handlers/memory.py's _handle_delete) sets
  -- deleted_at without bumping updated_at, so this OCC compare-and-swap
  -- cannot detect a delete racing an in-flight merge_section between the
  -- Python-side fetch and this RPC call — the row will be silently revived
  -- even though a concurrent caller just deleted it. Upgrade path: bump
  -- updated_at in _handle_delete's UPDATE, or add an explicit
  -- `and v_existing_deleted_at is not distinct from <expected_deleted_at>`
  -- comparison threaded through from the Python fetch. #1714 follow-up.
  if v_id is not null then
    if v_current_updated_at is distinct from p_expected_updated_at then
      return query select false, null::uuid, 'merge_conflict: concurrent modification'::text, null::boolean, null::timestamptz, null::uuid;
      return;
    end if;
  end if;

  -- #1714: revive-fresh — a soft-deleted row's prior description/tags are
  -- never preserved on revival, even if the caller asked to preserve
  -- (p_preserve_existing_* true is the merge_section default). This mirrors
  -- the plain memory_store upsert path, which already clobbers on revive.
  v_final_description := case
    when v_id is not null and not v_was_deleted and p_preserve_existing_description and v_existing_description is not null
    then v_existing_description
    else p_description
  end;

  v_final_tags := case
    when v_id is not null and not v_was_deleted and p_preserve_existing_tags and v_existing_tags is not null
    then v_existing_tags
    else p_tags
  end;

  if v_id is not null then
    update memories
       set content = p_merged_content,
           description = v_final_description,
           tags = v_final_tags,
           updated_at = now(),
           deleted_at = null,
           embedding = coalesce(p_embedding, embedding),
           embedding_model = coalesce(p_embedding_model, embedding_model),
           embedding_version = coalesce(p_embedding_version, embedding_version),
           embedding_v2 = coalesce(p_embedding_v2, embedding_v2),
           embedding_model_v2 = coalesce(p_embedding_model_v2, embedding_model_v2),
           embedding_version_v2 = coalesce(p_embedding_version_v2, embedding_version_v2)
     where id = v_id;
  else
    insert into memories (
      project, name, type, content, description, tags, source_provenance,
      embedding, embedding_model, embedding_version,
      embedding_v2, embedding_model_v2, embedding_version_v2
    )
    values (
      p_project, p_name, p_type, p_merged_content, v_final_description, v_final_tags, p_source_provenance,
      p_embedding, p_embedding_model, p_embedding_version,
      p_embedding_v2, p_embedding_model_v2, p_embedding_version_v2
    )
    returning memories.id into v_id;
  end if;

  return query select true, v_id, null::text, v_was_deleted, v_existing_expired_at, v_existing_superseded_by;
end;
$$ language plpgsql security definer;

grant execute on function merge_section_into_memory_upsert to anon, authenticated;

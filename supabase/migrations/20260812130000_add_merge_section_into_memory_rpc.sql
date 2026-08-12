-- Add atomic server-side merge_section function for memory_store (#1352)
-- Ensures atomicity by locking during SELECT-then-UPDATE sequence

create or replace function merge_section_into_memory_upsert(
  p_project text,
  p_name text,
  p_merged_content text,
  p_description text default '',
  p_tags text[] default '{}',
  p_preserve_existing_description boolean default true,
  p_preserve_existing_tags boolean default true
)
returns uuid as $$
declare
  v_id uuid;
  v_existing_description text;
  v_existing_tags text[];
  v_final_description text;
  v_final_tags text[];
begin
  -- Use advisory lock to serialize merges for this (project, name) pair
  -- Hash the project and name into a single lockid; use first 32 bits to fit into int
  perform pg_advisory_lock((
    hashtext(coalesce(p_project, '') || '::' || p_name)::bigint & x'7FFFFFFF'::bigint
  )::int);

  -- Fetch existing row (locked by advisory lock above for serialization)
  select id, description, tags
    into v_id, v_existing_description, v_existing_tags
    from memories
   where name = p_name
     and (project = p_project or (p_project is null and project is null))
     and deleted_at is null;

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
           updated_at = now()
     where id = v_id;
  else
    insert into memories (project, name, content, description, tags, source_provenance)
    values (p_project, p_name, p_merged_content, v_final_description, v_final_tags, 'rpc:merge_section')
    returning memories.id into v_id;
  end if;

  return v_id;
end;
$$ language plpgsql security definer;

-- Grant RPC access
grant execute on function merge_section_into_memory_upsert to anon, authenticated;

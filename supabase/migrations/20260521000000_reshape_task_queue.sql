-- Pillar 7 Sprint 5: task_queue reshape (issue #740)
-- Drop approval-gated columns, add priority + assignee, new FSM.
-- Paired with mcp-memory/schema.sql. CI gate requires a migration file
-- whenever schema.sql changes.
--
-- Rationale: approval-gated columns (approved_by, approved_at,
-- approved_scope_hash, auto_dispatch) were designed for the LangGraph
-- dispatcher (retired per #741). The reactive-core task queue needs a
-- simpler schema focused on ordering (priority) and ownership (assignee).
--
-- New FSM (enforced in code; DB CHECK guards the enum):
--   pending -> claimed -> running -> done | failed | parked
--   claimed -> pending      (claim timeout / re-queue)
--   done    -> (terminal)
--   failed  -> (terminal)
--   parked  -> (terminal)

-- Clear all existing rows — schema is incompatible (dropping NOT NULL
-- columns that were required in the old shape).
delete from task_queue;

-- Drop approval-gated columns.
alter table task_queue drop column approved_at;
alter table task_queue drop column approved_by;
alter table task_queue drop column approved_scope_hash;
alter table task_queue drop column auto_dispatch;

-- Add new ordering / ownership columns.
alter table task_queue add column priority int not null default 0;
alter table task_queue add column assignee text;

-- New FSM constraint.
alter table task_queue drop constraint if exists task_queue_status_check;
alter table task_queue add constraint task_queue_status_check
  check (status in ('pending', 'claimed', 'running', 'done', 'failed', 'parked'));

-- Replace the old index (ordered by approved_at) with one ordered by
-- priority then creation time, for claim_next() scanning.
drop index if exists idx_task_queue_pending_scan;
create index if not exists idx_task_queue_claim_scan
  on task_queue(priority asc, created_at asc)
  where status = 'pending';

-- Rename dispatched_at -> claimed_at for clarity under the new FSM.
-- Only rename if the column still exists (may have been renamed in an
-- earlier partial migration on some environments).
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_name = 'task_queue' and column_name = 'dispatched_at'
  ) then
    alter table task_queue rename column dispatched_at to claimed_at;
  end if;
end $$;

-- Issue #745: Add blocking_task column to events table for parked-event re-queue poller.
--
-- Enables the poller to map parked events to their blocking task_queue rows
-- and automatically requeue them when the blocking task reaches a terminal state (done).

-- Add blocking_task column: UUID reference to the blocking task_queue row.
-- NULL = event is not parked / not blocked by a task.
ALTER TABLE events ADD COLUMN IF NOT EXISTS blocking_task uuid;

-- Add foreign key constraint (cascade delete is deliberate — if a task is deleted,
-- its blocking relationship is also cleared, allowing the event to be processed
-- by other means).
ALTER TABLE events
  ADD CONSTRAINT fk_events_blocking_task
  FOREIGN KEY (blocking_task)
  REFERENCES task_queue (id)
  ON DELETE SET NULL;

-- Comment for schema documentation
COMMENT ON COLUMN events.blocking_task IS
  'UUID of the task_queue row blocking this event. NULL = not parked or no blocking task. Set when event is parked and awaiting task completion; cleared when event is requeued.';

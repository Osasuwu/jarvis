# Memory subsystem — pull-only reference

Evicted from the always-loaded [`docs/context/invariants.md`](../context/invariants.md) by
[#1418](https://github.com/Osasuwu/jarvis/issues/1418). These facts are read at the instant of an
`mcp__memory__*` call or while working inside `mcp-memory/` — they decide nothing in a session that
never touches memory internals, so they are not worth a byte in every window. Pull this file when
the answer turns on how the memory server behaves.

The two memory rules that *do* bind every session stay in `invariants.md`: Supabase is cross-device
truth, and secrets never land in any persistent surface.

## `memory_store` contract

Needs `source_provenance`. Idempotent on `(project, name)` and **never** similarity-blocked — the
tool response is the signal, so read it rather than assuming a store was deduplicated away.
`memories_used` carries UUIDs, never names (user-level `CLAUDE.md` §2 is the canonical statement of
that half; it is restated here only so this file reads whole).

## Recall internals

- FoK `unknown` / `skipped` are terminal states.
- HNSW is used only for a bare `<=> anchor limit K` query; adding predicates forces an exact scan.
- Clusters are disjoint per `(type, project_key)` and capped above 10.

Server-side implementation detail of `mcp-memory/`. It explains recall behaviour when a query
returns something surprising; it does not gate any tool call.

## Sandcastle provenance RLS

Row-level security covers **every** anon INSERT/UPDATE/DELETE on `memories`, `task_outcomes`,
`episodes`, and `events_canonical` — each requires `source_provenance` / `actor` matching
`LIKE 'sandcastle:%'`.

This is a database constraint: the DB rejects a non-conforming write. Recorded here so the rejection
is diagnosable, not as a rule an agent must remember to obey.

## Memory hygiene is owner-invoked only

`/curate` runs on command. There is no auto-demote hook — nothing prunes memory on a schedule. The
skill states its own trigger model; this line exists so "why did nothing get curated?" has an answer
without reading the skill.

## Write cost of the recall path, and the `archive_timeout` floor under it

Recorded from [#1645](https://github.com/Osasuwu/jarvis/issues/1645), where the Supabase
disk-IO budget hit a ~72% weekly average on a 149 MB database with a 100.000% buffer-cache
hit ratio. Every byte of that budget was write, none of it read.

**Why a timestamp bump is expensive here.** `memories` main-heap tuples average ~2.2 KB —
`fts`, `content` and `embedding` are wide — so a page holds ~3.6 rows and cannot fit a second
version of one. HOT therefore never applies (0.2% of 124k lifetime UPDATEs), and every
`last_accessed_at` bump rewrites all 19 indexes, including an HNSW and four GIN indexes.
Lowering `fillfactor` does not rescue this: reserving 20% of a page leaves 1,638 bytes against
a 2.2 KB tuple. `touch_memories` is debounced to one write per row per hour for this reason;
treat `last_accessed_at` as hour-granular.

**`archive_timeout = 120` is a multiplier on all of it.** WAL segments are 16 MB. A forced
segment switch makes the archiver read and ship the whole 16 MB file no matter how few bytes
of real WAL it holds, so the archive volume tracks *how many 2-minute windows contain any
write at all*, not how much was written. Measured on this instance: 1,720 segments over 4.73
days — 26.9 GB archived to carry a period whose real WAL was a small fraction of that, against
a lifetime ratio of roughly 40:1 (1,055 GB archived vs 26.4 GB of actual WAL records). A
workload of small writes spread thinly over time is the worst possible fit for the setting,
which is exactly what an unbounded recall-touch path produces.

**The setting is not reachable from here.** Supabase exposes Postgres configuration through
three surfaces, and `archive_timeout` is outside all of them: it is not `context='user'` in
`pg_settings` (so no `alter database ... set`), it is not supautils role-settable (so no
`alter role`), and it is not on the ~25-parameter allowlist of
`supabase --experimental postgres-config`. There is no dashboard UI for server parameters.
Changing it requires a support request; one was filed for this project on 2026-08-24.
`checkpoint_timeout`, by contrast, *is* on the CLI allowlist and was raised 300 → 1800 —
which cut checkpoint count 4.67× but bought only ~6% in WAL volume, because on a scattered
index-heavy write pattern the dirty-page set per checkpoint scales roughly linearly with the
interval instead of saturating. Cutting the writes beats spacing out their consequences.

**RPO consequence, stated explicitly.** `archive_timeout` bounds the worst case window of WAL
that exists only on the instance's local disk and has not yet reached archive storage. At 120 s
that window is two minutes; raising it to 600 s widens it to ten. On total instance loss,
committed transactions inside that window are unrecoverable from the archive. For this
database — a personal memory store whose writes are recall timestamps and new memories, with
no external system reconciling against it — ten minutes of potential loss is an accepted
trade for a ~5× cut in archive volume. Do not carry this judgement over to a database with
different loss semantics.

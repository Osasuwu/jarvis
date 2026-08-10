"""MCP write-path Tier-2 secret-scrubber gate (#555).

The slice-3 scrubber (``scripts/lib/secret_scrubber.py``) is applied at the
MCP write boundary. This is the Tier-2 backstop in the two-layer privacy
model (decision ``eb62980e``, ADR-0003): even if the SessionEnd hook scrubber
(slice 6) leaks, MCP writes still cannot land secrets.

When any pattern fires on user-supplied text, the write is **rejected** — not
silently scrubbed. The write is intent-bearing, so the sender must know the
payload was blocked rather than silently rewritten.

Privacy invariant: no value from a blocked payload ever leaves this module.
Only pattern names + fire counts appear in the rejection error, the
``mcp_write_scrubber_block`` counter event, or any log line.

Scope (#555 AC + #999 follow-up): this gate covers ``memory_store``,
``record_decision``, ``goal_set``, ``goal_update``, ``outcome_record``, and
``outcome_update``. ``credential_add`` is deliberately NOT a candidate — it is the one write path
whose entire *domain* is credentials. It records credential metadata (env var
names, provider, expiry) plus free-text note fields (``notes`` /
``rotation_notes``) that legitimately discuss key-shaped values; a
secret-reject gate there would fight the handler's own purpose (it exists to
catalogue credentials, so naming one is expected, not a leak). The structured
value columns reject raw secrets at the schema level; the notes fields rely on
the ``credential_registry`` access model, not scrubbing.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import threading
from datetime import datetime, timezone
from collections.abc import Iterator
from pathlib import Path

# The scrubber lib lives under scripts/lib. The live server runtime launches
# server.py from mcp-memory/ (via run-memory-server.py), so scripts/ is NOT on
# sys.path by default — add it here so jarvis always loads the real gate
# instead of silently degrading to a no-op. Tests already put scripts/ on the
# path (conftest), so the insert is idempotent there.
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
# Gate on the target FILE existing, not merely a scripts/ dir: a host that has
# an unrelated scripts/ directory (or a redrobot layout) must not get scripts/
# prepended to sys.path, where it could shadow a stdlib/site module named `lib`.
if (_SCRIPTS / "lib" / "secret_scrubber.py").is_file() and str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _classify_disable_reason(exc: BaseException) -> str:
    """Map an import-time exception to a disable-reason string (AC1, #1000).

    ``module_absent`` covers the expected redrobot case (scripts/lib genuinely
    missing); ``import_broken:<ExceptionType>`` covers a present-but-broken
    module (syntax error, bad ref) so the two causes stay distinguishable in
    the disabled-gate observability event.
    """
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return "module_absent"
    return f"import_broken:{type(exc).__name__}"


# Set at import time in the except branches below; None while the gate is
# enabled. check_write() reads this to build the disabled-gate event (AC1).
_SCRUB_DISABLE_REASON: str | None = None


def _disabled_event_dedup_key(reason: str, utc_date: str) -> str:
    """Day-bucketed dedup key for the ``mcp_write_scrubber_disabled`` event.

    Each MCP handler does its own ``import write_scrubber``, so there is no
    single process-local flag to prevent re-emitting on every cold start
    during a multi-day outage — bucketing by UTC date instead caps the event
    at one row/day regardless of process count (AC1, #1000).
    """
    return hashlib.sha256(f"scrubber_disabled|{reason}|{utc_date}".encode()).hexdigest()


def _block_event_dedup_key(write_path: str, patterns: dict[str, int], utc_date: str) -> str:
    """Day-bucketed dedup key for the ``mcp_write_scrubber_block`` event.

    A distinct incident is a (write_path, pattern set, day) triple. Repeats of
    the *same* incident on the same UTC day collapse into one row via
    ``scrubber_block_event_upsert``'s ``payload.occurrence_count`` instead of
    inserting a new row per fire (AC2, #1000). ``sorted(patterns)`` makes the
    key order-independent — ``scan_fields``'s dict iteration order is not a
    stable identity for the incident.
    """
    pattern_key = ",".join(sorted(patterns))
    return hashlib.sha256(f"{write_path}|{pattern_key}|{utc_date}".encode()).hexdigest()


try:
    from lib.secret_scrubber import scrub, API_KEY_PATTERNS, EXTRA_PATTERN_NAMES  # type: ignore
except (ImportError, ModuleNotFoundError):
    # redrobot path: scripts/lib genuinely absent. Fail-open is intentional
    # (availability > over-blocking) but MUST be loud: a silent no-op would
    # erase the Tier-2 layer with zero operator signal. Suppressible via
    # WRITE_SCRUBBER_QUIET so repos that legitimately lack scripts/lib don't
    # print this on every cold start forever.
    scrub = None  # type: ignore
    API_KEY_PATTERNS = []  # type: ignore
    EXTRA_PATTERN_NAMES = frozenset()  # type: ignore
    _SCRUB_DISABLE_REASON = "module_absent"
    if not os.environ.get("WRITE_SCRUBBER_QUIET"):
        print(
            "[write_scrubber] WARNING: secret_scrubber unavailable (module absent) "
            "— the Tier-2 MCP write-path gate is DISABLED; writes will NOT be "
            "scanned for secrets. Set WRITE_SCRUBBER_QUIET=1 to silence (e.g. on "
            "redrobot).",
            file=sys.stderr,
        )
except Exception as exc:  # noqa: BLE001 — module FOUND but broken (syntax error, etc.)
    # On jarvis scripts/lib exists, so this branch means secret_scrubber.py
    # itself failed to import (merge-conflict marker, syntax error, bad ref).
    # Surfacing the actual error type — not the misleading "unavailable" —
    # is what tells the developer to fix the module rather than hunt a phantom
    # missing dependency. Type only (no str(exc)) to honour the privacy stance.
    scrub = None  # type: ignore
    API_KEY_PATTERNS = []  # type: ignore
    EXTRA_PATTERN_NAMES = frozenset()  # type: ignore
    _SCRUB_DISABLE_REASON = _classify_disable_reason(exc)
    print(
        "[write_scrubber] ERROR: secret_scrubber import failed — the module was "
        f"found but is broken ({type(exc).__name__}); the Tier-2 gate is DISABLED. "
        "Fix scripts/lib/secret_scrubber.py.",
        file=sys.stderr,
    )


# Patterns the scrubber detects but that must NOT hard-block an MCP write.
# `path_username` is a privacy *normalization* (scrub-and-keep), not a secret
# leak: ~26% of the live memory corpus (214/832) legitimately contains absolute
# user paths (`C:\Users\<name>\…`, `/Users/<name>/…`). Hard-rejecting those
# would violate AC#4 ("no false-positive blocks on real-world content") and
# break a quarter of all memory writes that reference a file path. Path
# normalization is the SessionEnd/Deriver lane's job (slice 6), not this
# Tier-2 secret-reject backstop. The genuine-secret patterns (API keys, env
# blocks) — 0 false positives in the corpus — remain blocking.
SCRUB_ONLY_PATTERNS = frozenset({"path_username"})

# Guard against silent string-coupling drift: SCRUB_ONLY_PATTERNS names must be
# real pattern names emitted by secret_scrubber.py. If a pattern is renamed
# there, this warns loudly at import instead of letting the frozenset become a
# no-op that starts hard-blocking every path-containing write. We warn rather
# than raise: a startup crash would take down the whole (shared) MCP server —
# disproportionate for a drift whose worst case is a functional regression
# (path writes hard-blocked), not a secret leak (fail-open). Loud-but-alive
# beats dead.
_KNOWN_PATTERN_NAMES = {name for name, _ in API_KEY_PATTERNS} | set(EXTRA_PATTERN_NAMES)
if scrub is not None and not SCRUB_ONLY_PATTERNS <= _KNOWN_PATTERN_NAMES:
    print(
        "[write_scrubber] WARNING: SCRUB_ONLY_PATTERNS references pattern name(s) "
        f"not produced by secret_scrubber: {SCRUB_ONLY_PATTERNS - _KNOWN_PATTERN_NAMES}. "
        "A rename in secret_scrubber.py disables path exclusion — those writes "
        "will now be hard-blocked. Update SCRUB_ONLY_PATTERNS in lockstep.",
        file=sys.stderr,
    )


def _iter_strings(value: object) -> Iterator[str]:
    """Yield the str values worth scanning out of a field value.

    str → itself; list/tuple → each str element; everything else (ints,
    None, dicts, floats) is skipped so non-text fields never raise.

    Depth is one level: nested lists (``[["a"]]``) are NOT descended — the
    inner list is not a str so it yields nothing. All current callers pass
    flat ``str`` / ``list[str]`` fields, so this is safe today; if a future
    caller passes nested structure it must flatten first or scanning silently
    skips the nested text.
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str):
                yield item


def scan_fields(fields: dict[str, object]) -> dict[str, int]:
    """Run the scrubber over each text field, return aggregate fire counts.

    *fields* maps a logical field name → value. Returns a dict of pattern
    name → total fire count across all fields. Empty when nothing fires (or
    when the scrubber lib is unavailable — see module docstring).

    A ``scrub()`` crash is contained per-field (logged + skipped) so a bug in
    the scrubber cannot take down every MCP write; this is fail-open, matching
    the unavailable-scrubber stance above.
    """
    if scrub is None:
        return {}
    totals: dict[str, int] = {}
    for field_name, value in fields.items():
        for text in _iter_strings(value):
            try:
                _, fires = scrub(text)
            except Exception as exc:  # noqa: BLE001 — scrubber bug must not crash writes
                # Privacy invariant: log only the exception *type* and field
                # name — never `{exc}`, whose str() could embed the input text
                # (e.g. a regex-engine error carrying match context).
                print(
                    f"[write_scrubber] scrub() raised on field {field_name!r}, "
                    f"skipped (fail-open): {type(exc).__name__}",
                    file=sys.stderr,
                )
                continue
            for name, count in fires.items():
                totals[name] = totals.get(name, 0) + count
    return totals


def rejection_error(patterns: dict[str, int]) -> dict:
    """Build the structured rejection payload.

    Carries ONLY pattern names + counts — never any payload value.

    Returns a ``dict`` (#1000 AC3) — handlers ``json.dumps()`` it themselves
    at the edge before wrapping in a ``TextContent``.
    """
    return {"error": "secret_pattern_detected", "patterns": patterns}


# High-entropy credential patterns — a fire here means a real, live-key-shaped
# secret was caught, which the orchestrator should triage above an env-block or
# (already non-blocking) path. Anything not listed maps to "medium". The block
# itself prevented the leak, so these are never "critical" (no incident
# occurred), but severity must reflect *what* was caught for triage indexing.
_HIGH_SEVERITY_PATTERNS = frozenset(
    {
        "api_key_anthropic",
        "api_key_openai",
        "api_key_aws",
        "api_key_github",
        "api_key_slack",
        # A leaked JWT is typically a Supabase service-role token — full DB
        # access, so high-sensitivity alongside the raw API keys.
        "api_key_jwt",
        # VoyageAI embedding key — a real live credential for this codebase.
        "api_key_voyageai",
    }
)


def _event_severity(patterns: dict[str, int]) -> str:
    """Map fired patterns → event severity for orchestrator triage indexing."""
    return "high" if any(p in _HIGH_SEVERITY_PATTERNS for p in patterns) else "medium"


# Serialize the audit insert: concurrent blocked/disabled-gate writes dispatch
# their events via asyncio.to_thread, which runs them on separate executor
# threads against the *same* Supabase client singleton. httpx.Client is
# generally thread-safe for concurrent requests, but the surrounding
# supabase-py query-builder is not documented as such, and a corrupted/dropped
# audit event is a security-signal loss. Each insert is a single short
# round-trip on a rare path, so serializing them behind one lock is cheap
# insurance. Shared across both event kinds — they hit the same client.
_EVENT_LOG_LOCK = threading.Lock()


def log_block_event(client, patterns: dict[str, int], *, write_path: str) -> None:
    """Best-effort: upsert an ``mcp_write_scrubber_block`` counter event.

    Records pattern names + counts only (privacy invariant). *write_path*
    identifies which handler blocked (``memory_store`` / ``record_decision``)
    so ``/learn`` can surface eager-pattern false positives. Repo slug is
    env-overridable so cross-repo (redrobot) blocks are attributed correctly.
    Severity reflects which pattern fired (see ``_event_severity``) so an
    ``sk-ant-*`` catch is not buried at the same priority as an env-block.

    Day-bucketed via ``_block_event_dedup_key`` and written through the
    ``scrubber_block_event_upsert`` RPC (mirrors the ``review_debt_upsert``
    ``on conflict (dedup_key) do update`` precedent) rather than a plain
    insert — repeats of the same incident on the same UTC day increment
    ``payload.occurrence_count`` instead of each getting their own row, which
    would otherwise flood the events table on a hot repeated-write path
    (AC2, #1000).

    Serialized via ``_EVENT_LOG_LOCK`` so concurrent ``to_thread`` dispatches
    don't drive the shared client singleton from two threads at once.
    """
    try:
        utc_date = datetime.now(timezone.utc).date().isoformat()
        dedup_key = _block_event_dedup_key(write_path, patterns, utc_date)
        with _EVENT_LOG_LOCK:
            client.rpc(
                "scrubber_block_event_upsert",
                {
                    "p_dedup_key": dedup_key,
                    "p_severity": _event_severity(patterns),
                    "p_repo": os.environ.get("JARVIS_REPO_SLUG", "Osasuwu/jarvis"),
                    "p_write_path": write_path,
                    "p_patterns": patterns,
                },
            ).execute()
    except Exception as exc:  # noqa: BLE001 — logging must never block the rejection
        # Loud-but-non-fatal: a silent pass hides "why are there no block
        # events in the table?" during debugging. Log only the exception type —
        # the row we tried to insert carries pattern names + counts, but a
        # client-layer error str() could still echo request context, so stay
        # value-free here too.
        print(
            f"[write_scrubber] block-event log failed: {type(exc).__name__}",
            file=sys.stderr,
        )


async def _log_block_event_async(client, patterns: dict[str, int], *, write_path: str) -> None:
    """Run the blocking insert off the event-loop thread.

    ``log_block_event`` does synchronous Supabase HTTP I/O. Scheduling it via
    ``create_task`` alone only defers *when* it starts — it would still run the
    50–200 ms round-trip on the loop thread and stall every other coroutine.
    ``asyncio.to_thread`` hands it to the default executor so the loop stays
    free. (The codebase's older fire-and-forget helpers — ``_emit_recall_event``
    — block the loop directly; this path is the corrected pattern.)"""
    await asyncio.to_thread(log_block_event, client, patterns, write_path=write_path)


# Strong references to in-flight block-log tasks. CPython holds only a *weak*
# reference to a task returned by asyncio.create_task; if nothing else keeps it
# alive the GC can collect it mid-run, silently dropping the insert. For a
# security audit event that is unacceptable — so we pin each task here and drop
# it on completion. (See https://docs.python.org/3/library/asyncio-task.html
# #asyncio.create_task — "Save a reference to the result of this function".)
_PENDING_BLOCK_LOGS: set[asyncio.Task] = set()


def _on_block_log_done(task: asyncio.Task) -> None:
    """Unpin a finished block-log task and surface any exception eagerly.

    Without retrieving ``task.exception()`` here, a failure inside the detached
    insert would surface only as a late, value-bearing "Task exception was never
    retrieved" warning at GC time. We log the exception *type* (privacy) and
    drop the pin.
    """
    _PENDING_BLOCK_LOGS.discard(task)
    if not task.cancelled():
        exc = task.exception()
        if exc is not None:
            print(
                f"[write_scrubber] block-log task failed: {type(exc).__name__}",
                file=sys.stderr,
            )


def _dispatch_block_log(client, patterns: dict[str, int], *, write_path: str) -> None:
    """Emit the block event off the hot path.

    Inside an async handler (a loop is running) the insert is scheduled as a
    detached task so the rejection returns immediately — the MCP event loop is
    never stalled on a 50–200 ms Supabase round-trip. The task is held in
    ``_PENDING_BLOCK_LOGS`` until done so it cannot be GC-dropped mid-insert.
    Two paths fall back to a synchronous inline insert: (1) no loop is running
    (direct unit-test calls), and (2) a loop *was* running but is now closing,
    so ``create_task`` itself raises ``RuntimeError`` during teardown. In both
    cases the audit event must still be written, so we insert inline.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        log_block_event(client, patterns, write_path=write_path)
        return
    try:
        task = asyncio.create_task(_log_block_event_async(client, patterns, write_path=write_path))
    except RuntimeError:
        # Loop is closing (teardown race) — create_task rejects. The audit event
        # is non-negotiable, so fall back to a blocking inline insert.
        log_block_event(client, patterns, write_path=write_path)
        return
    _PENDING_BLOCK_LOGS.add(task)
    task.add_done_callback(_on_block_log_done)


def log_disabled_event(client, reason: str) -> None:
    """Best-effort: upsert one ``mcp_write_scrubber_disabled`` event/day.

    Fires from ``check_write`` when the Tier-2 gate is disabled (``scrub is
    None``). Day-bucketed via ``_disabled_event_dedup_key`` so a multi-day
    outage produces one row/day across every MCP handler process, not one
    per cold start (AC1, #1000).

    Written through the ``scrubber_disabled_event_upsert`` RPC, not a plain
    ``.table("events").upsert(...)`` — ``events.dedup_key`` is a PARTIAL
    unique index (``where dedup_key is not null``), and Postgres only infers a
    partial index as the ON CONFLICT arbiter when its predicate is restated in
    the conflict target. The original plain-upsert version raised on every
    call and was silently swallowed below, so no disabled-gate event ever
    landed (code-review round-2 finding on #1000's PR). Mirrors
    ``log_block_event``'s RPC shape exactly.

    Mirrors ``log_block_event``'s "logging must never block the rejection"
    pattern too: any DB error here must not turn today's fail-*open* disabled
    state into a fail-*closed* break of every memory write, so it is swallowed
    and only the exception type is logged.
    """
    try:
        utc_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dedup_key = _disabled_event_dedup_key(reason, utc_date)
        with _EVENT_LOG_LOCK:
            client.rpc(
                "scrubber_disabled_event_upsert",
                {
                    "p_dedup_key": dedup_key,
                    "p_reason": reason,
                    "p_repo": os.environ.get("JARVIS_REPO_SLUG", "Osasuwu/jarvis"),
                },
            ).execute()
    except Exception as exc:  # noqa: BLE001 — logging must never block the write
        print(
            f"[write_scrubber] disabled-gate event log failed: {type(exc).__name__}",
            file=sys.stderr,
        )


async def _log_disabled_event_async(client, reason: str) -> None:
    """Run the blocking disabled-gate insert off the event-loop thread.

    Mirrors ``_log_block_event_async`` — see that function's docstring for why
    ``asyncio.to_thread`` (not just ``create_task``) is required.
    """
    await asyncio.to_thread(log_disabled_event, client, reason)


# Strong references to in-flight disabled-log tasks — same GC-pinning rationale
# as ``_PENDING_BLOCK_LOGS`` (see that set's docstring). Kept as a separate set
# rather than shared with ``_PENDING_BLOCK_LOGS`` so each event kind's pending
# tasks stay independently inspectable/testable.
_PENDING_DISABLED_LOGS: set[asyncio.Task] = set()


def _on_disabled_log_done(task: asyncio.Task) -> None:
    """Unpin a finished disabled-log task and surface any exception eagerly.

    Mirrors ``_on_block_log_done`` — see that function's docstring.
    """
    _PENDING_DISABLED_LOGS.discard(task)
    if not task.cancelled():
        exc = task.exception()
        if exc is not None:
            print(
                f"[write_scrubber] disabled-log task failed: {type(exc).__name__}",
                file=sys.stderr,
            )


def _dispatch_disabled_log(client, reason: str) -> None:
    """Emit the disabled-gate event off the hot path.

    Mirrors ``_dispatch_block_log`` exactly — see that function's docstring
    for the loop-detection / teardown-race rationale. ``check_write`` used to
    call ``log_disabled_event`` directly and synchronously, blocking the MCP
    event loop for the round-trip on every write made while the gate is
    disabled (code-review round-2 finding on #1000's PR).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        log_disabled_event(client, reason)
        return
    try:
        task = asyncio.create_task(_log_disabled_event_async(client, reason))
    except RuntimeError:
        log_disabled_event(client, reason)
        return
    _PENDING_DISABLED_LOGS.add(task)
    task.add_done_callback(_on_disabled_log_done)


def check_write(client, fields: dict[str, object], *, write_path: str) -> dict | None:
    """Tier-2 gate. Scan *fields*; on any **blocking** secret fire, emit the
    block event (off the event loop when one is running) and return the
    rejection dict. Return ``None`` to allow the write. Scrub-only patterns
    (see ``SCRUB_ONLY_PATTERNS``) are ignored — they are normalization
    concerns, not write-blocking leaks.

    When the gate itself is disabled (``scrub is None``), log the
    disabled-gate observability event (off the event loop when one is
    running, same as the block-event path) and fail open before reaching
    ``scan_fields`` (AC1, #1000) — ``scan_fields`` already no-ops on
    ``scrub is None``, but skipping the call makes the fail-open path
    explicit rather than incidental.
    """
    if scrub is None:
        _dispatch_disabled_log(client, _SCRUB_DISABLE_REASON)
        return None
    fires = scan_fields(fields)
    blocking = {k: v for k, v in fires.items() if k not in SCRUB_ONLY_PATTERNS}
    if not blocking:
        return None
    _dispatch_block_log(client, blocking, write_path=write_path)
    return rejection_error(blocking)

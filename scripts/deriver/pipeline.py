"""Deep module: ``derive_from_session(session_id) → list[UUID]``.

Reads the accumulator buffer, scrubs the transcript, calls the LLM
(Ollama primary → DeepSeek fallback), validates and scrubs the output,
and inserts ≤5 candidates into ``memories``.

Interface (the "small interface"):
  - ``derive_from_session(session_id, *, ...)`` — primary entry.
  - Inject ``insert_fn`` and ``llm_fn`` for testing (see tests/).

Invariants:
  - **No candidate is inserted without going through the scrubber.**
    Enforced by pipeline shape: scrub is called on output inside
    ``_build_row()``, before ``insert_fn`` is invoked.
  - **≤5 candidates per run.**  The LLM prompt caps at 5; the code
    truncates whatever the LLM returns.
  - **All rows** have ``requires_review=true`` and
    ``source_provenance='deriver:<session-id>'``.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from lib.secret_scrubber import scrub
from deriver.escalation import TierResult, derive_with_escalation

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Matches the accumulator's buffer root.
BUFFER_ROOT = Path.home() / ".claude" / ".deriver-buffer"

# Cap: never insert more than this many candidates per run.
MAX_CANDIDATES = 5

# Path to the prompt template (co-located with this file).
_PROMPT_PATH = Path(__file__).resolve().parent / "derive.md"

# Owner-self-reflection pass (#1556): non-reactive retrospective feedback
# (cherry-picking, rehearsal failure, competence, "nothing going to plan")
# that the reactive comm_patterns classifier's pair-structured rubric has
# no schema slot for. Separate prompt, separate budget — does not compete
# with MAX_CANDIDATES above.
_OWNER_SELF_PROMPT_PATH = Path(__file__).resolve().parent / "derive_owner_self.md"
OWNER_SELF_MAX_CANDIDATES = 5

# Stable hash of project root directory.  Must produce the same value as
# ``deriver-accumulator._project_hash`` so the SessionEnd hook finds the
# same buffer the accumulator wrote to.
HASH_LENGTH = 12  # first N hex chars of SHA-256


def project_hash(cwd: str) -> str:
    """Stable hash of the project root directory.

    Uses the first *HASH_LENGTH* hex chars of SHA-256 of the absolute,
    resolved cwd path.  Same project → same hash across devices (assuming
    the same clone path within the user's home), so the Deriver can find
    the buffer the accumulator wrote to.
    """
    import hashlib

    raw = os.path.realpath(cwd).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:HASH_LENGTH]


# Keyed by prompt path so multiple extraction passes can cache independently.
_PROMPT_CACHE: dict[Path, str] = {}

# JSON array extraction regex (the LLM often wraps in code fences or
# explanatory text around the JSON).
#
# Greedy on purpose: when the LLM wraps the candidates array in prose, each
# candidate has a nested `tags` array. Non-greedy `*?` stopped at the FIRST
# `]` — i.e. an inner tags array — `json.loads` then succeeded on a list of
# strings, every _validate_candidate failed, and zero candidates were
# inserted silently. Greedy extends to the OUTERMOST `]`, capturing the
# real candidates array.
_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")

# Allowed values
VALID_TYPES = {"user", "feedback"}
VALID_PROJECTS = {"jarvis", "redrobot", None}

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

InsertFn = Callable[[dict[str, Any]], UUID]
"""Signature: ``insert_fn(row) → UUID`` — persists a candidate row and
returns the new row's UUID."""

LLMFn = Callable[[str], str | None]
"""Signature: ``llm_fn(prompt) → response_text | None`` — calls an LLM."""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_prompt_template(prompt_path: Path = _PROMPT_PATH) -> str:
    if prompt_path not in _PROMPT_CACHE:
        _PROMPT_CACHE[prompt_path] = prompt_path.read_text(encoding="utf-8")
    return _PROMPT_CACHE[prompt_path]


def _render_prompt(transcript_text: str, prompt_path: Path = _PROMPT_PATH) -> str:
    template = _load_prompt_template(prompt_path)
    return template.replace("{transcript}", transcript_text)


def _read_buffer(session_id: str, project_hash: str, buffer_root: Path | None = None) -> str | None:
    """Read the accumulator buffer for *session_id*.

    Returns the concatenated transcript text, or None if the buffer file
    does not exist or is empty.
    """
    root = buffer_root or BUFFER_ROOT
    buffer_dir = root / project_hash
    buffer_path = buffer_dir / f"{session_id}.jsonl"
    if not buffer_path.exists():
        return None

    turns: list[str] = []
    with buffer_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = _extract_text(obj)
            if content:
                role = obj.get("role", "unknown")
                turns.append(f"[{role}]\n{content}")

    if not turns:
        return None
    return "\n\n".join(turns)


def _extract_text(obj: dict[str, Any]) -> str:
    """Extract human-readable text from a transcript JSON object."""
    content = obj.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content", "")
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(text, list):
                    for t in text:
                        if isinstance(t, dict) and "text" in t:
                            parts.append(t["text"])
        return "\n".join(parts)
    return ""


def _parse_json_response(raw: str) -> list[dict[str, Any]]:
    """Parse a JSON array from the LLM response.

    Handles code fences, leading/trailing text, and truncated arrays.
    Returns an empty list on parse failure.
    """
    raw = raw.strip()
    # Strip markdown code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)
    raw = raw.strip()

    # Try direct parse first
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fall back to regex extraction of first array
    m = _JSON_ARRAY_RE.search(raw)
    if not m:
        return []
    try:
        parsed = json.loads(m.group(0))
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _validate_candidate(candidate: dict[str, Any], *, forced_type: str | None = None) -> str | None:
    """Validate a single candidate dict.  Returns an error message or None.

    ``forced_type``: when a pass forces the row's ``type`` in code (see
    ``_build_row``), the candidate is not required to carry its own valid
    ``type`` field — the prompt for that pass doesn't ask the LLM for one.
    """
    if not isinstance(candidate, dict):
        return "candidate is not a dict"
    name = candidate.get("name")
    if not name or not isinstance(name, str) or not name.strip():
        return "missing or empty 'name'"
    if forced_type is None:
        typ = candidate.get("type")
        if typ not in VALID_TYPES:
            return f"invalid type: {typ!r} (valid: {sorted(VALID_TYPES)})"
    content = candidate.get("content")
    if not content or not isinstance(content, str) or not content.strip():
        return "missing or empty 'content'"
    if len(name.strip()) > 200:
        return f"name too long ({len(name.strip())} chars, max 200)"
    return None


def _normalize_project(typ: str, raw_project: Any) -> str | None:
    """Normalise the project field.

    ``user``-type candidates are always global (None).  ``feedback``-type
    candidates may be ``"jarvis"``, ``"redrobot"``, or None (cross-project).
    """
    if typ == "user":
        return None
    if raw_project in ("jarvis", "redrobot"):
        return raw_project
    return None


def _build_row(
    candidate: dict[str, Any],
    *,
    session_id: str,
    forced_tags: list[str] | None = None,
    forced_type: str | None = None,
) -> dict[str, Any] | str:
    """Build a memory row dict from a validated candidate.

    Returns the row dict on success, or an error message string on failure
    (e.g. scrub returns something the DB rejects — though scrub is pure
    string replacement, so this is a defensive catch).

    ``forced_tags``/``forced_type``: a pass-level override (e.g. the
    owner-self pass always writes ``type="feedback"`` and tags
    ``scope:owner-self``) — enforced here in code rather than trusted from
    LLM output, so a misbehaving prompt can't drop the pass's identity.
    """
    name = candidate["name"].strip()
    typ = forced_type if forced_type is not None else candidate["type"]
    raw_content = candidate.get("content", "").strip()
    raw_description = candidate.get("description", "").strip() or name
    raw_tags = candidate.get("tags", [])

    # ---- Scrubbing (mandatory before any insert) ----
    scrubbed_content, _ = scrub(raw_content)
    scrubbed_description, _ = scrub(raw_description)
    # Also scrub the name (paths, keys are unlikely in names, but defensively)
    scrubbed_name, _ = scrub(name)

    # Normalise tags. Per the module-level invariant, every text field
    # written to memories MUST pass through scrub() — including tags, which
    # the LLM can occasionally populate with paths or secret-like fragments
    # (e.g. classifier tags derived from raw transcript phrases).
    cleaned_tags: list[str] = []
    if isinstance(raw_tags, list):
        for t in raw_tags:
            if not isinstance(t, (str, int, float)):
                continue
            t_str = str(t).strip().lower()[:50]
            if not t_str:
                continue
            scrubbed_t, _ = scrub(t_str)
            scrubbed_t = scrubbed_t.strip()
            if scrubbed_t:
                cleaned_tags.append(scrubbed_t)

    # Deduplicate, preserve order, cap at 15. Forced tags (pass-level, e.g.
    # scope:owner-self) go first so they always survive the cap even if the
    # candidate supplies 15+ of its own tags.
    seen: set[str] = set()
    tags: list[str] = []
    for t in (forced_tags or []) + cleaned_tags:
        if t and t not in seen:
            seen.add(t)
            tags.append(t)
            if len(tags) >= 15:
                break

    project = _normalize_project(typ, candidate.get("project"))

    return {
        "name": scrubbed_name[:200],
        "type": typ,
        "project": project,
        "description": scrubbed_description[:500],
        "content": scrubbed_content,
        "tags": tags,
        "requires_review": True,
        "source_provenance": f"deriver:{session_id}",
        "derivation_run_id": None,  # S4 Dreamer populates this; Deriver leaves null
        "merge_targets": None,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _run_extraction_pass(
    session_id: str,
    *,
    project_hash: str,
    system_prompt: str,
    prompt_path: Path = _PROMPT_PATH,
    forced_tags: list[str] | None = None,
    forced_type: str | None = None,
    max_candidates: int = MAX_CANDIDATES,
    llm_fn: LLMFn | None = None,
    insert_fn: InsertFn | None = None,
    buffer_root: Path | None = None,
) -> list[UUID]:
    """Shared extraction-pass flow: read buffer → scrub → render prompt →
    call LLM → parse → validate+insert (≤max_candidates).

    Generalizes the single-pass flow that used to live directly in
    ``derive_from_session`` so multiple prompts (the default pass and the
    owner-self-reflection pass, #1556) can share buffer-read/scrub/parse/
    insert machinery while forcing different type/tags per pass.

    Returns:
      List of inserted candidate UUIDs (≤max_candidates).  Empty list on
      empty buffer, all-parsing-fail, or all-tiers-exhausted (defer-to-queue
      with ``events_canonical`` row).

    No exception escapes — errors are logged to stderr and the function
    returns whatever was inserted before the error.
    """
    # 1. Read buffer
    transcript = _read_buffer(session_id, project_hash, buffer_root=buffer_root)
    if transcript is None:
        print(
            f"[deriver-pipeline] no buffer for session {session_id}", file=__import__("sys").stderr
        )
        return []

    # 2. Scrub input transcript before LLM sees it
    scrubbed_transcript, _ = scrub(transcript)

    # 3. Call LLM (multi-tier escalation in production, injected fn for tests)
    prompt = _render_prompt(scrubbed_transcript, prompt_path)

    if llm_fn is not None:
        response = llm_fn(prompt)
        if response is None:
            print(
                "[deriver-pipeline] LLM returned None (both backends failed)",
                file=__import__("sys").stderr,
            )
            return []
    else:
        tier_result = derive_with_escalation(
            prompt,
            system_prompt=system_prompt,
            format_json=True,
        )
        if tier_result.text is None:
            print(
                f"[deriver-pipeline] all tiers failed (tier={tier_result.tier_completed} "
                f"model={tier_result.model}) — deferring to queue",
                file=__import__("sys").stderr,
            )
            _write_skip_event(session_id, tier_result)
            return []
        response = tier_result.text

    # 4. Parse response
    candidates = _parse_json_response(response)
    if not candidates:
        print(
            "[deriver-pipeline] LLM returned empty or unparseable response",
            file=__import__("sys").stderr,
        )
        return []

    # 5. Validate and insert (≤max_candidates)
    if insert_fn is None:
        try:
            insert_fn = _build_supabase_insert_fn()
        except Exception as e:
            print(
                f"[deriver-pipeline] failed to build Supabase insert fn: {e}",
                file=__import__("sys").stderr,
            )
            return []

    inserted: list[UUID] = []
    errors: list[str] = []

    # Two counters with different semantics:
    #   * attempted_seen — incremented for every VALID candidate we tried to
    #     insert, regardless of whether the insert itself succeeded. This is
    #     what bounds the cap so a misconfigured Supabase (all inserts fail)
    #     can't loop through 20+ candidates burning errors.
    #   * inserted (the return value) — only candidates that landed.
    # Pre-round-3 used a single counter that only incremented on success, so
    # a persistent RLS rejection turned the cap into "no cap".
    attempted_seen = 0
    for i, candidate in enumerate(candidates):
        if attempted_seen >= max_candidates:
            break
        err = _validate_candidate(candidate, forced_type=forced_type)
        if err:
            errors.append(f"candidate #{i}: {err}")
            continue

        # _build_row defensively runs scrub() on three text fields plus tags.
        # scrub() is pure regex replacement — but if a future change makes it
        # raise on pathological input, the "No exception escapes" contract in
        # this function's docstring would break. Wrap in try/except as
        # belt-and-braces.
        try:
            row = _build_row(
                candidate,
                session_id=session_id,
                forced_tags=forced_tags,
                forced_type=forced_type,
            )
        except Exception as e:
            errors.append(f"candidate #{i}: row build crashed: {e}")
            attempted_seen += 1
            continue
        if isinstance(row, str):
            errors.append(f"candidate #{i}: row build failed: {row}")
            attempted_seen += 1
            continue

        attempted_seen += 1
        try:
            uid = insert_fn(row)
            inserted.append(uid)
        except Exception as e:
            errors.append(f"candidate #{i}: insert failed: {e}")
            # Continue inserting remaining candidates (cap still enforced).
            continue

    if errors:
        print(
            f"[deriver-pipeline] {len(errors)} error(s): {'; '.join(errors)}",
            file=__import__("sys").stderr,
        )

    return inserted


def derive_from_session(
    session_id: str,
    *,
    project_hash: str,
    llm_fn: LLMFn | None = None,
    insert_fn: InsertFn | None = None,
    buffer_root: Path | None = None,
) -> list[UUID]:
    """Run the Deriver pipeline for one session.

    Parameters:
      session_id:       Session ID (from hook input).
      project_hash:     Stable hash of the project root (see
                        ``deriver-accumulator._project_hash``).
      llm_fn:           Callable ``(prompt) → text or None``.  Defaults to
                        ``derive_with_escalation`` (multi-tier: Ollama →
                        Ollama-small → DeepSeek; see
                        ``deriver.escalation``).
      insert_fn:        Callable ``(row_dict) → UUID``.  Defaults to
                        ``_insert_memory`` (writes to Supabase).
      buffer_root:      Override the buffer directory root.  Defaults to
                        ``~/.claude/.deriver-buffer``.

    Returns:
      List of inserted candidate UUIDs (≤5).  Empty list on empty buffer,
      all-parsing-fail, or all-tiers-exhausted (defer-to-queue with
      ``events_canonical`` row).

    No exception escapes — errors are logged to stderr and the function
    returns whatever was inserted before the error.
    """
    system_prompt = (
        "You are a memory-extraction assistant. "
        "Analyse the session transcript and return ONLY a JSON array of memory-worthy insights. "
        "Each object must have: type, project, name, description, content, tags."
    )
    return _run_extraction_pass(
        session_id,
        project_hash=project_hash,
        system_prompt=system_prompt,
        prompt_path=_PROMPT_PATH,
        forced_tags=None,
        forced_type=None,
        max_candidates=MAX_CANDIDATES,
        llm_fn=llm_fn,
        insert_fn=insert_fn,
        buffer_root=buffer_root,
    )


def derive_owner_self_pass(
    session_id: str,
    *,
    project_hash: str,
    llm_fn: LLMFn | None = None,
    insert_fn: InsertFn | None = None,
    buffer_root: Path | None = None,
) -> list[UUID]:
    """Run the non-reactive owner-self-reflection extraction pass (#1556).

    Separate prompt and budget from ``derive_from_session`` — surfaces
    retrospective owner feedback (cherry-picking, rehearsal failure,
    competence, "nothing going to plan") that the reactive, pair-structured
    ``comm_patterns`` classifier has no schema slot for. Rows are forced to
    ``type="feedback"`` with a ``scope:owner-self`` tag in code (see
    ``_build_row``) — never trusted from LLM output.

    Same return/error contract as ``derive_from_session``.
    """
    system_prompt = (
        "You are a memory-extraction assistant specialised in non-reactive "
        "owner self-reflection. Analyse the session transcript and return ONLY "
        "a JSON array of memory-worthy owner self-reflection insights. "
        "Each object must have: name, description, content, tags."
    )
    return _run_extraction_pass(
        session_id,
        project_hash=project_hash,
        system_prompt=system_prompt,
        prompt_path=_OWNER_SELF_PROMPT_PATH,
        forced_tags=["scope:owner-self"],
        forced_type="feedback",
        max_candidates=OWNER_SELF_MAX_CANDIDATES,
        llm_fn=llm_fn,
        insert_fn=insert_fn,
        buffer_root=buffer_root,
    )


# ---------------------------------------------------------------------------
# Defer-to-queue — events_canonical row on all-tiers-failure
# ---------------------------------------------------------------------------


def _write_skip_event(session_id: str, result: TierResult) -> None:
    """Write an ``events_canonical`` row recording the skip.

    Called when all escalation tiers are exhausted.  This is best-effort:
    if Supabase is unreachable the error is logged but not raised (the
    session end must not block on observability).

    ``events_canonical`` schema (see ``mcp-memory/schema.sql``):
      event_id (PK), trace_id, ts, actor, action, payload, outcome,
      cost_tokens, cost_usd, redacted, degraded.
    """
    import json as _json

    _root = Path(__file__).resolve().parent.parent.parent
    try:
        from dotenv import load_dotenv

        for _env in [_root / ".env", _root.parent / ".env"]:
            if _env.exists():
                load_dotenv(_env, override=True)
                break
    except Exception:
        pass

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not (url and key):
        print(
            "[deriver-pipeline] skip-event: SUPABASE_URL or SUPABASE_KEY missing — skipping events row",
            file=__import__("sys").stderr,
        )
        return

    total_tokens = result.input_tokens + result.output_tokens

    body = _json.dumps(
        {
            "trace_id": str(uuid4()),
            "actor": "deriver:sessionend",
            "action": "deriver_skip",
            "payload": {
                "session_id": session_id,
                "tier_completed": result.tier_completed,
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            },
            "outcome": "failure",
            "cost_tokens": total_tokens if total_tokens > 0 else None,
            "degraded": True,
        }
    )

    # Use stdlib urllib (no extra dependency).
    import urllib.request

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    api_url = f"{url.rstrip('/')}/rest/v1/events_canonical"
    req = urllib.request.Request(
        api_url,
        data=body.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(
            f"[deriver-pipeline] skip-event: write failed: {e}",
            file=__import__("sys").stderr,
        )


# ---------------------------------------------------------------------------
# Default Supabase insert (lazy singleton)
# ---------------------------------------------------------------------------

_SUPABASE_INSERT_FN: InsertFn | None = None


def _build_supabase_insert_fn() -> InsertFn:
    """Build a default insert function that writes to Supabase ``memories``.

    The result is cached so the Supabase client is created once per process.
    """
    global _SUPABASE_INSERT_FN
    if _SUPABASE_INSERT_FN is not None:
        return _SUPABASE_INSERT_FN

    from dotenv import load_dotenv

    _root = Path(__file__).resolve().parent.parent.parent  # scripts/deriver → scripts → repo root
    for _env in [_root / ".env", _root.parent / ".env"]:
        if _env.exists():
            load_dotenv(_env, override=True)
            break

    from supabase import create_client

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY", "")
    if not (url and key):
        raise RuntimeError(
            "Missing Supabase credentials: SUPABASE_URL and "
            "SUPABASE_SERVICE_KEY (or SUPABASE_KEY) must be set"
        )
    client = create_client(url, key)

    def _insert(row: dict[str, Any]) -> UUID:
        resp = client.table("memories").insert(row).execute()
        data = resp.data
        if not (data and len(data) > 0):
            raise RuntimeError(f"Supabase insert returned no data: {resp}")
        # Defensive .get() instead of direct subscript: PostgREST
        # `Prefer: return=minimal` (or an RLS policy stripping returned
        # columns) yields a row dict without "id". Direct `data[0]["id"]`
        # raised KeyError → outer except caught it → row reported as
        # "insert failed" but the row WAS persisted → re-run created
        # duplicates. Surface this explicitly as a deployment
        # misconfiguration instead of as a silent dup-create.
        row_id = data[0].get("id")
        if not row_id:
            raise RuntimeError(
                f"Supabase insert succeeded but returned row without 'id': {data[0]!r}"
            )
        return UUID(row_id)

    _SUPABASE_INSERT_FN = _insert
    return _SUPABASE_INSERT_FN

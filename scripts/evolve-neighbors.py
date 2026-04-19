"""Memory A-MEM evolution — Haiku neighbor-tag refresher (dry-run).

When the Phase 2 classifier applies an UPDATE decision (a candidate memory
supersedes an older target), the target's linked neighbors don't know it
happened. Their tags and descriptions were written framing `target` as a
live fact; now they describe a dead one. A-MEM (arxiv 2502.12110, §3.3)
calls this the "frozen interpretations" problem: the link graph drifts
out of sync with the fact graph.

This script is Phase 5.2-α (#230). Offline, read-only, no mutations.
It surfaces what tags/descriptions _would_ need refresh if we had an
evolution apply path. 5.2-β will add the mutation + review-queue path.

For each recent `memory_review_queue` row where `decision='UPDATE' AND
status='auto_applied'`:
  1. Loads candidate (new) + target (old, superseded)
  2. Loads 1-hop neighbors of the target via get_linked_memories RPC
     (lifecycle-filtered — dead neighbors already excluded)
  3. Asks Claude Haiku-4.5 per-neighbor: given (target → candidate) swap,
     are your tags/description stale? If yes, propose new values.
  4. Renders per-update markdown (default) or JSON (--json)
  5. Upserts a memory snapshot on --save-memory

Graceful fallback: any Haiku / httpx / parse failure → KEEP decision,
confidence=0, no action required. No neighbor is ever presented as
"needs change" unless Haiku said so explicitly.

Usage:
    python scripts/evolve-neighbors.py                     # markdown, last 10 UPDATEs
    python scripts/evolve-neighbors.py --json              # machine-readable
    python scripts/evolve-neighbors.py --since 2026-04-01  # floor on applied_at
    python scripts/evolve-neighbors.py --limit 3           # cap UPDATEs processed
    python scripts/evolve-neighbors.py --save-memory       # upsert evolution_plan_YYYY-MM-DD

Requires SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY. .env auto-loaded.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Windows cp1251 console can't encode em-dashes / arrows / Cyrillic —
# force UTF-8 so output works on all 3 devices. Safe no-op elsewhere.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv

    here = Path(__file__).resolve().parent
    for c in (here.parent / ".env", here.parent.parent / ".env"):
        if c.exists():
            # override=True: empty-string shell vars (observed in this repo's
            # login shell) don't win over the real value in .env.
            load_dotenv(c, override=True)
            break
except ImportError:
    pass

import httpx
from supabase import create_client


DEFAULT_LIMIT = 10
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_TIMEOUT = 15.0

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MAX_TOKENS = 1200
MAX_CONTENT_CHARS = 700     # truncate each memory body before sending
MAX_NEIGHBORS_PER_UPDATE = 8  # hard cap to bound Haiku cost per UPDATE

VALID_ACTIONS = ("KEEP", "UPDATE_TAGS", "UPDATE_DESC", "UPDATE_BOTH")


SYSTEM_PROMPT = """You are a memory-graph hygiene planner for a personal AI agent.

You receive:
  - OLD_MEMORY: a memory that was just marked superseded
  - NEW_MEMORY: the memory that supersedes it (the UPDATE candidate)
  - NEIGHBORS: 1-hop linked memories of OLD_MEMORY. Each has its own tags
    and description, written before the UPDATE happened. Some of those
    tags/descriptions may now be stale given the OLD → NEW swap.

For each NEIGHBOR independently, decide one of:

- KEEP: No drift. The neighbor's tags and description remain accurate
  whether OLD or NEW is the current fact. This is the default — only
  diverge when you have a clear reason.
- UPDATE_TAGS: Tags reference the old state of the world (e.g. a tag
  naming an approach the UPDATE abandoned, a status that's now wrong,
  a version tag that moved). Propose a revised tag list.
- UPDATE_DESC: Description narrates the neighbor's role using a fact
  that the UPDATE invalidated. Propose a revised one-line description.
- UPDATE_BOTH: Both of the above.

Rules:
  - Be conservative. "Same topic" is not "needs update". Only rewrite
    when the neighbor's current tags/description would mislead a reader
    who knows NEW is now the truth.
  - When proposing new tags, preserve existing ones where possible —
    do not rewrite the full tag set just to normalize style.
  - When proposing a new description, keep it one sentence, same style
    as the existing one.
  - Confidence: 0.9+ for clear cases (an old tag literally names a
    deprecated thing); 0.5-0.7 for judgment calls; <0.5 when guessing.
  - Never invent neighbor ids — you must reuse the ids shown to you.

Output strict JSON, nothing else. No prose before or after.

Schema:
{
  "proposals": [
    {
      "neighbor_id": "<uuid from input>",
      "action": "KEEP" | "UPDATE_TAGS" | "UPDATE_DESC" | "UPDATE_BOTH",
      "new_tags": ["..."] | null,            // required iff action in (UPDATE_TAGS, UPDATE_BOTH)
      "new_description": "<one sentence>" | null,  // required iff action in (UPDATE_DESC, UPDATE_BOTH)
      "confidence": <float 0..1>,
      "reasoning": "<one short sentence>"
    },
    ...
  ]
}

Emit one entry per neighbor. Preserve input order.
"""


# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------


def fetch_recent_updates(
    client, *, limit: int, since: str | None, include_seen: bool
) -> list[dict]:
    """Fetch recent Phase 2 UPDATE/auto_applied queue rows.

    `include_seen=False` is advisory — 5.2-α has no mutation, so it can't
    actually mark an update 'seen'. We keep the flag for parity with 5.1b-α
    and wire it fully in 5.2-β when the EVOLVE queue row exists.
    """
    q = (
        client.table("memory_review_queue")
        .select("id, candidate_id, target_id, applied_at, confidence, reasoning")
        .eq("decision", "UPDATE")
        .eq("status", "auto_applied")
        .order("applied_at", desc=True)
        .limit(limit)
    )
    if since:
        q = q.gte("applied_at", since)
    rows = q.execute().data or []
    # Drop rows missing either side — target can be null after an FK cascade.
    return [r for r in rows if r.get("candidate_id") and r.get("target_id")]


def fetch_memory(client, memory_id: str) -> dict | None:
    """Fetch one memory row with the fields the evolver cares about."""
    rows = (
        client.table("memories")
        .select("id, name, type, project, description, content, tags, updated_at")
        .eq("id", memory_id)
        .execute()
        .data
    ) or []
    return rows[0] if rows else None


def fetch_neighbors(client, target_id: str) -> list[dict]:
    """1-hop live neighbors of target_id via get_linked_memories RPC.

    We pass `show_history=false` — dead neighbors aren't worth evolving.
    """
    try:
        resp = client.rpc(
            "get_linked_memories",
            {
                "memory_ids": [target_id],
                "link_types": None,
                "show_history": False,
            },
        ).execute()
    except Exception as e:
        print(f"! get_linked_memories failed for {target_id}: {e}", file=sys.stderr)
        return []
    return resp.data or []


# ---------------------------------------------------------------------------
# Prompt build + parse
# ---------------------------------------------------------------------------


def _truncate(text: str | None, limit: int = MAX_CONTENT_CHARS) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit] + "…"


def _fmt_memory_block(label: str, mem: dict) -> str:
    lines = [
        f"{label}:",
        f"  id: {mem['id']}",
        f"  name: {mem['name']}",
        f"  type: {mem.get('type', '')}",
    ]
    tags = mem.get("tags") or []
    if tags:
        lines.append(f"  tags: {', '.join(tags)}")
    desc = mem.get("description") or ""
    if desc:
        lines.append(f"  description: {desc}")
    content = _truncate(mem.get("content"))
    if content:
        lines.append(f"  content: {content}")
    return "\n".join(lines)


def _fmt_neighbor_block(idx: int, n: dict) -> str:
    lines = [
        f"NEIGHBOR {idx}:",
        f"  neighbor_id: {n['id']}",
        f"  name: {n['name']}",
        f"  type: {n.get('type', '')}",
        f"  link_type: {n.get('link_type', '')}",
    ]
    tags = n.get("tags") or []
    lines.append(f"  tags: {', '.join(tags) if tags else '(none)'}")
    desc = n.get("description") or ""
    if desc:
        lines.append(f"  description: {desc}")
    content = _truncate(n.get("content"))
    if content:
        lines.append(f"  content: {content}")
    return "\n".join(lines)


def build_user_message(old: dict, new: dict, neighbors: list[dict]) -> str:
    parts = [
        _fmt_memory_block("OLD_MEMORY (just superseded)", old),
        "",
        _fmt_memory_block("NEW_MEMORY (the UPDATE)", new),
        "",
    ]
    for i, n in enumerate(neighbors, 1):
        parts.append(_fmt_neighbor_block(i, n))
        parts.append("")
    return "\n".join(parts).rstrip()


def _parse_response(text: str, neighbor_ids: set[str]) -> list[dict] | None:
    """Parse Haiku's JSON response. Returns list of per-neighbor proposals.

    Tolerant of leading/trailing prose. Each proposal is shape-checked and
    downgraded to KEEP if contradicting its own action (e.g. UPDATE_TAGS
    with new_tags=null). Unknown neighbor_ids are dropped.
    """
    if not text:
        return None
    first = text.find("{")
    last = text.rfind("}")
    if first < 0 or last <= first:
        return None
    try:
        data = json.loads(text[first : last + 1])
    except json.JSONDecodeError:
        return None

    proposals_raw = data.get("proposals")
    if not isinstance(proposals_raw, list):
        return None

    out: list[dict] = []
    for p in proposals_raw:
        if not isinstance(p, dict):
            continue
        nid = p.get("neighbor_id")
        if not isinstance(nid, str) or nid not in neighbor_ids:
            continue
        action = str(p.get("action", "")).upper().strip()
        if action not in VALID_ACTIONS:
            action = "KEEP"

        new_tags = p.get("new_tags")
        if not isinstance(new_tags, list) or not all(isinstance(t, str) for t in new_tags):
            new_tags = None
        else:
            new_tags = [t.strip() for t in new_tags if t.strip()]

        new_desc = p.get("new_description")
        if not isinstance(new_desc, str) or not new_desc.strip():
            new_desc = None
        else:
            new_desc = new_desc.strip()

        # Cross-field consistency: downgrade if action is missing its payload.
        original_action = action
        if action in ("UPDATE_TAGS", "UPDATE_BOTH") and new_tags is None:
            action = "KEEP" if action == "UPDATE_TAGS" else "UPDATE_DESC"
        if action in ("UPDATE_DESC", "UPDATE_BOTH") and new_desc is None:
            action = "KEEP" if action == "UPDATE_DESC" else "UPDATE_TAGS"

        try:
            confidence = float(p.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        raw_reasoning = p.get("reasoning")
        reasoning = (raw_reasoning if isinstance(raw_reasoning, str) else "").strip()[:500]
        if action != original_action:
            note = f"downgraded from {original_action} (payload missing)"
            reasoning = f"{note}: {reasoning}" if reasoning else note

        out.append(
            {
                "neighbor_id": nid,
                "action": action,
                "new_tags": new_tags if action in ("UPDATE_TAGS", "UPDATE_BOTH") else None,
                "new_description": new_desc
                if action in ("UPDATE_DESC", "UPDATE_BOTH")
                else None,
                "confidence": round(confidence, 3),
                "reasoning": reasoning,
            }
        )
    return out


def _fallback_keep(neighbors: list[dict], why: str) -> list[dict]:
    """Return KEEP for every neighbor — safe no-op fallback."""
    return [
        {
            "neighbor_id": n["id"],
            "action": "KEEP",
            "new_tags": None,
            "new_description": None,
            "confidence": 0.0,
            "reasoning": f"fallback: {why}",
        }
        for n in neighbors
    ]


# ---------------------------------------------------------------------------
# Haiku call
# ---------------------------------------------------------------------------


def call_haiku(
    old: dict, new: dict, neighbors: list[dict], *, model: str, timeout: float
) -> list[dict]:
    """Plan evolution for one (old → new, neighbors) triple. See _parse_response."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_keep(neighbors, "ANTHROPIC_API_KEY missing")
    if not neighbors:
        return []

    body = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": build_user_message(old, new, neighbors)}],
    }

    try:
        with httpx.Client(timeout=timeout) as http:
            resp = http.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as e:
        return _fallback_keep(neighbors, f"http_error: {type(e).__name__}")
    except ValueError:
        return _fallback_keep(neighbors, "invalid_json_payload")

    blocks = payload.get("content", [])
    text = ""
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text":
            text = b.get("text", "")
            break

    parsed = _parse_response(text, {n["id"] for n in neighbors})
    if parsed is None:
        return _fallback_keep(neighbors, "unparseable_response")

    # Fill in KEEP for any neighbor Haiku silently dropped — we always
    # return one row per input neighbor so downstream rendering is regular.
    seen = {p["neighbor_id"] for p in parsed}
    for n in neighbors:
        if n["id"] not in seen:
            parsed.append(
                {
                    "neighbor_id": n["id"],
                    "action": "KEEP",
                    "new_tags": None,
                    "new_description": None,
                    "confidence": 0.0,
                    "reasoning": "haiku omitted — default KEEP",
                }
            )
    # Preserve original neighbor order for rendering stability.
    order = {n["id"]: i for i, n in enumerate(neighbors)}
    parsed.sort(key=lambda p: order.get(p["neighbor_id"], 999))
    return parsed


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def render_markdown(results: list[dict], *, model: str, limit: int) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_neighbors = sum(len(r["proposals"]) for r in results)
    by_action: dict[str, int] = defaultdict(int)
    for r in results:
        for p in r["proposals"]:
            by_action[p["action"]] += 1

    lines = [
        f"# Memory A-MEM evolution plan — {now}",
        "",
        f"- Model: `{model}`",
        f"- UPDATE decisions processed: **{len(results)}** (cap: {limit})",
        f"- Neighbors evaluated: {total_neighbors}",
        f"- Actions: KEEP={by_action.get('KEEP', 0)}, "
        f"UPDATE_TAGS={by_action.get('UPDATE_TAGS', 0)}, "
        f"UPDATE_DESC={by_action.get('UPDATE_DESC', 0)}, "
        f"UPDATE_BOTH={by_action.get('UPDATE_BOTH', 0)}",
        "",
        "_Dry-run only. No writes to `memories`. Apply path ships in 5.2-β._",
        "",
    ]

    if not results:
        lines.append("_No recent UPDATE/auto_applied rows. Nothing to evolve._")
        return "\n".join(lines)

    for r in results:
        old, new = r["old_memory"], r["new_memory"]
        lines.append(
            f"## UPDATE `{old['name']}` → `{new['name']}` "
            f"(queue {r['queue_id'][:8]}, {r['applied_at'][:10]})"
        )
        lines.append("")
        lines.append(
            f"- Old: `{old['name']}` ({old.get('type', '')}), tags: "
            f"{', '.join(old.get('tags') or []) or '_none_'}"
        )
        lines.append(
            f"- New: `{new['name']}` ({new.get('type', '')}), tags: "
            f"{', '.join(new.get('tags') or []) or '_none_'}"
        )
        lines.append("")
        if not r["proposals"]:
            lines.append("_No linked neighbors. Nothing to evaluate._")
            lines.append("")
            continue
        lines.append("| Neighbor | Action | Conf | Reasoning |")
        lines.append("|---|---|---|---|")
        name_by_id = {n["id"]: n for n in r["neighbors"]}
        for p in r["proposals"]:
            n = name_by_id.get(p["neighbor_id"], {})
            name = n.get("name", p["neighbor_id"][:8])
            reasoning = (
                (p.get("reasoning") or "_(empty)_")
                .replace("\r\n", " ")
                .replace("\n", " ")
                .replace("|", "\\|")
            )
            lines.append(
                f"| `{name}` | **{p['action']}** | {p['confidence']:.2f} | {reasoning} |"
            )
        lines.append("")
        # Detail block for non-KEEP proposals
        actionable = [p for p in r["proposals"] if p["action"] != "KEEP"]
        if actionable:
            lines.append("### Proposed changes")
            lines.append("")
            for p in actionable:
                n = name_by_id.get(p["neighbor_id"], {})
                lines.append(f"**`{n.get('name', p['neighbor_id'])}`** — {p['action']}")
                if p.get("new_tags") is not None:
                    old_tags = ", ".join(n.get("tags") or []) or "_none_"
                    new_tags = ", ".join(p["new_tags"]) or "_none_"
                    lines.append(f"- tags: `{old_tags}` → `{new_tags}`")
                if p.get("new_description") is not None:
                    old_desc = (n.get("description") or "_none_").replace("`", "'")
                    new_desc = p["new_description"].replace("`", "'")
                    lines.append(f"- description:")
                    lines.append(f"  - old: {old_desc}")
                    lines.append(f"  - new: {new_desc}")
                lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "**Next**: 5.2-β will add `EVOLVE` to `memory_review_queue.decision`, "
        "route high-confidence proposals to an apply RPC, and queue the rest."
    )
    return "\n".join(lines)


def save_plan_memory(client, plan_md: str, results: list[dict]) -> None:
    """Upsert as `evolution_plan_YYYY-MM-DD`, type=project.

    Parallel to `save_plan_memory` in consolidation-merge-plan.py.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    name = f"evolution_plan_{today}"
    by_action: dict[str, int] = defaultdict(int)
    for r in results:
        for p in r["proposals"]:
            by_action[p["action"]] += 1
    total_neighbors = sum(by_action.values())
    description = (
        f"Evolution plan {today}: {len(results)} UPDATEs × {total_neighbors} neighbors. "
        f"KEEP={by_action.get('KEEP', 0)}, "
        f"UPDATE_TAGS={by_action.get('UPDATE_TAGS', 0)}, "
        f"UPDATE_DESC={by_action.get('UPDATE_DESC', 0)}, "
        f"UPDATE_BOTH={by_action.get('UPDATE_BOTH', 0)}. "
        "Haiku dry-run (Phase 5.2-α)."
    )
    existing = (
        client.table("memories")
        .select("id")
        .eq("project", "jarvis")
        .eq("name", name)
        .is_("deleted_at", "null")
        .execute()
        .data
    )
    payload = {
        "project": "jarvis",
        "name": name,
        "type": "project",
        "description": description,
        "content": plan_md,
        "tags": ["memory", "evolution", "a-mem", "phase-5", "haiku-plan"],
        "source_provenance": "skill:evolution",
    }
    if existing:
        client.table("memories").update(payload).eq("id", existing[0]["id"]).execute()
        print(f"Updated memory `{name}` (id={existing[0]['id']})", file=sys.stderr)
    else:
        client.table("memories").insert(payload).execute()
        print(f"Inserted memory `{name}`", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Max UPDATE decisions processed per run (default {DEFAULT_LIMIT})",
    )
    p.add_argument(
        "--since",
        type=str,
        default=None,
        help="ISO date floor on applied_at, e.g. 2026-04-01",
    )
    p.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Anthropic model id (default {DEFAULT_MODEL})"
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Per-UPDATE API timeout seconds (default {DEFAULT_TIMEOUT})",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    p.add_argument(
        "--save-memory",
        action="store_true",
        help="Upsert the plan as a Jarvis memory (`evolution_plan_YYYY-MM-DD`)",
    )
    p.add_argument(
        "--include-seen",
        action="store_true",
        help="Reserved for 5.2-β (EVOLVE queue dedup). 5.2-α has no mutation — flag is a no-op.",
    )
    args = p.parse_args()

    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_KEY")
    if not sb_url or not sb_key:
        print("SUPABASE_URL / SUPABASE_KEY missing from env", file=sys.stderr)
        return 2
    # ANTHROPIC_API_KEY is NOT a hard requirement: call_haiku() falls back to
    # a KEEP-only plan when the key is absent, matching the documented fallback
    # contract. We still warn so a misconfigured run is visible.
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY missing — emitting KEEP-only fallback plan",
            file=sys.stderr,
        )

    client = create_client(sb_url, sb_key)

    updates = fetch_recent_updates(
        client, limit=args.limit, since=args.since, include_seen=args.include_seen
    )
    if not updates:
        if args.json:
            print(
                json.dumps(
                    {
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "model": args.model,
                        "results": [],
                    },
                    indent=2,
                )
            )
        else:
            print(render_markdown([], model=args.model, limit=args.limit))
        return 0

    print(f"Planning evolution for {len(updates)} UPDATE(s) with {args.model}...",
          file=sys.stderr)

    results: list[dict] = []
    for i, row in enumerate(updates, 1):
        cand = fetch_memory(client, row["candidate_id"])
        tgt = fetch_memory(client, row["target_id"])
        if not cand or not tgt:
            print(f"  [{i}/{len(updates)}] skipped: missing candidate/target rows",
                  file=sys.stderr)
            continue
        neighbors = fetch_neighbors(client, row["target_id"])[:MAX_NEIGHBORS_PER_UPDATE]
        print(
            f"  [{i}/{len(updates)}] {tgt['name']} → {cand['name']} "
            f"({len(neighbors)} neighbors)...",
            file=sys.stderr,
        )
        proposals = call_haiku(
            tgt, cand, neighbors, model=args.model, timeout=args.timeout
        )
        results.append(
            {
                "queue_id": row["id"],
                "applied_at": row["applied_at"],
                "old_memory": tgt,
                "new_memory": cand,
                "neighbors": neighbors,
                "proposals": proposals,
            }
        )

    if args.json:
        out = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": args.model,
            "limit": args.limit,
            "since": args.since,
            "results": results,
        }
        print(json.dumps(out, indent=2, default=str))
    else:
        md = render_markdown(results, model=args.model, limit=args.limit)
        print(md)
        if args.save_memory:
            save_plan_memory(client, md, results)

    return 0


if __name__ == "__main__":
    sys.exit(main())

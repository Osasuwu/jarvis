"""Memory consolidation — Haiku merge-plan generator (dry-run).

Takes the clusters that `scripts/consolidation-report.py` surfaces
and asks Claude Haiku-4.5 to emit one of:

    MERGE         — members hold partial views of the same fact; synthesize
                    a new canonical memory combining them
    SUPERSEDE     — one member is current/correct, others are stale; mark
                    the stale ones expired
    KEEP_DISTINCT — same topic but different purposes; leave them alone

**Dry-run only.** No mutations, no --apply flag. Phase 5.1b-β will add
the apply path with confidence gating + review queue.

Output: markdown report (default) or JSON. `--save-memory` upserts the
markdown as `consolidation_plan_YYYY-MM-DD` (`type=project`).

The Haiku call follows the same pattern as `mcp-memory/classifier.py`
(httpx, tolerant JSON parse, graceful fallback to KEEP_DISTINCT on
network/parse failure). No SDK dependency.

Usage:
    python scripts/consolidation-merge-plan.py                       # markdown
    python scripts/consolidation-merge-plan.py --json                # machine-readable
    python scripts/consolidation-merge-plan.py --min-size 3 --threshold 0.80
    python scripts/consolidation-merge-plan.py --save-memory

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


DEFAULT_MIN_SIZE = 3
DEFAULT_THRESHOLD = 0.80
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_TIMEOUT = 15.0  # per-cluster; clusters are larger than single-write classifier

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MAX_TOKENS = 1500  # room for canonical_content on MERGE
MAX_MEMBER_CONTENT_CHARS = 800  # truncate long memories before sending

VALID_DECISIONS = ("MERGE", "SUPERSEDE", "KEEP_DISTINCT")


SYSTEM_PROMPT = """You are a memory-consolidation planner for a personal AI agent's long-term memory store.

You receive a CLUSTER of memories that are semantically similar (cosine similarity above threshold). Decide one of:

- MERGE: Members hold partial, complementary views of the same underlying fact. A unified memory would serve strictly better than the parts. Synthesize canonical_name, canonical_description, canonical_content combining the best information from all members.
- SUPERSEDE: One member is the current/correct version; the others are stale, wrong, or incomplete and should be marked expired. Pick canonical_id from the existing members.
- KEEP_DISTINCT: Members cover the same topic but serve different purposes (e.g., reflection + results + status of the same event; decisions in the same area with different scope; notes from different dates). Leave them alone.

Rules:
  - Different types (user vs project vs decision) usually mean KEEP_DISTINCT — the type carries semantic meaning.
  - Different dates or events referenced inside the content → lean KEEP_DISTINCT. Only MERGE/SUPERSEDE if they genuinely refer to the same fact.
  - Supersession requires evidence that one is both newer AND more correct. Not just more recent.
  - Merging should produce a memory strictly better than any single member. If the members are already useful individually, prefer KEEP_DISTINCT.
  - Be conservative. When in doubt, KEEP_DISTINCT.
  - Confidence: 0.9+ for unambiguous cases; 0.5-0.7 for judgment calls; <0.5 when guessing.

Output strict JSON, nothing else. No prose before or after.

Schema:
{
  "decision": "MERGE" | "SUPERSEDE" | "KEEP_DISTINCT",
  "canonical_id": "<uuid of winning member>" | null,
  "supersede_ids": ["<uuid>", ...],
  "canonical_name": "<snake_case identifier>" | null,
  "canonical_description": "<one sentence summary>" | null,
  "canonical_content": "<full merged content>" | null,
  "confidence": <float 0..1>,
  "reasoning": "<one short sentence>"
}

Field rules by decision:
  - MERGE: canonical_id = null; canonical_name / description / content REQUIRED; supersede_ids = ALL cluster member ids.
  - SUPERSEDE: canonical_id = id of the winning member; canonical_* may be null; supersede_ids = the other ids (not including the winner).
  - KEEP_DISTINCT: canonical_id = null; canonical_* = null; supersede_ids = [].
"""


def fetch_clusters(client, min_size: int, threshold: float) -> list[dict]:
    """Call find_consolidation_clusters RPC."""
    resp = client.rpc(
        "find_consolidation_clusters",
        {"min_cluster_size": min_size, "sim_threshold": threshold},
    ).execute()
    return resp.data or []


def fetch_member_details(client, memory_ids: list[str]) -> dict[str, dict]:
    """Fetch full details (description, tags, content, lifecycle) for Haiku input."""
    if not memory_ids:
        return {}
    rows = (
        client.table("memories")
        .select(
            "id, name, type, description, tags, content, "
            "expired_at, valid_to, superseded_by, deleted_at, "
            "updated_at, content_updated_at"
        )
        .in_("id", memory_ids)
        .execute()
        .data
    )
    return {r["id"]: r for r in rows}


def _parse_ts(ts) -> datetime | None:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def is_live(row: dict) -> bool:
    """Phase 1 live-filter (kept in sync with server.py `_hybrid_recall`).

    RPC already filters at SQL source (Phase 5.1c), so this is a defensive
    no-op against current DB revs.
    """
    if row.get("expired_at") is not None:
        return False
    if row.get("superseded_by") is not None:
        return False
    if row.get("deleted_at") is not None:
        return False
    valid_to = _parse_ts(row.get("valid_to"))
    if valid_to is not None and valid_to <= datetime.now(timezone.utc):
        return False
    return True


def _truncate(text: str, limit: int = MAX_MEMBER_CONTENT_CHARS) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit] + "…"


def group_clusters(rpc_rows: list[dict], details_by_id: dict[str, dict]) -> list[dict]:
    """Re-group RPC rows by cluster_id, drop dead memories, dedupe by id.

    Content is truncated at `MAX_MEMBER_CONTENT_CHARS` — it's what Haiku will
    see and what ends up in `--json` output; keeping full text on every
    cluster member bloats output for large memories with no benefit.
    """
    by_cluster: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in rpc_rows:
        mid = r["memory_id"]
        details = details_by_id.get(mid)
        if details is None or not is_live(details):
            continue
        sim = float(r["similarity"])
        existing = by_cluster[r["cluster_id"]].get(mid)
        if existing and existing["similarity"] >= sim:
            continue
        by_cluster[r["cluster_id"]][mid] = {
            "id": mid,
            "name": r["memory_name"],
            "type": r["memory_type"],
            "similarity": sim,
            "updated_at": r["updated_at"],
            "description": details.get("description") or "",
            "tags": details.get("tags") or [],
            "content": _truncate(details.get("content") or ""),
        }

    clusters: list[dict] = []
    for cid, by_id in by_cluster.items():
        members = sorted(by_id.values(), key=lambda m: m["updated_at"], reverse=True)
        max_sim = max(m["similarity"] for m in members)
        clusters.append({
            "cluster_id": cid,
            "size": len(members),
            "max_similarity": round(max_sim, 4),
            "types": sorted({m["type"] for m in members}),
            "members": members,
        })
    clusters.sort(key=lambda c: (c["size"], c["max_similarity"]), reverse=True)
    return clusters


def _build_user_message(cluster: dict) -> str:
    lines = [
        f"CLUSTER {cluster['cluster_id']} — {cluster['size']} members, "
        f"max_similarity={cluster['max_similarity']:.3f}, types={', '.join(cluster['types'])}",
        "",
        "MEMBERS:",
    ]
    for m in cluster["members"]:
        block = [
            f"- id: {m['id']}",
            f"  name: {m['name']}",
            f"  type: {m['type']}",
            f"  updated_at: {m['updated_at']}",
            f"  similarity_to_cluster: {m['similarity']:.3f}",
        ]
        if m.get("tags"):
            block.append(f"  tags: {', '.join(m['tags'])}")
        if m.get("description"):
            block.append(f"  description: {m['description']}")
        if m.get("content"):
            block.append(f"  content: {_truncate(m['content'])}")
        lines.append("\n".join(block))
    return "\n".join(lines)


def _parse_response(text: str, member_ids: list[str]) -> dict | None:
    """Parse Haiku's JSON reply. Tolerant of leading/trailing prose.

    Validates against member_ids so the model can't invent UUIDs.
    Returns None on any unrecoverable issue; caller falls back to KEEP_DISTINCT.
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

    decision = str(data.get("decision", "")).upper().strip()
    if decision not in VALID_DECISIONS:
        return None

    member_set = set(member_ids)

    canonical_id = data.get("canonical_id")
    if canonical_id in ("", "null", None):
        canonical_id = None
    elif not isinstance(canonical_id, str) or canonical_id not in member_set:
        # Model invented an ID or returned non-string. For SUPERSEDE this is
        # fatal; for other decisions we can null it out.
        if decision == "SUPERSEDE":
            return None
        canonical_id = None

    supersede_ids_raw = data.get("supersede_ids") or []
    if not isinstance(supersede_ids_raw, list):
        supersede_ids_raw = []
    supersede_ids = [s for s in supersede_ids_raw if isinstance(s, str) and s in member_set]

    # Cross-field consistency checks — downgrade to KEEP_DISTINCT with low
    # confidence if Haiku contradicts its own decision, rather than silently
    # trusting garbage. These checks run BEFORE invariant normalization so
    # the downgrade reason reflects what Haiku actually said.
    if decision == "SUPERSEDE" and canonical_id is None:
        return _downgrade(data, "SUPERSEDE without canonical_id")
    if decision == "MERGE":
        name = data.get("canonical_name")
        content = data.get("canonical_content")
        if not (isinstance(name, str) and name.strip()) or not (isinstance(content, str) and content.strip()):
            return _downgrade(data, "MERGE missing canonical_name or canonical_content")

    # Enforce schema invariants — the model's output is advisory; downstream
    # consumers (plan renderer, upcoming 5.1b-β --apply) rely on these
    # invariants rather than trusting that Haiku filled every field
    # consistently with its chosen decision.
    if decision == "MERGE":
        # All members get superseded by the new canonical; no existing id wins.
        canonical_id = None
        supersede_ids = sorted(member_set)
    elif decision == "SUPERSEDE":
        # Exactly one winner from the existing set; every other member loses.
        # Derive supersede_ids deterministically so Haiku can't "forget" a loser.
        supersede_ids = sorted(member_set - {canonical_id})
    else:  # KEEP_DISTINCT
        canonical_id = None
        supersede_ids = []

    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    reasoning = str(data.get("reasoning", "")).strip()[:500]

    return {
        "decision": decision,
        "canonical_id": canonical_id,
        "supersede_ids": supersede_ids,
        "canonical_name": (data.get("canonical_name") or None) if decision == "MERGE" else None,
        "canonical_description": (data.get("canonical_description") or None) if decision == "MERGE" else None,
        "canonical_content": (data.get("canonical_content") or None) if decision == "MERGE" else None,
        "confidence": confidence,
        "reasoning": reasoning,
    }


def _downgrade(data: dict, why: str) -> dict:
    """Return a safe KEEP_DISTINCT with low confidence + note."""
    original_reasoning = str(data.get("reasoning", "")).strip()[:300]
    note = f"downgraded ({why})"
    if original_reasoning:
        note = f"{note}: {original_reasoning}"
    return {
        "decision": "KEEP_DISTINCT",
        "canonical_id": None,
        "supersede_ids": [],
        "canonical_name": None,
        "canonical_description": None,
        "canonical_content": None,
        "confidence": 0.2,
        "reasoning": note,
    }


def _fallback_keep_distinct(why: str) -> dict:
    """When the API call itself fails — default to safe no-op."""
    return {
        "decision": "KEEP_DISTINCT",
        "canonical_id": None,
        "supersede_ids": [],
        "canonical_name": None,
        "canonical_description": None,
        "canonical_content": None,
        "confidence": 0.0,
        "reasoning": f"fallback: {why}",
    }


def plan_cluster(cluster: dict, *, model: str, timeout: float) -> dict:
    """Call Haiku for one cluster. Returns a plan dict (see _parse_response).

    On any API/parse error returns a KEEP_DISTINCT fallback with confidence=0
    so the caller (and ultimately 5.1b-β --apply) never acts on garbage.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_keep_distinct("ANTHROPIC_API_KEY missing")

    body = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": _build_user_message(cluster)}],
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
        return _fallback_keep_distinct(f"http_error: {type(e).__name__}")
    except ValueError:
        return _fallback_keep_distinct("invalid_json_payload")

    blocks = payload.get("content", [])
    text = ""
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text":
            text = b.get("text", "")
            break

    member_ids = [m["id"] for m in cluster["members"]]
    parsed = _parse_response(text, member_ids)
    if parsed is None:
        return _fallback_keep_distinct("unparseable_response")
    return parsed


def render_markdown(clusters: list[dict], plans: list[dict], min_size: int, threshold: float, model: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    by_decision: dict[str, int] = defaultdict(int)
    for p in plans:
        by_decision[p["decision"]] += 1

    lines = [
        f"# Memory consolidation plan — {now}",
        "",
        f"- RPC: `find_consolidation_clusters(min_cluster_size={min_size}, sim_threshold={threshold})`",
        f"- Model: `{model}`",
        f"- Clusters planned: **{len(clusters)}**",
        f"- Decisions: MERGE={by_decision.get('MERGE', 0)}, "
        f"SUPERSEDE={by_decision.get('SUPERSEDE', 0)}, "
        f"KEEP_DISTINCT={by_decision.get('KEEP_DISTINCT', 0)}",
        "",
        "_Dry-run only. No mutations. Apply path lands in 5.1b-β with confidence gating._",
        "",
    ]

    if not clusters:
        lines.append("_No live clusters above threshold. Nothing to plan._")
        return "\n".join(lines)

    id_to_name = {m["id"]: m["name"] for c in clusters for m in c["members"]}

    for cluster, plan in zip(clusters, plans):
        lines.append(
            f"## Cluster {cluster['cluster_id']} — {plan['decision']} "
            f"(confidence {plan['confidence']:.2f})"
        )
        lines.append("")
        lines.append(f"**Reasoning:** {plan['reasoning'] or '_(empty)_'}")
        lines.append("")
        lines.append(
            f"Members ({cluster['size']}, max_sim {cluster['max_similarity']:.3f}, "
            f"types: {', '.join(cluster['types'])}):"
        )
        for m in cluster["members"]:
            marker = ""
            if plan["decision"] == "SUPERSEDE":
                if m["id"] == plan["canonical_id"]:
                    marker = " **[CANONICAL]**"
                elif m["id"] in plan["supersede_ids"]:
                    marker = " **[SUPERSEDE]**"
            elif plan["decision"] == "MERGE" and m["id"] in plan["supersede_ids"]:
                marker = " **[MERGE→archived]**"
            lines.append(f"- `{m['name']}` ({m['type']}, updated {m['updated_at'][:10]}){marker}")
        lines.append("")

        if plan["decision"] == "MERGE":
            lines.append(f"**Canonical name:** `{plan['canonical_name']}`")
            lines.append("")
            if plan.get("canonical_description"):
                lines.append(f"**Canonical description:** {plan['canonical_description']}")
                lines.append("")
            if plan.get("canonical_content"):
                lines.append("**Canonical content:**")
                lines.append("")
                lines.append("```")
                lines.append(plan["canonical_content"])
                lines.append("```")
                lines.append("")
        elif plan["decision"] == "SUPERSEDE":
            winner_name = id_to_name.get(plan["canonical_id"], plan["canonical_id"])
            lines.append(f"**Keep:** `{winner_name}`")
            lines.append("")
            if plan["supersede_ids"]:
                loser_names = [id_to_name.get(i, i) for i in plan["supersede_ids"]]
                lines.append(f"**Expire:** {', '.join(f'`{n}`' for n in loser_names)}")
                lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("**Next**: review plans; 5.1b-β will add `--apply` with a confidence threshold (≥ 0.9) and a review queue for the rest.")
    return "\n".join(lines)


def save_plan_memory(client, plan_md: str, plans: list[dict]) -> None:
    """Upsert as `consolidation_plan_YYYY-MM-DD`, type=project.

    Parallel to `save_report_memory` in consolidation-report.py but with a
    distinct name so the plan and the raw report don't collide.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    name = f"consolidation_plan_{today}"
    by_decision: dict[str, int] = defaultdict(int)
    for p in plans:
        by_decision[p["decision"]] += 1
    description = (
        f"Consolidation plan {today}: "
        f"{by_decision.get('MERGE', 0)} MERGE, "
        f"{by_decision.get('SUPERSEDE', 0)} SUPERSEDE, "
        f"{by_decision.get('KEEP_DISTINCT', 0)} KEEP_DISTINCT. "
        "Haiku dry-run (Phase 5.1b-α)."
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
        "tags": ["memory", "consolidation", "phase-5", "haiku-plan"],
        "source_provenance": "skill:consolidation",
    }
    if existing:
        client.table("memories").update(payload).eq("id", existing[0]["id"]).execute()
        print(f"Updated memory `{name}` (id={existing[0]['id']})", file=sys.stderr)
    else:
        client.table("memories").insert(payload).execute()
        print(f"Inserted memory `{name}`", file=sys.stderr)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--min-size", type=int, default=DEFAULT_MIN_SIZE,
                   help=f"Minimum cluster size (default {DEFAULT_MIN_SIZE})")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                   help=f"Cosine similarity threshold (default {DEFAULT_THRESHOLD})")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Anthropic model id (default {DEFAULT_MODEL})")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                   help=f"Per-cluster API timeout seconds (default {DEFAULT_TIMEOUT})")
    p.add_argument("--json", action="store_true",
                   help="Emit JSON instead of markdown")
    p.add_argument("--save-memory", action="store_true",
                   help="Upsert the plan as a Jarvis memory (`consolidation_plan_YYYY-MM-DD`)")
    args = p.parse_args()

    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_KEY")
    if not sb_url or not sb_key:
        print("SUPABASE_URL / SUPABASE_KEY missing from env", file=sys.stderr)
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing from env", file=sys.stderr)
        return 2

    client = create_client(sb_url, sb_key)

    rpc_rows = fetch_clusters(client, args.min_size, args.threshold)
    ids = sorted({r["memory_id"] for r in rpc_rows})
    details_by_id = fetch_member_details(client, ids)

    clusters = group_clusters(rpc_rows, details_by_id)
    clusters = [c for c in clusters if c["size"] >= args.min_size]

    if not clusters:
        if args.json:
            print(json.dumps({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "params": {"min_size": args.min_size, "threshold": args.threshold},
                "model": args.model,
                "clusters": [],
                "plans": [],
            }, indent=2))
        else:
            print(render_markdown([], [], args.min_size, args.threshold, args.model))
        return 0

    print(f"Planning {len(clusters)} cluster(s) with {args.model}...", file=sys.stderr)
    plans = []
    for i, cluster in enumerate(clusters, 1):
        print(f"  [{i}/{len(clusters)}] cluster {cluster['cluster_id']} "
              f"({cluster['size']} members)...", file=sys.stderr)
        plans.append(plan_cluster(cluster, model=args.model, timeout=args.timeout))

    if args.json:
        out = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "params": {"min_size": args.min_size, "threshold": args.threshold},
            "model": args.model,
            "clusters": clusters,
            "plans": plans,
        }
        print(json.dumps(out, indent=2, default=str))
    else:
        md = render_markdown(clusters, plans, args.min_size, args.threshold, args.model)
        print(md)
        if args.save_memory:
            save_plan_memory(client, md, plans)

    return 0


if __name__ == "__main__":
    sys.exit(main())

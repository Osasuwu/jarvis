"""Memory recall evaluation harness.

Runs the query set in tests/memory-eval/queries.yaml against the live Supabase
corpus, reproduces the server.py recall pipeline (pgvector match_memories +
pg_trgm keyword_search_memories + RRF + temporal scoring), and reports:

    - recall@5, recall@10:  fraction of queries where >=1 expected name is in top-k
    - MRR:                  mean reciprocal rank of the first expected hit
    - must_not violations:  queries where a "should not surface" memory landed
                            in top 5 (tracked separately — this is the lifecycle
                            signal we want to drive to zero)

Usage:
    python scripts/eval-recall.py                 # run, pretty-print, don't save
    python scripts/eval-recall.py --save-baseline # run + overwrite baseline.json
    python scripts/eval-recall.py --diff baseline # run + print delta vs baseline.json
    python scripts/eval-recall.py --quiet         # only print aggregates

No dependency on mcp-memory/server.py: we duplicate the pipeline constants here
so Phase-by-phase server.py changes are measurable as deltas against the
previous baseline. Keep this file's constants in sync with server.py OR, when
pipeline diverges intentionally, the delta in eval output *is* the thing we
wanted to measure.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Pipeline constants — mirrored from mcp-memory/server.py as of Phase 1.
# When server.py changes, re-sync OR deliberately let them differ to measure.
# ---------------------------------------------------------------------------
SIMILARITY_THRESHOLD = 0.25
RRF_K = 60
# TYPE_BOOST_MULTIPLIER intentionally not duplicated here. When --with-rewriter
# is enabled, we load scripts/memory-recall-hook.py and read its constant,
# so re-tuning the boost only needs to happen in one place.
TEMPORAL_HALF_LIVES = {
    "user": 180,
    "feedback": 90,
    "decision": 60,
    "reference": 30,
    "project": 7,
}
DEFAULT_HALF_LIFE = 30
ACCESS_BOOST_MAX = 0.3
ACCESS_HALF_LIFE = 14

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3-lite"
EMBED_TIMEOUT = 10.0


def _load_hook_module():
    """Load scripts/memory-recall-hook.py as a module via importlib.

    Hyphen in the hook filename blocks normal imports. Returning the whole
    module lets callers pull both `rewrite_prompt` and `TYPE_BOOST_MULTIPLIER`
    from the same source — eval and hook stay in lockstep when the boost is
    re-tuned. Returns None if the file is missing or import fails.
    """
    here = Path(__file__).resolve().parent
    hook_path = here / "memory-recall-hook.py"
    if not hook_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("memory_recall_hook", hook_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        print(f"WARN: failed to load hook module: {e}", file=sys.stderr)
        return None


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / ".env", here.parent.parent / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
            return


async def _embed_query(text: str) -> list[float]:
    """Sync-in-async Voyage embed. Raises on error — eval should fail loud, not open."""
    import httpx

    api_key = os.environ["VOYAGE_API_KEY"]
    async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
        resp = await client.post(
            VOYAGE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": VOYAGE_MODEL,
                "input": [text],
                "input_type": "query",
            },
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


def _rrf_merge(
    semantic_rows: list[dict],
    keyword_rows: list[dict],
    limit: int,
    k: int = RRF_K,
    boost_types: set[str] | None = None,
    boost_multiplier: float = 1.0,
) -> list[dict]:
    scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}
    for rank, row in enumerate(semantic_rows):
        rid = row.get("id") or row["name"]
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        by_id[rid] = row
    for rank, row in enumerate(keyword_rows):
        rid = row.get("id") or row["name"]
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        by_id[rid] = row
    if boost_types:
        for rid, row in by_id.items():
            if row.get("type") in boost_types:
                scores[rid] *= boost_multiplier
    ranked = sorted(scores.keys(), key=lambda r: scores[r], reverse=True)
    result = []
    for rid in ranked[:limit]:
        row = by_id[rid]
        row["_rrf_score"] = scores[rid]
        result.append(row)
    return result


def _apply_temporal_scoring(rows: list[dict]) -> list[dict]:
    now = datetime.now(timezone.utc)
    for row in rows:
        rrf = row.get("_rrf_score", 0.01)
        mem_type = row.get("type", "decision")
        half_life = TEMPORAL_HALF_LIVES.get(mem_type, DEFAULT_HALF_LIFE)

        # Phase 1: decay is driven by content_updated_at (content changes),
        # not updated_at (which gets bumped by every recall's touch_memories).
        # Fall back to updated_at for rows without backfilled content_updated_at.
        updated_str = row.get("content_updated_at") or row.get("updated_at") or ""
        try:
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            days_since_update = max(0, (now - updated).total_seconds() / 86400)
        except (ValueError, AttributeError):
            days_since_update = half_life

        accessed_str = row.get("last_accessed_at") or ""
        try:
            accessed = datetime.fromisoformat(accessed_str.replace("Z", "+00:00"))
            days_since_access = max(0, (now - accessed).total_seconds() / 86400)
        except (ValueError, AttributeError):
            days_since_access = days_since_update * 2

        recency = math.exp(-0.693 * days_since_update / half_life)
        access = 1.0 + ACCESS_BOOST_MAX * math.exp(-0.693 * days_since_access / ACCESS_HALF_LIFE)
        row["_temporal_score"] = rrf * recency * access

    rows.sort(key=lambda r: r.get("_temporal_score", 0), reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Eval core
# ---------------------------------------------------------------------------

@dataclass
class QueryResult:
    id: str
    query: str
    kind: str
    expected: list[str]
    must_not: list[str]
    top_names: list[str]                 # top-10 names in order
    first_hit_rank: int | None           # 1-indexed, None if no expected hit in top-10
    hits_at_5: list[str]                 # expected names that appeared in top-5
    hits_at_10: list[str]
    must_not_violations_at_5: list[str]  # must_not names that appeared in top-5
    passed: bool                         # recall@5 >= 1 AND no must_not violations
    rewriter_entities: list[str] = field(default_factory=list)
    rewriter_types: list[str] = field(default_factory=list)
    rewriter_fired: bool = False         # True when rewriter returned a non-null result


@dataclass
class EvalReport:
    timestamp: str
    mode: str                            # "server_only" | "with_rewriter"
    corpus_size: int
    total_queries: int
    recall_at_5: float
    recall_at_10: float
    mrr: float
    must_not_violations: int
    passed: int
    failed: int
    rewriter_fired_count: int = 0        # queries where rewriter produced output
    results: list[dict] = field(default_factory=list)


async def run_query(
    client,
    q: dict,
    rewriter: Callable[[str], dict | None] | None = None,
    boost_multiplier: float = 1.0,
) -> QueryResult:
    embedding = await _embed_query(q["query"])

    # Phase 3: if a rewriter is supplied, use it to denoise the keyword leg
    # (entities substitute for the raw prompt) and optionally narrow types.
    # Matches the hook contract: entities-only → kw query substitution, types
    # list → Python-side filter on BOTH semantic and keyword rows before RRF.
    rw_entities: list[str] = []
    rw_types: list[str] = []
    rw_fired = False
    if rewriter is not None:
        rw = rewriter(q["query"])
        if rw:
            rw_fired = True
            rw_entities = list(rw.get("entities") or [])
            rw_types = list(rw.get("types") or [])

    keyword_query = " ".join(rw_entities) if rw_entities else q["query"]

    sem = client.rpc("match_memories", {
        "query_embedding": embedding,
        "match_limit": 20,
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "filter_project": None,
        "filter_type": None,
        "show_history": False,
    }).execute()
    sem_rows = sem.data or []

    kw = client.rpc("keyword_search_memories", {
        "search_query": keyword_query,
        "match_limit": 20,
        "filter_project": None,
        "filter_type": None,
        "show_history": False,
    }).execute()
    kw_rows = kw.data or []

    # Rewriter types → soft boost (matches hook behavior after the
    # type-narrowing regression fix). No default scope filter — eval
    # doesn't model the hook's exclusion of user/project memories.
    boost_types = set(rw_types) if rw_types else None
    merged = _rrf_merge(
        sem_rows,
        kw_rows,
        limit=10,
        boost_types=boost_types,
        boost_multiplier=boost_multiplier,
    )
    _apply_temporal_scoring(merged)

    top_names = [r.get("name", "?") for r in merged]
    expected = set(q.get("expected") or [])
    must_not = set(q.get("must_not") or [])

    top5 = top_names[:5]
    top10 = top_names[:10]
    hits_5 = [n for n in top5 if n in expected]
    hits_10 = [n for n in top10 if n in expected]
    mn_viol = [n for n in top5 if n in must_not]

    first_hit_rank = None
    for i, name in enumerate(top10, start=1):
        if name in expected:
            first_hit_rank = i
            break

    passed = bool(hits_5) and not mn_viol

    return QueryResult(
        id=q["id"],
        query=q["query"],
        kind=q.get("kind", ""),
        expected=sorted(expected),
        must_not=sorted(must_not),
        top_names=top_names,
        first_hit_rank=first_hit_rank,
        hits_at_5=hits_5,
        hits_at_10=hits_10,
        must_not_violations_at_5=mn_viol,
        passed=passed,
        rewriter_entities=rw_entities,
        rewriter_types=rw_types,
        rewriter_fired=rw_fired,
    )


async def run_all(
    queries: list[dict],
    client,
    rewriter: Callable[[str], dict | None] | None = None,
    boost_multiplier: float = 1.0,
) -> EvalReport:
    results = []
    for q in queries:
        r = await run_query(
            client, q, rewriter=rewriter, boost_multiplier=boost_multiplier
        )
        results.append(r)

    total = len(results)
    r5 = sum(1 for r in results if r.hits_at_5) / total if total else 0.0
    r10 = sum(1 for r in results if r.hits_at_10) / total if total else 0.0
    mrr = sum(1.0 / r.first_hit_rank for r in results if r.first_hit_rank) / total if total else 0.0
    mn_viol = sum(1 for r in results if r.must_not_violations_at_5)
    passed = sum(1 for r in results if r.passed)
    rw_fired = sum(1 for r in results if r.rewriter_fired)

    # corpus size for context
    cs = client.table("memories").select("id", count="exact").is_("deleted_at", "null").limit(1).execute()
    corpus_size = cs.count or 0

    return EvalReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        mode="with_rewriter" if rewriter is not None else "server_only",
        corpus_size=corpus_size,
        total_queries=total,
        recall_at_5=r5,
        recall_at_10=r10,
        mrr=mrr,
        must_not_violations=mn_viol,
        passed=passed,
        failed=total - passed,
        rewriter_fired_count=rw_fired,
        results=[asdict(r) for r in results],
    )


# ---------------------------------------------------------------------------
# Formatting / CLI
# ---------------------------------------------------------------------------

def _fmt_pct(x: float) -> str:
    return f"{x*100:5.1f}%"


def print_report(report: EvalReport, quiet: bool = False) -> None:
    if not quiet:
        print(f"\nQueries: {report.total_queries}   Corpus: {report.corpus_size} memories   Mode: {report.mode}\n")
        print(f"{'id':<5} {'kind':<10} {'rank':>5}  {'hit5':>5}  {'viol':>5}  {'rw':>3}  query")
        print("-" * 100)
        for r in report.results:
            rank_s = str(r["first_hit_rank"]) if r["first_hit_rank"] else "-"
            hit = "Y" if r["hits_at_5"] else " "
            viol = "!" if r["must_not_violations_at_5"] else " "
            rw = "*" if r.get("rewriter_fired") else " "
            q = r["query"] if len(r["query"]) <= 60 else r["query"][:57] + "..."
            print(f"{r['id']:<5} {r['kind']:<10} {rank_s:>5}  {hit:>5}  {viol:>5}  {rw:>3}  {q}")

        # fail details
        fails = [r for r in report.results if not r["passed"]]
        if fails:
            print("\nFAILED queries (recall@5 miss or must_not violation):")
            for r in fails:
                print(f"\n  [{r['id']}] {r['query']}")
                print(f"    expected:  {r['expected']}")
                if r["must_not"]:
                    print(f"    must_not:  {r['must_not']}")
                print(f"    top-5:     {r['top_names'][:5]}")
                if r["must_not_violations_at_5"]:
                    print(f"    violated:  {r['must_not_violations_at_5']}")
                if r.get("rewriter_fired"):
                    print(f"    rewriter:  entities={r.get('rewriter_entities') or []} types={r.get('rewriter_types') or []}")

    print("\n=== AGGREGATES ===")
    print(f"mode               : {report.mode}")
    print(f"recall@5           : {_fmt_pct(report.recall_at_5)}  ({report.passed}/{report.total_queries} queries retrieved at least one expected memory in top-5)")
    print(f"recall@10          : {_fmt_pct(report.recall_at_10)}")
    print(f"MRR                : {report.mrr:.3f}")
    print(f"must_not violations: {report.must_not_violations}  (lifecycle signal — should be 0 after Phase 1)")
    print(f"passed / failed    : {report.passed} / {report.failed}")
    if report.mode == "with_rewriter":
        print(f"rewriter fired     : {report.rewriter_fired_count}/{report.total_queries}")
    print()


def print_diff(current: EvalReport, baseline: dict) -> None:
    def delta(k: str) -> str:
        cur = getattr(current, k)
        base = baseline.get(k, 0)
        d = cur - base
        sign = "+" if d >= 0 else ""
        return f"{cur:.3f}  (baseline {base:.3f}, {sign}{d:.3f})"

    print("=== DELTA vs baseline.json ===")
    print(f"baseline saved : {baseline.get('timestamp', '?')}")
    base_mode = baseline.get("mode", "server_only")
    if base_mode != current.mode:
        print(f"MODE MISMATCH  : current={current.mode}  baseline={base_mode}  — delta mixes pipeline changes with mode change")
    else:
        print(f"mode           : {current.mode}")
    print(f"recall@5       : {delta('recall_at_5')}")
    print(f"recall@10      : {delta('recall_at_10')}")
    print(f"MRR            : {delta('mrr')}")
    print(f"must_not viol  : {current.must_not_violations}  (baseline {baseline.get('must_not_violations', '?')})")
    print()

    # per-query regression
    base_results = {r["id"]: r for r in baseline.get("results", [])}
    regressed = []
    improved = []
    for r in current.results:
        br = base_results.get(r["id"])
        if not br:
            continue
        if br["passed"] and not r["passed"]:
            regressed.append(r["id"])
        elif not br["passed"] and r["passed"]:
            improved.append(r["id"])
    if regressed:
        print(f"REGRESSIONS: {regressed}")
    if improved:
        print(f"IMPROVEMENTS: {improved}")
    if not regressed and not improved:
        print("(no per-query status changes vs baseline)")
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save-baseline", action="store_true",
                    help="Overwrite tests/memory-eval/baseline.json with this run's results")
    ap.add_argument("--diff", choices=["baseline"],
                    help="Print delta vs baseline.json")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--queries", default=None,
                    help="Path to queries.yaml (default: tests/memory-eval/queries.yaml)")
    ap.add_argument("--with-rewriter", action="store_true",
                    help="Run the hook's Haiku rewriter on each query — entities "
                         "substitute for the raw prompt in keyword search, and "
                         "returned types narrow both RPC result sets Python-side. "
                         "Requires ANTHROPIC_API_KEY; falls back per-query to raw "
                         "prompt when the rewriter returns None.")
    args = ap.parse_args()

    _load_env()

    repo = Path(__file__).resolve().parent.parent
    queries_path = Path(args.queries) if args.queries else repo / "tests" / "memory-eval" / "queries.yaml"
    baseline_path = repo / "tests" / "memory-eval" / "baseline.json"

    import yaml
    with queries_path.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    queries = doc["queries"]

    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase package not installed in venv", file=sys.stderr)
        return 2

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL / SUPABASE_KEY not set", file=sys.stderr)
        return 2
    client = create_client(url, key)

    rewriter = None
    boost_multiplier = 1.0  # no-op when rewriter disabled
    if args.with_rewriter:
        hook_mod = _load_hook_module()
        if hook_mod is None:
            print("ERROR: --with-rewriter set but scripts/memory-recall-hook.py "
                  "could not be loaded as a module", file=sys.stderr)
            return 2
        rewriter = getattr(hook_mod, "rewrite_prompt", None)
        if rewriter is None:
            print("ERROR: --with-rewriter set but rewrite_prompt not found in hook "
                  "module", file=sys.stderr)
            return 2
        # Source boost calibration from the hook — single source of truth.
        boost_multiplier = float(getattr(hook_mod, "TYPE_BOOST_MULTIPLIER", 1.5))
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("WARN: --with-rewriter set but ANTHROPIC_API_KEY missing — "
                  "rewriter will return None for every query (degrades to server_only).",
                  file=sys.stderr)

    report = asyncio.run(
        run_all(queries, client, rewriter=rewriter, boost_multiplier=boost_multiplier)
    )
    print_report(report, quiet=args.quiet)

    if args.diff == "baseline":
        if not baseline_path.exists():
            print(f"(no baseline at {baseline_path} — run --save-baseline first)")
        else:
            with baseline_path.open("r", encoding="utf-8") as f:
                baseline = json.load(f)
            print_diff(report, baseline)

    if args.save_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        with baseline_path.open("w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2, ensure_ascii=False)
        print(f"Baseline saved to {baseline_path}")

    # exit code: 0 if all queries passed, 1 otherwise — CI-friendly
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

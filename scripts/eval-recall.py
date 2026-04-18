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
import json
import math
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Pipeline constants — mirrored from mcp-memory/server.py as of Phase 1.
# When server.py changes, re-sync OR deliberately let them differ to measure.
# ---------------------------------------------------------------------------
SIMILARITY_THRESHOLD = 0.25
RRF_K = 60
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


def _rrf_merge(semantic_rows: list[dict], keyword_rows: list[dict], limit: int, k: int = RRF_K) -> list[dict]:
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


@dataclass
class EvalReport:
    timestamp: str
    corpus_size: int
    total_queries: int
    recall_at_5: float
    recall_at_10: float
    mrr: float
    must_not_violations: int
    passed: int
    failed: int
    results: list[dict] = field(default_factory=list)


async def run_query(client, q: dict) -> QueryResult:
    embedding = await _embed_query(q["query"])

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
        "search_query": q["query"],
        "match_limit": 20,
        "filter_project": None,
        "filter_type": None,
        "show_history": False,
    }).execute()
    kw_rows = kw.data or []

    merged = _rrf_merge(sem_rows, kw_rows, limit=10)
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
    )


async def run_all(queries: list[dict], client) -> EvalReport:
    results = []
    for q in queries:
        r = await run_query(client, q)
        results.append(r)

    total = len(results)
    r5 = sum(1 for r in results if r.hits_at_5) / total if total else 0.0
    r10 = sum(1 for r in results if r.hits_at_10) / total if total else 0.0
    mrr = sum(1.0 / r.first_hit_rank for r in results if r.first_hit_rank) / total if total else 0.0
    mn_viol = sum(1 for r in results if r.must_not_violations_at_5)
    passed = sum(1 for r in results if r.passed)

    # corpus size for context
    cs = client.table("memories").select("id", count="exact").is_("deleted_at", "null").limit(1).execute()
    corpus_size = cs.count or 0

    return EvalReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        corpus_size=corpus_size,
        total_queries=total,
        recall_at_5=r5,
        recall_at_10=r10,
        mrr=mrr,
        must_not_violations=mn_viol,
        passed=passed,
        failed=total - passed,
        results=[asdict(r) for r in results],
    )


# ---------------------------------------------------------------------------
# Formatting / CLI
# ---------------------------------------------------------------------------

def _fmt_pct(x: float) -> str:
    return f"{x*100:5.1f}%"


def print_report(report: EvalReport, quiet: bool = False) -> None:
    if not quiet:
        print(f"\nQueries: {report.total_queries}   Corpus: {report.corpus_size} memories\n")
        print(f"{'id':<5} {'kind':<10} {'rank':>5}  {'hit5':>5}  {'viol':>5}  query")
        print("-" * 100)
        for r in report.results:
            rank_s = str(r["first_hit_rank"]) if r["first_hit_rank"] else "-"
            hit = "Y" if r["hits_at_5"] else " "
            viol = "!" if r["must_not_violations_at_5"] else " "
            q = r["query"] if len(r["query"]) <= 60 else r["query"][:57] + "..."
            print(f"{r['id']:<5} {r['kind']:<10} {rank_s:>5}  {hit:>5}  {viol:>5}  {q}")

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

    print("\n=== AGGREGATES ===")
    print(f"recall@5           : {_fmt_pct(report.recall_at_5)}  ({report.passed}/{report.total_queries} queries retrieved at least one expected memory in top-5)")
    print(f"recall@10          : {_fmt_pct(report.recall_at_10)}")
    print(f"MRR                : {report.mrr:.3f}")
    print(f"must_not violations: {report.must_not_violations}  (lifecycle signal — should be 0 after Phase 1)")
    print(f"passed / failed    : {report.passed} / {report.failed}")
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

    report = asyncio.run(run_all(queries, client))
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

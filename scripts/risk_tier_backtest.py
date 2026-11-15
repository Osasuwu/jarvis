"""Backtest the planned risk-tier inputs on merged jarvis PRs (#2199, unblocks #2200).

The decision "Three risk tiers; the final tier is computed from the diff, and the reviewer may
only raise it" (docs/decisions/2026-Q4.md, PR #2197) keeps these computed inputs and locks their
thresholds only after this backtest:

- protected paths: a changed path in any bucket of `config/protected-paths.json` -> HIGH
  (the floor `risk_tier.path_tier` applies today);
- test weakening -> HIGH (`risk_tier.test_weakening`, unchanged);
- the plan classifier's ordinal -> MEDIUM when churn is above the threshold (lockfiles
  excluded) or the diff touches at least the minimum number of production areas, unless the
  diff is docs-only (`agents.plan_classifier.classify`, thresholds overridden per variant);
- the comment-only exemption: a protected-path diff drops to LOW when every changed file is
  `.py`, the AST is equal before and after, and no directive comment changed. A parse
  failure means no exemption. Computed from the merge commit and its first parent.

A file list the API cannot read in full is HIGH and listed, as in the live check.

The classifier code is not copied: `.github/scripts/risk_tier.py` is loaded by file path and
its `path_tier` / `test_weakening` are called, and the ordinal comes from `classify`. What
this script adds is only what the live check does not have yet: the lockfile exclusion, the
threshold variants and the comment-only exemption.

The protected list and `plan_review.yaml` are read from this checkout, not from each PR's base:
the question is what today's planned rules would have said about the history.

Usage (needs `gh` signed in and full git history of the repo):

    python scripts/risk_tier_backtest.py --since 2026-09-01 \\
        --out docs/research/risk-tier-backtest-2026-11-15.md
"""

from __future__ import annotations

import argparse
import ast
import collections
import dataclasses
import datetime as dt
import importlib.util
import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from agents import path_policy  # noqa: E402
from agents.plan_classifier import (  # noqa: E402
    ChangeSet,
    classify,
    derive_mechanical_criteria,
    prod_areas_from_paths,
)
from agents.plan_review_config import load_plan_review_config  # noqa: E402

REPO = "Osasuwu/jarvis"
TIERS = ("LOW", "MEDIUM", "HIGH")
BASELINE = (400, 2)
CHURN_VARIANTS = (300, 400, 600)
AREA_VARIANTS = (2, 3)
PREDICTED_HIGH_SHARE = 0.25

# Lockfiles do not count toward churn (decision PR #2197). Basenames, any directory.
LOCKFILES = frozenset(
    {
        "uv.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "Gemfile.lock",
        "composer.lock",
        "go.sum",
    }
)

# A comment that a tool reads as an instruction. Changing one is not "comment-only".
_DIRECTIVE = re.compile(
    r"^#!|^#.*coding[:=]|#\s*(?:noqa|type:|pragma|pylint:|fmt:|ruff:|nosec|mypy:|isort:|pyright:)",
    re.IGNORECASE,
)


def _load_risk_tier():
    """`.github/scripts/risk_tier.py`, the live check's own code, loaded by file path."""
    name = "_risk_tier_for_backtest"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / ".github" / "scripts" / "risk_tier.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


risk_tier = _load_risk_tier()


# --- inputs -------------------------------------------------------------------------------


def churn_without_lockfiles(files):
    """Added plus deleted lines over every file whose basename is not a lockfile."""
    return sum(
        f.get("additions", 0) + f.get("deletions", 0)
        for f in files
        if f["filename"].rsplit("/", 1)[-1] not in LOCKFILES
    )


def bucket_hits(paths, buckets):
    """`{bucket: matched paths}` for every bucket with a match, in the bucket order given."""
    hits = {}
    for name, globs in buckets.items():
        found = path_policy.matched_paths(paths, globs)
        if found:
            hits[name] = found
    return hits


def classifier_tier(config, paths, churn, areas, churn_threshold, min_areas):
    """The plan classifier's ordinal as a tier, with the variant's thresholds."""
    variant = dataclasses.replace(
        config,
        class_2=dataclasses.replace(
            config.class_2, churn_threshold=churn_threshold, min_prod_areas=min_areas
        ),
    )
    ordinal = classify(variant, ChangeSet(tuple(paths), churn, areas))
    return {1: "LOW", 2: "MEDIUM", 3: "HIGH"}[ordinal]


def _directives(source):
    """The directive comments of a source text, in order."""
    found = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT and _DIRECTIVE.search(tok.string):
            found.append(tok.string.strip())
    return found


def comment_only(files, read_blob):
    """`(exempt, why)` for the comment-only exemption.

    `read_blob(side, path)` returns the file text at `"base"` or `"head"`, `None` when the
    path does not exist on that side, and raises `LookupError` when the side cannot be read.
    `exempt` is `None` when the exemption could not be computed.
    """
    if not files:
        return False, "no files"
    for f in files:
        names = [f["filename"], f.get("previous_filename") or f["filename"]]
        if not all(n.endswith(".py") for n in names):
            return False, f"not .py: {f['filename']}"
    for f in files:
        try:
            before = read_blob("base", f.get("previous_filename") or f["filename"])
            after = read_blob("head", f["filename"])
        except LookupError as exc:
            return None, f"unreadable: {exc}"
        if before is None or after is None:
            return False, f"file added or removed: {f['filename']}"
        try:
            same_ast = ast.dump(ast.parse(before)) == ast.dump(ast.parse(after))
            same_directives = _directives(before) == _directives(after)
        except (SyntaxError, ValueError, tokenize.TokenError):
            return False, f"parse failure: {f['filename']}"
        if not same_ast:
            return False, f"AST changed: {f['filename']}"
        if not same_directives:
            return False, f"directive comment changed: {f['filename']}"
    return True, "every file .py, AST equal, directives equal"


# --- one PR -------------------------------------------------------------------------------


@dataclasses.dataclass
class Result:
    number: int
    title: str
    merged_at: str
    churn: int
    areas: int
    unreadable: str | None
    buckets: dict
    weakening: list
    docs_only: bool
    exemption: bool | None
    exemption_why: str
    tiers: dict  # {(churn_threshold, min_areas): tier}

    @property
    def tier(self):
        return self.tiers[BASELINE]

    def inputs(self):
        """The inputs that fired under the baseline thresholds."""
        fired = []
        if self.unreadable:
            fired.append(f"file list unreadable ({self.unreadable})")
        fired += [f"path:{name}" for name in self.buckets]
        if self.weakening:
            fired.append("test weakening")
        if self.docs_only:
            fired.append("docs-only")
        else:
            if self.churn > BASELINE[0]:
                fired.append(f"churn>{BASELINE[0]}")
            if self.areas >= BASELINE[1]:
                fired.append(f"areas>={BASELINE[1]}")
        if self.exemption:
            fired.append("comment-only exemption")
        elif self.exemption is None and self.exemption_why:  # "" = not evaluated
            fired.append(f"exemption not computable ({self.exemption_why})")
        return fired


def evaluate(pr, files, buckets, host_root, config, read_blob):
    """The planned tier of one merged PR under every threshold variant.

    `files` is the PR's file listing as the API returns it, or `None` when it could not be read.
    """
    unreadable = None
    if files is None:
        unreadable, files = "listing failed", []
    elif len(files) < pr["changedFiles"]:
        unreadable = f"{len(files)} of {pr['changedFiles']} files listed"
    paths = risk_tier._changed_paths(files)
    floor, _ = risk_tier.path_tier(paths, REPO, host_root)
    weakening = risk_tier.test_weakening(files)
    churn = churn_without_lockfiles(files)
    areas = prod_areas_from_paths(paths)
    exemption, why = None, ""
    if floor == "HIGH" and not unreadable:
        exemption, why = comment_only(files, read_blob)
    hard_high = bool(unreadable) or (floor == "HIGH" and not exemption) or bool(weakening)
    tiers = {}
    for c in CHURN_VARIANTS:
        for a in AREA_VARIANTS:
            if hard_high:
                tiers[(c, a)] = "HIGH"
            elif exemption:
                tiers[(c, a)] = "LOW"
            else:
                tiers[(c, a)] = classifier_tier(config, paths, churn, areas, c, a)
    return Result(
        number=pr["number"],
        title=pr["title"],
        merged_at=pr["mergedAt"],
        churn=churn,
        areas=areas,
        unreadable=unreadable,
        buckets=bucket_hits(paths, buckets),
        weakening=weakening,
        docs_only=bool(paths) and "docs-only" in derive_mechanical_criteria(paths),
        exemption=exemption,
        exemption_why=why,
        tiers=tiers,
    )


# --- aggregation and report ---------------------------------------------------------------


def week_of(merged_at):
    """The Monday (UTC) of the ISO week a PR merged in, as `YYYY-MM-DD`."""
    day = dt.datetime.fromisoformat(merged_at.replace("Z", "+00:00")).date()
    return (day - dt.timedelta(days=day.weekday())).isoformat()


def shares(tiers):
    """`{tier: share}` over a list of tiers; every tier present, an empty list is all zero."""
    count = collections.Counter(tiers)
    total = len(tiers)
    return {t: (count[t] / total if total else 0.0) for t in TIERS}


def _pct(x):
    return f"{100 * x:.0f}%"


def render(results, *, since, until, command, run_date):
    results = sorted(results, key=lambda r: r.merged_at)
    n = len(results)
    base = shares([r.tier for r in results])
    held = base["HIGH"] <= PREDICTED_HIGH_SHARE
    counts = collections.Counter(r.tier for r in results)
    out = [
        f"# Risk-tier backtest: jarvis PRs merged {since} – {until}",
        "",
        f"- Command: `{command}`",
        f"- Window: merged {since} to {until} (UTC dates, inclusive). Run {run_date}.",
        f"- PRs: **{n}**, one row each below.",
        "- Rules: `config/protected-paths.json` and `config/plan_review.yaml` at the commit "
        "of this report, not at each PR's base. Inputs and their sources: "
        "`scripts/risk_tier_backtest.py` docstring. Issue: #2199; thresholds lock in #2200.",
        "",
        "## Prediction",
        "",
        f"Pre-registered (decision PR #2197): HIGH share at or below "
        f"{_pct(PREDICTED_HIGH_SHARE)}. Measured: **{_pct(base['HIGH'])}** "
        f"({counts['HIGH']} of {n}). The prediction **{'held' if held else 'missed'}**.",
        "",
        "## Distribution by threshold variant",
        "",
        "Churn and areas only move PRs between LOW and MEDIUM, so HIGH is the same in every "
        "variant.",
        "",
        "| churn > | areas >= | HIGH | MEDIUM | LOW |",
        "|---|---|---|---|---|",
    ]
    for c in CHURN_VARIANTS:
        for a in AREA_VARIANTS:
            s = shares([r.tiers[(c, a)] for r in results])
            mark = " (baseline)" if (c, a) == BASELINE else ""
            out.append(
                f"| {c}{mark} | {a} | {_pct(s['HIGH'])} | {_pct(s['MEDIUM'])} | {_pct(s['LOW'])} |"
            )
    fired = collections.Counter()
    for r in results:
        for item in r.inputs():
            fired[item.split(" (")[0]] += 1
    out += ["", "## Inputs that fired (baseline)", "", "| input | PRs |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in sorted(fired.items(), key=lambda kv: -kv[1])]
    only_mach = [
        r
        for r in results
        if r.tier == "HIGH"
        and not r.unreadable
        and not r.weakening
        and r.buckets
        and set(r.buckets) <= {"machinery", "gate"}
    ]
    out += [
        "",
        f"HIGH from the `machinery`/`gate` buckets alone (no `hitl`/`guarded` path, no test "
        f"weakening, list readable): {len(only_mach)} of {counts['HIGH']} HIGH PRs.",
    ]
    by_week = collections.defaultdict(list)
    for r in results:
        by_week[week_of(r.merged_at)].append(r)
    variant_cols = [(c, a) for c in CHURN_VARIANTS for a in AREA_VARIANTS if (c, a) != BASELINE]
    out += [
        "",
        "## Weekly shares",
        "",
        "Baseline (churn > 400, areas >= 2) HIGH / MEDIUM / LOW, then the MEDIUM share under "
        "each other variant (`c` churn threshold, `a` areas minimum). Week = Monday, UTC.",
        "",
        "| week | PRs | HIGH | MEDIUM | LOW | "
        + " | ".join(f"MED c{c} a{a}" for c, a in variant_cols)
        + " |",
        "|---|---|---|---|---|" + "---|" * len(variant_cols),
    ]
    for week in sorted(by_week):
        rows = by_week[week]
        s = shares([r.tier for r in rows])
        extra = [_pct(shares([r.tiers[v] for r in rows])["MEDIUM"]) for v in variant_cols]
        out.append(
            f"| {week} | {len(rows)} | {_pct(s['HIGH'])} | {_pct(s['MEDIUM'])} | "
            f"{_pct(s['LOW'])} | " + " | ".join(extra) + " |"
        )
    unreadable = [r for r in results if r.unreadable]
    out += ["", "## Unreadable file lists", ""]
    if unreadable:
        out += [f"- #{r.number}: {r.unreadable} — counted HIGH" for r in unreadable]
    else:
        out.append("None: every PR's file list was read in full.")
    out += [
        "",
        "## Per PR",
        "",
        "Churn excludes lockfiles; areas are top-level path components, `tests/` excluded.",
        "",
        "| PR | merged | tier | churn | areas | inputs fired |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        inputs = "; ".join(r.inputs()) or "none"
        out.append(
            f"| #{r.number} | {r.merged_at[:10]} | {r.tier} | {r.churn} | {r.areas} | {inputs} |"
        )
    return "\n".join(out) + "\n"


# --- I/O ----------------------------------------------------------------------------------


def _gh(args):
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def fetch_prs(since, until):
    raw = _gh(
        [
            "pr", "list", "--repo", REPO, "--state", "merged", "--limit", "1000",
            "--search", f"merged:{since}..{until}",
            "--json", "number,title,mergedAt,mergeCommit,changedFiles",
        ]
    )  # fmt: skip
    return json.loads(raw)


def fetch_files(number):
    """The PR's file listing, or `None` when the API call fails."""
    try:
        raw = _gh(
            ["api", "--paginate", f"repos/{REPO}/pulls/{number}/files?per_page=100", "--jq", ".[]"]
        )
    except subprocess.CalledProcessError:
        return None
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def git_reader(merge_sha):
    """`read_blob` for one merge commit: `base` is its first parent, `head` the commit."""
    refs = {"base": f"{merge_sha}^1", "head": merge_sha}

    def read_blob(side, path):
        rev = refs[side]
        check = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
            capture_output=True,
        )
        if check.returncode != 0:
            raise LookupError(f"commit {rev} not in the local history")
        shown = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", f"{rev}:{path}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return shown.stdout if shown.returncode == 0 else None

    return read_blob


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--since", default="2026-09-01")
    parser.add_argument("--until", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    parser.add_argument("--out", required=True, help="markdown report path")
    parser.add_argument(
        "--cache", help="JSON file: read the fetched PRs and file lists from it, or write them"
    )
    args = parser.parse_args(argv)

    cache = Path(args.cache) if args.cache else None
    if cache and cache.exists():
        data = json.loads(cache.read_text("utf-8"))
    else:
        prs = fetch_prs(args.since, args.until)
        data = {"prs": prs, "files": {str(p["number"]): fetch_files(p["number"]) for p in prs}}
        if cache:
            cache.write_text(json.dumps(data), "utf-8")

    policy = path_policy.load_policy(REPO_ROOT / "config" / "protected-paths.json")
    buckets = policy.buckets(REPO)
    config = load_plan_review_config(REPO_ROOT / "config" / "plan_review.yaml")
    results = [
        evaluate(
            pr,
            data["files"][str(pr["number"])],
            buckets,
            REPO_ROOT,
            config,
            git_reader((pr.get("mergeCommit") or {}).get("oid") or "missing"),
        )
        for pr in data["prs"]
    ]
    command = "python scripts/risk_tier_backtest.py " + " ".join(
        a for a in (f"--since {args.since}", f"--until {args.until}", f"--out {args.out}")
    )
    report = render(
        results,
        since=args.since,
        until=args.until,
        command=command,
        run_date=dt.datetime.now(dt.timezone.utc).date().isoformat(),
    )
    Path(args.out).write_text(report, "utf-8", newline="\n")
    base = shares([r.tier for r in results])
    print(
        f"{len(results)} PRs: HIGH {_pct(base['HIGH'])}, MEDIUM {_pct(base['MEDIUM'])}, "
        f"LOW {_pct(base['LOW'])} -> {args.out}"
    )


if __name__ == "__main__":
    main()

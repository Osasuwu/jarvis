# Stale-fact sweep — re-runnable recipe

Pull-only reference. Read it when you want to check the repo's own steering docs for claims
that went false when something else moved (#1374, slice 1). The steering docs name files,
checks and paths in prose; when the thing goes, the mention stays and nothing fails. This
recipe is the mechanical half of a sweep: three classes of falsifiable claim, each checked
against an independent source (the filesystem, `git`, and `gh api` on branch protection),
never against another doc. Value and preference claims ("quality over speed") are not
fact-checked.

## What it checks

| # | Claim class | Independent source | Scope |
|---|---|---|---|
| 1 | Dead user-level paths: `~/.claude/reference/` and `~/.claude/hooks` no longer exist on the operator's devices. The reference files ship with the jarvis-private plugin at `~/.claude/plugins/marketplaces/jarvis-private/reference/`; `docs/reference/test-quality.md` is the repo-local copy of one of them. | text match | `AGENTS.md`, `CONTEXT.md`, `config/SOUL.md`, `docs/reference/*.md`, `docs/architecture.md`, `docs/design/*.md`, `docs/security/*.md`, `.github/scripts/`, `scripts/` |
| 2 | Required merge gates: every check branch protection reports is named in `AGENTS.md` and `docs/reference/github-repo-setup.md`; no in-scope line gives a different count; `risk-tier` is not described as still pending. | `gh api repos/Osasuwu/jarvis/branches/main/protection/required_status_checks` | same files |
| 3 | Backticked repo-relative paths that do not exist at the head. A hit is explained when its paragraph says the file is gone (retired, deleted, removed, no longer, historical, ...), or the token is a placeholder, a convention directory (`.claude/rules/`, `.claude/skills/`), or its line names another repo (`jarvis-oss`, `jarvis-private`), or its line names a commit (a backticked SHA, as in a seeded-defect row's Head) whose tree holds the path. That last one is per line and per path: a path the named commit lacks is still a hit, and so is one whose commit is missing from the local clone (fetch its branch). | filesystem, `git cat-file` | `AGENTS.md`, `CONTEXT.md`, `config/SOUL.md`, `docs/reference/*.md` |

Not covered, by design: `docs/research/**` and `docs/decisions/**` (dated records of the state
on their date), and `/dispatch` references (the skill still exists, #2009 is deferred).

`tests/ci/test_steering_doc_paths_guard.py` (#2045) is the CI-enforced subset of class 3 for
`.github/` and `docs/` paths in `AGENTS.md`, `CONTEXT.md` and `docs/reference/*.md`; it has its
own allowlist. The script below adds the other roots (`scripts/`, `tests/`, `config/`,
`agents/`, `.claude/`, `supabase/`), `config/SOUL.md`, and classes 1 and 2.

## Run it

From the repo root, in a shell with `git`, `python` and (for class 2) an authenticated `gh`.
The script lives in this file; extract it to a scratch path outside the repo and run that
file:

```bash
awk '/^```python$/{f=1;next} /^```$/{f=0} f' docs/reference/stale-fact-sweep.md > "${TMPDIR:-/tmp}/stale_fact_sweep.py"
python -X utf8 "${TMPDIR:-/tmp}/stale_fact_sweep.py"
python -m pytest tests/ci/test_steering_doc_paths_guard.py -q
```

Clean run: a per-file table of claims inspected (the baseline numbers), then
`no unexplained hit`, exit 0. Without a usable `gh`, class 2 prints a `notice:` and
is skipped; that is not a pass for class 2.

Each hit line is `<class>  <file>:<line>`. Fix the doc so the claim is true, or, for a
mention that is deliberately historical, make its paragraph say the file is gone. Do not add
an exception to the script to silence a hit that is a real defect.

```python
"""Stale-fact sweep for the jarvis repo's own docs (#1374 slice 1). See docs/reference/stale-fact-sweep.md."""
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8").splitlines()


def tracked(*specs):
    return subprocess.check_output(["git", "ls-files", *specs], text=True, cwd=ROOT).split()


DOCS = ["AGENTS.md", "CONTEXT.md", "config/SOUL.md", *tracked("docs/reference/*.md")]
SCAN = DOCS + ["docs/architecture.md", *tracked("docs/design/*.md", "docs/security/*.md")]
CODE = [f for f in tracked(".github/scripts", "scripts") if f.endswith((".py", ".ps1", ".sh", ".yml"))]

# Known hits that are deliberately left in place: (file, line) -> why. Keep this empty
# unless a hit cannot be fixed in the same change; every entry needs a reason.
EXPLAINED = {}
hits = []
checked = defaultdict(Counter)  # file -> {claim class: number of claims inspected}
SELF = "docs/reference/stale-fact-sweep.md"  # describes the dead paths, so class 1 skips it


def hit(kind, rel, n, detail=""):
    if (rel, n) not in EXPLAINED:
        hits.append(f"{kind}  {rel}:{n}  {detail}".rstrip())


# 1. Dead user-level paths.
DEAD = re.compile(r"~/\.claude/(reference|hooks)\b|\$HOME/\.claude/(reference|hooks)\b")
for rel in [f for f in SCAN + CODE if f != SELF]:
    for n, line in enumerate(read(rel), 1):
        checked["scripts/ + .github/scripts/ (all files)" if rel in CODE else rel]["1-dead-path-lines"] += 1
        if DEAD.search(line):
            hit("dead-user-level-path", rel, n, line.strip()[:100])

# 2. Required checks against branch protection.
NUMBERS = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
try:
    live = set(json.loads(subprocess.check_output(
        ["gh", "api", "repos/Osasuwu/jarvis/branches/main/protection/required_status_checks",
         "--jq", ".contexts"], text=True, stderr=subprocess.DEVNULL)))
except (OSError, subprocess.CalledProcessError, ValueError):
    live = None
    print("notice: gh unavailable or unauthenticated, required-checks class skipped")
if live is not None:
    for rel in ("AGENTS.md", "docs/reference/github-repo-setup.md"):
        text = "\n".join(read(rel))
        for name in sorted(live):
            checked[rel]["2-gate-claims"] += 1
            if f"`{name}`" not in text:
                hit("required-check-not-named", rel, 1, name)
    count = re.compile(r"\b(three|four|five|six|seven|eight)\s+(?:required|blocking)\b[^.\n]{0,40}"
                       r"\b(?:checks|gates)\b", re.I)
    pending = re.compile(r"`risk-tier`[^.\n]*(?:once the check is live|not yet required)", re.I)
    for rel in SCAN:
        for n, line in enumerate(read(rel), 1):
            for m in count.finditer(line):
                checked[rel]["2-gate-claims"] += 1
                if NUMBERS[m.group(1).lower()] != len(live):
                    hit("gate-count", rel, n, f"says {m.group(1)}, branch protection has {len(live)}")
            checked[rel]["2-gate-claims"] += bool(pending.search(line))
            if pending.search(line):
                hit("risk-tier-not-yet-required", rel, n)

# 3. Backticked repo-relative paths that do not exist.
TOP = ("docs/", "scripts/", ".github/", "tests/", "config/", "agents/", ".claude/", "supabase/")
CONVENTION_DIRS = {".claude/rules/", ".claude/skills/"}
GONE = re.compile(r"retire|delet|remov|no longer|historical|orphan|\bgone\b|obsolete|"
                  r"(?:does not|doesn't) exist", re.I)
OTHER_REPO = re.compile(r"jarvis-oss|jarvis-private")
PLACEHOLDER = re.compile(r"(^|/)(X|NAME)[-_.]|X-guard|test_X_")
SUFFIX = re.compile(r"\.(py|md|yml|yaml|json|ps1|toml|sh|txt|jsonl|csv)$|/$")
COMMIT = re.compile(r"`([0-9a-f]{7,40})`")


def at_named_commit(path, line):
    """The line names a commit (a backticked SHA) whose tree holds the path (#2167)."""
    return any(subprocess.run(["git", "cat-file", "-e", f"{sha}:{path}"], cwd=ROOT,
                              capture_output=True).returncode == 0 for sha in COMMIT.findall(line))


for rel in DOCS:
    paras, cur = [], []
    for n, line in enumerate(read(rel), 1):
        if line.strip():
            cur.append((n, line))
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    for para in paras:
        ptext = " ".join(t for _, t in para)
        for n, line in para:
            for tok in re.findall(r"`([^`\s]+)`", line):
                path = re.sub(r":\d+(-\d+)?$", "", tok.split("#")[0].rstrip(".,;:)"))
                if path.startswith(("~", "http", "/", "$", "<", "-")) or re.search(r"[*<>{}$|=()\[\]]", path):
                    continue
                if not (path.startswith(TOP) or path in ("AGENTS.md", "CONTEXT.md", "README.md")):
                    continue
                if not SUFFIX.search(path):
                    continue
                checked[rel]["3-path-claims"] += 1
                if path in CONVENTION_DIRS or (ROOT / path).exists():
                    continue
                if PLACEHOLDER.search(path) or OTHER_REPO.search(line) or GONE.search(ptext):
                    continue
                if at_named_commit(path, line):
                    continue
                hit("nonexistent-path", rel, n, f"`{tok}`")

print(f"{'claims inspected per file':<48}{'1-dead-path-lines':>18}{'2-gate-claims':>15}{'3-path-claims':>15}")
for rel in sorted(checked):
    c = checked[rel]
    print(f"{rel:<48}{c['1-dead-path-lines']:>18}{c['2-gate-claims']:>15}{c['3-path-claims']:>15}")
if hits:
    print("\n".join(hits))
    print(f"{len(hits)} unexplained hit(s)")
    sys.exit(1)
print("no unexplained hit")
```

## Baseline

First run, `main` 39501f2 plus the slice-1 fixes (2026-10-20). Counts are claims the recipe
inspects, not claims a human judged: class 1 inspects every line of the scanned files, class
2 every required-check name and count phrase, class 3 every backticked repo path token.
The slice-2/3 sweeps (user-level files, memory store) and a later re-run compare against
these numbers; per-file counts and the findings fixed are in the closing comment on #1374.

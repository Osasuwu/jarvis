"""Fail when live branch protection and the documented required-check binding disagree.

Runs from `.github/workflows/branch-protection-drift.yml`. docs/reference/github-repo-setup.md
carries the binding branch protection is meant to have, as a JSON block after the
`<!-- required-checks-binding -->` marker: required check name -> the GitHub App id allowed
to post it. An `app_id` of null in live protection accepts a same-named check run or commit
status from any source, so a documented binding that was never applied (#1998) is a fail-open
merge gate; this probe is what notices.

The branch object (`GET /repos/{owner}/{repo}/branches/{branch}`) carries the protection
settings for any token that can read the repo, so the probe needs no admin credential.

Stdlib only: the job needs no dependency install.
"""

import json
import os
import re
import sys
import urllib.request

MARKER = "<!-- required-checks-binding -->"
_BLOCK = re.compile(re.escape(MARKER) + r"\s*```json\s*\n(.*?)\n```", re.DOTALL)
DEFAULT_DOC = "docs/reference/github-repo-setup.md"


class BindingError(Exception):
    """The documented binding could not be read."""


def parse_documented_binding(markdown):
    """Return {check name: app id} from the marked JSON block of the doc."""
    match = _BLOCK.search(markdown)
    if not match:
        raise BindingError(f"no ```json block follows {MARKER}")
    try:
        binding = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise BindingError(f"binding block is not valid JSON: {exc}") from exc
    if not isinstance(binding, dict) or not binding:
        raise BindingError("binding block must be a non-empty JSON object")
    bad = [k for k, v in binding.items() if type(v) is not int]
    if bad:
        raise BindingError(f"app id must be an integer for: {', '.join(bad)}")
    return binding


def live_binding(branch):
    """Return {check name: app id or None} for the required checks of a branch object."""
    required = (branch.get("protection") or {}).get("required_status_checks") or {}
    live = {c["context"]: c.get("app_id") for c in required.get("checks") or []}
    for context in required.get("contexts") or []:
        live.setdefault(context, None)
    return live


def find_drift(documented, branch):
    """List the ways live protection differs from the documented binding."""
    live = live_binding(branch)
    problems = []
    for name, app_id in documented.items():
        if name not in live:
            problems.append(f"{name}: documented app_id {app_id}, not required live")
        elif live[name] != app_id:
            problems.append(f"{name}: documented app_id {app_id}, live {live[name]}")
    for name, app_id in live.items():
        if name not in documented:
            problems.append(f"{name}: required live (app_id {app_id}), not documented")
    return problems


def run(doc_text, fetch_branch):
    """Compare; print the verdict; return the process exit code."""
    documented = parse_documented_binding(doc_text)
    problems = find_drift(documented, fetch_branch())
    if problems:
        print("Branch protection drifts from the binding documented in " + DEFAULT_DOC + ":")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "Apply the documented binding (PATCH .../protection/required_status_checks) or fix the doc."
        )
        return 1
    print(f"No drift: {len(documented)} required checks match the documented binding.")
    return 0


def _fetch_branch():
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ["DEFAULT_BRANCH"]
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/branches/{branch}",
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    with open(os.environ.get("BINDING_DOC", DEFAULT_DOC), encoding="utf-8") as doc:
        return run(doc.read(), _fetch_branch)


if __name__ == "__main__":
    sys.exit(main())

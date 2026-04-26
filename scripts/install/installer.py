"""Jarvis install/sync — applies install-manifest.yaml into ~/.claude/.

Epic #335 M1 (#336). Handles three device states:
  fresh     — target_root missing or has no .jarvis-version → full install
  outdated  — .jarvis-version present but differs from current repo SHA → re-apply
  current   — .jarvis-version matches current SHA → no-op

Default mode is dry-run. Destructive writes require explicit --apply.

NOTE: .mcp.json is round-tripped through json.loads/json.dumps during installation
and therefore JSONC comments and key ordering are not preserved. Future authors who
add comments to .mcp.json should expect them to be stripped on install.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml


DEFAULT_MANIFEST = "install-manifest.yaml"


# ---------- data model ----------


@dataclasses.dataclass
class Action:
    """One planned filesystem action."""

    kind: str  # "copy_file" | "copy_dir" | "merge_json" | "quarantine_file" | "register_mcp_user" | "write_version" | "set_env"
    source: str | None
    dest: str
    template: bool = False
    group: str = ""
    note: str = ""


@dataclasses.dataclass
class Plan:
    state: str  # "fresh" | "outdated" | "current"
    actions: list[Action]
    backup_path: Path | None
    current_sha: str
    previous_sha: str | None
    target_root: Path
    repo_root: Path


# ---------- helpers ----------


def _run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def current_git_sha(repo_root: Path) -> str:
    return _run_git(repo_root, "rev-parse", "HEAD")


def read_version(target_root: Path) -> str | None:
    marker = target_root / ".jarvis-version"
    if not marker.exists():
        return None
    try:
        return marker.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path))).resolve()


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"manifest {path} did not parse to a mapping")
    if data.get("version") != 1:
        raise ValueError(
            f"unsupported manifest version {data.get('version')!r}; expected 1"
        )
    return data


def detect_state(target_root: Path, current_sha: str) -> tuple[str, str | None]:
    if not target_root.exists():
        return "fresh", None
    prev = read_version(target_root)
    if prev is None:
        # Target exists but no version marker — treat as outdated so we
        # re-apply, but preserve via backup.
        return "outdated", None
    if prev == current_sha:
        return "current", prev
    return "outdated", prev


# ---------- template substitution ----------


# Match `scripts/` or `config/` only at a token boundary — start of string or
# preceded by whitespace. Protects URLs (`https://.../scripts/x`) and compound
# names (`my-scripts/x`) from being rewritten, while still catching embedded
# commands like `python scripts/foo.py && cat config/SOUL.md`.
_POSIX_PATH_PATTERN = re.compile(r"(?<!\S)(scripts|config)/")


# A pre-migration `.mcp.json` sitting in any parent dir of JARVIS_HOME (e.g.
# `D:\Github\.mcp.json`) shadows the correctly-templated user-level file:
# Claude Code walks up from CWD and binds the first `.mcp.json` it finds.
# Pre-migration files reference `jarvis/scripts/...` as a *relative* path,
# which only resolves when CWD == the legacy file's parent. From any other
# project (redrobot, etc.) the server fails to launch. Detect by JSON content,
# not just filename, so we don't quarantine unrelated parent-dir MCP configs.
_LEGACY_RELATIVE_JARVIS_PATTERN = re.compile(r"^jarvis[\\/]")


def _transform_json_paths(node: Any, repo_root_posix: str) -> Any:
    """Rewrite relative `scripts/...` and `config/...` references to
    absolute paths inside the jarvis repo. JSON-aware walk preserves
    structure while only touching string leaves."""
    if isinstance(node, str):
        return _POSIX_PATH_PATTERN.sub(
            lambda m: f"{repo_root_posix}/{m.group(1)}/", node
        )
    if isinstance(node, list):
        return [_transform_json_paths(x, repo_root_posix) for x in node]
    if isinstance(node, dict):
        return {k: _transform_json_paths(v, repo_root_posix) for k, v in node.items()}
    return node


def _references_relative_jarvis(node: Any) -> bool:
    """True if any string leaf is a relative path beginning with `jarvis/` or `jarvis\\`."""
    if isinstance(node, str):
        return bool(_LEGACY_RELATIVE_JARVIS_PATTERN.match(node))
    if isinstance(node, list):
        return any(_references_relative_jarvis(x) for x in node)
    if isinstance(node, dict):
        return any(_references_relative_jarvis(v) for v in node.values())
    return False


def find_legacy_parent_mcp(repo_root: Path, max_depth: int = 4) -> list[Path]:
    """Return parent-dir `.mcp.json` files referencing jarvis with relative paths.

    Walks up to `max_depth` parents from `repo_root` (typically JARVIS_HOME).
    A file is flagged only when its JSON content contains a string starting
    with `jarvis/` or `jarvis\\` — i.e. a path that resolves correctly when
    CWD is the legacy file's parent dir but breaks elsewhere. Absolute paths
    (already-templated by a prior install) are left alone.
    """
    found: list[Path] = []
    parent = repo_root.parent
    for _ in range(max_depth):
        if parent == parent.parent:  # filesystem root
            break
        candidate = parent / ".mcp.json"
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
            else:
                if _references_relative_jarvis(data):
                    found.append(candidate)
        parent = parent.parent
    return found


def _quarantine_dest(path: Path) -> Path:
    """Compute non-clobbering `.bak.pre-jarvis-migration` destination for `path`."""
    base = path.with_name(path.name + ".bak.pre-jarvis-migration")
    if not base.exists():
        return base
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return path.with_name(f"{path.name}.bak.pre-jarvis-migration-{stamp}")


def _plan_mcp_user_registrations(
    source: Path,
    repo_root: Path,
    target_root: Path,
) -> list[Action]:
    """Generate a `register_mcp_user` action per server in `source` (.mcp.json).

    Claude Code does NOT read `~/.claude/.mcp.json` as user-scope MCP config —
    only project-scope (CWD walk) and the `mcpServers` block inside
    `~/.claude.json` (managed by `claude mcp add -s user`). Earlier installer
    revisions dropped the file under `target_root` where Claude Code never
    looked. This helper reads that file and plans `claude mcp add -s user`
    invocations that actually register servers in user scope.

    Path templating (`scripts/...` → `<repo_root>/scripts/...`) and
    `{{JARVIS_HOME}}` substitution are applied before serialising each spec
    into the action note, so apply-time runs see absolute paths.

    Also schedules a quarantine of any pre-existing `target_root/.mcp.json`
    left over from the dead file-drop strategy.
    """
    rendered = template_content(source, repo_root, target_root).decode("utf-8")
    data = json.loads(rendered)
    actions: list[Action] = []
    for name, spec in (data.get("mcpServers") or {}).items():
        payload = json.dumps({"name": name, "spec": spec}, ensure_ascii=False)
        actions.append(
            Action(
                kind="register_mcp_user",
                source=str(source),
                dest=name,
                template=False,
                group="mcp_config",
                note=payload,
            )
        )
    stale = target_root / ".mcp.json"
    if stale.is_file():
        actions.append(
            Action(
                kind="quarantine_file",
                source=str(stale),
                dest=str(_quarantine_dest(stale)),
                group="mcp_config",
                note="superseded by user-scope MCP registrations",
            )
        )
    return actions


def _register_mcp_user(name: str, spec: dict[str, Any]) -> None:
    """Run `claude mcp add -s user` for one server, removing any prior entry first.

    Idempotent: a stale entry is removed (errors swallowed — it may not exist)
    before the add. Subprocess args are passed as a list so values containing
    spaces or shell metacharacters survive intact.

    Argument order matters (#432). The Claude Code CLI declares variadic
    options:
        -e, --env <env...>
        -H, --header <header...>
    A variadic flag eats every following token until the next flag (or `--`),
    including positional arguments. Putting `-H`/`-e` BEFORE the positional
    `<name>` causes the parser to consume `<name>` as a header/env value and
    fail with `error: missing required argument 'name'`.

    Fix: place positionals first, then the variadic flags. For stdio, the
    `--` separator marks the end of options, so `-e` between `<name>` and
    `--` is safe.
    """
    subprocess.run(
        ["claude", "mcp", "remove", "-s", "user", name],
        check=False,
        capture_output=True,
    )
    cmd: list[str] = ["claude", "mcp", "add", "-s", "user"]
    transport = spec.get("type")
    if transport in {"http", "sse"}:
        # Order: --transport <t> <name> <url> -H ... -H ...
        # Headers AFTER positionals so the -H variadic doesn't swallow them.
        cmd += ["--transport", transport, name, spec["url"]]
        for hk, hv in (spec.get("headers") or {}).items():
            cmd += ["-H", f"{hk}: {hv}"]
    else:
        # Order: <name> -e ... -- <command> <args...>
        # Env flags AFTER name so the -e variadic doesn't swallow it; the
        # `--` separator then marks the boundary before the inner command.
        cmd += [name]
        for ek, ev in (spec.get("env") or {}).items():
            cmd += ["-e", f"{ek}={ev}"]
        cmd += ["--", spec["command"], *spec.get("args", [])]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"claude mcp add failed for {name!r}: {result.stderr.strip() or result.stdout.strip()}"
        )


def _substitute_placeholders(text: str, repo_root: Path, claude_home: Path) -> str:
    return (
        text.replace("{{JARVIS_HOME}}", repo_root.as_posix())
        .replace("{{CLAUDE_USER_HOME}}", claude_home.as_posix())
    )


def template_content(source: Path, repo_root: Path, claude_home: Path) -> bytes:
    """Read source, apply templating, return bytes to write at dest.

    For .json files: parse, rewrite relative `scripts/`/`config/` paths to
    absolute, pretty-print. For other files: plain placeholder replace.
    Non-text / non-json files fall back to a raw copy (no transformation).
    """
    ext = source.suffix.lower()
    raw = source.read_bytes()
    if ext == ".json":
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return raw
        transformed = _transform_json_paths(data, repo_root.as_posix())
        rendered = json.dumps(transformed, indent=2, ensure_ascii=False) + "\n"
        return _substitute_placeholders(rendered, repo_root, claude_home).encode(
            "utf-8"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    return _substitute_placeholders(text, repo_root, claude_home).encode("utf-8")


# ---------- planning ----------


def build_plan(
    manifest: dict[str, Any],
    repo_root: Path,
    target_root_override: str | None = None,
) -> Plan:
    target_root = _expand(
        target_root_override or manifest.get("target_root", "~/.claude")
    )
    current_sha = current_git_sha(repo_root)
    state, previous_sha = detect_state(target_root, current_sha)

    actions: list[Action] = []

    if state == "current":
        return Plan(
            state=state,
            actions=actions,
            backup_path=None,
            current_sha=current_sha,
            previous_sha=previous_sha,
            target_root=target_root,
            repo_root=repo_root,
        )

    for group in manifest.get("groups") or []:
        if not group.get("enabled"):
            continue
        gid = group.get("id", "?")
        for entry in group.get("files") or []:
            src = repo_root / entry["source"]
            install_as = entry.get("install_as")
            if install_as == "user_mcp_registrations":
                actions.extend(
                    _plan_mcp_user_registrations(src, repo_root, target_root)
                )
                continue
            if install_as is not None:
                raise ValueError(
                    f"manifest group {gid!r}: unknown install_as {install_as!r}"
                )
            dest = target_root / entry["dest"]
            # `merge: true` → deep-merge JSON instead of plain overwrite.
            # Preserves user keys not owned by jarvis (M3 #338).
            kind = "merge_json" if entry.get("merge") else "copy_file"
            actions.append(
                Action(
                    kind=kind,
                    source=str(src),
                    dest=str(dest),
                    template=bool(entry.get("template")),
                    group=gid,
                )
            )
        for entry in group.get("directories") or []:
            src = repo_root / entry["source"]
            dest = target_root / entry["dest"]
            include = entry.get("include")
            actions.append(
                Action(
                    kind="copy_dir",
                    source=str(src),
                    dest=str(dest),
                    template=bool(entry.get("template")),
                    group=gid,
                    note=f"include={include}" if include else "",
                )
            )

    for legacy in find_legacy_parent_mcp(repo_root):
        actions.append(
            Action(
                kind="quarantine_file",
                source=str(legacy),
                dest=str(_quarantine_dest(legacy)),
                group="legacy_mcp",
                note="parent-dir .mcp.json shadows ~/.claude/.mcp.json",
            )
        )

    actions.append(
        Action(
            kind="write_version",
            source=None,
            dest=str(target_root / manifest.get("version_marker", ".jarvis-version")),
            note=current_sha,
        )
    )

    for env in manifest.get("env_vars") or []:
        value = env.get("value", "").format(repo_root=str(repo_root))
        actions.append(
            Action(
                kind="set_env",
                source=None,
                dest=env["name"],
                note=value,
            )
        )

    # Backup only when target_root already exists AND we have destructive actions.
    has_writes = any(
        a.kind in {"copy_file", "copy_dir", "merge_json"} for a in actions
    )
    backup_path: Path | None = None
    if target_root.exists() and has_writes:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        prefix = (manifest.get("backup") or {}).get("prefix", ".claude.backup-")
        backup_path = target_root.parent / f"{prefix}{stamp}"

    return Plan(
        state=state,
        actions=actions,
        backup_path=backup_path,
        current_sha=current_sha,
        previous_sha=previous_sha,
        target_root=target_root,
        repo_root=repo_root,
    )


# ---------- execution ----------


def _copy_dir(
    src: Path,
    dest: Path,
    include: Iterable[str] | None,
    template: bool,
    repo_root: Path,
    claude_home: Path,
) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    allowed = set(include) if include else None
    for child in src.iterdir():
        if allowed is not None and child.name not in allowed:
            continue
        if child.is_dir():
            _copy_dir(
                child, dest / child.name, None, template, repo_root, claude_home
            )
        else:
            _copy_file(child, dest / child.name, template, repo_root, claude_home)


def _copy_file(
    src: Path,
    dest: Path,
    template: bool,
    repo_root: Path,
    claude_home: Path,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if template:
        dest.write_bytes(template_content(src, repo_root, claude_home))
    else:
        shutil.copy2(src, dest)


# Keys inside `settings.json.hooks` and `.mcp.json.mcpServers` are treated
# as "wholesale-replace on conflict": when the source declares a hook event
# or MCP server, it overwrites the target's entry for that key and leaves
# every other key alone. Per-child-dict replace is the only strategy that
# stays idempotent (re-apply never duplicates) while still letting users
# keep custom entries under events/servers jarvis doesn't own.
_JARVIS_OWNED_REPLACE_PARENTS = ("hooks", "mcpServers")


def _deep_merge_jarvis_json(existing: Any, source: Any) -> Any:
    """Merge `source` onto `existing` using jarvis-aware semantics.

    - For dict parents named in `_JARVIS_OWNED_REPLACE_PARENTS`
      (top-level `hooks`, `mcpServers`): each child key in `source`
      wholesale replaces the same key in `existing`; children in
      `existing` not mentioned by `source` are preserved.
    - For other dicts: recurse.
    - For non-dicts at the leaf: `source` wins.

    Not a general-purpose deep-merge — tuned for the two files M3 ships.
    """
    if not isinstance(existing, dict) or not isinstance(source, dict):
        return source
    out = dict(existing)
    for key, src_val in source.items():
        if (
            key in _JARVIS_OWNED_REPLACE_PARENTS
            and isinstance(src_val, dict)
            and isinstance(out.get(key), dict)
        ):
            merged_child = dict(out[key])
            for child_key, child_val in src_val.items():
                merged_child[child_key] = child_val
            out[key] = merged_child
        elif isinstance(src_val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_jarvis_json(out[key], src_val)
        else:
            out[key] = src_val
    return out


def _merge_json_file(
    src: Path,
    dest: Path,
    template: bool,
    repo_root: Path,
    claude_home: Path,
) -> None:
    """Write `src` to `dest`, deep-merging with any existing dest JSON.

    If dest exists and parses as JSON, merge (user keys jarvis doesn't own
    are preserved). If dest is absent or unparseable, fall through to a
    plain write — identical to `_copy_file` in that case.
    """
    if template:
        new_bytes = template_content(src, repo_root, claude_home)
    else:
        new_bytes = src.read_bytes()
    try:
        new_data = json.loads(new_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Not JSON — fall back to plain write. Shouldn't happen for
        # manifest entries flagged `merge: true`, but safe by default.
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(new_bytes)
        return

    merged: Any = new_data
    if dest.exists():
        try:
            existing = json.loads(dest.read_text(encoding="utf-8"))
            merged = _deep_merge_jarvis_json(existing, new_data)
        except (OSError, json.JSONDecodeError):
            # Unparseable existing → treat as absent (backup already captured it).
            merged = new_data

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _set_env(name: str, value: str, platform: str) -> None:
    if platform == "windows":
        result = subprocess.run(["setx", name, value], check=False, capture_output=True)
        if result.returncode != 0:
            stderr_msg = result.stderr.decode(errors='replace').strip()
            print(
                f"setx {name} failed (rc={result.returncode}): {stderr_msg}",
                file=sys.stderr
            )
    else:
        rc_files = [Path.home() / ".bashrc", Path.home() / ".zshrc"]
        line = f'export {name}="{value}"\n'
        for rc in rc_files:
            if not rc.exists():
                continue
            existing = rc.read_text(encoding="utf-8")
            if f"export {name}=" in existing:
                continue
            rc.write_text(existing + "\n# added by jarvis installer\n" + line,
                          encoding="utf-8")


def _platform() -> str:
    return "windows" if os.name == "nt" else "posix"


def _copy_tolerant(src: str, dst: str, *, follow_symlinks: bool = True) -> str | None:
    """shutil.copy2 that tolerates entries which vanish or lock mid-copy.

    Claude Code actively rotates files under ``~/.claude/debug/`` while the
    installer runs. ``shutil.copytree`` defaults to aggregate-then-raise on
    such races, aborting the whole backup (#350). These artefacts aren't
    user data — skip with a stderr note and continue instead of failing
    the install.

    Tolerated errors:
    - ``FileNotFoundError`` — entry disappeared between scandir and copy
    - ``PermissionError`` — entry is held open with an exclusive lock
      (common on Windows while a log file is being rotated / appended to)
    """
    try:
        return shutil.copy2(src, dst, follow_symlinks=follow_symlinks)
    except (FileNotFoundError, PermissionError) as e:
        print(f"backup: skipped unreadable entry {src} ({e})", file=sys.stderr)
        return None


def _backup_target_root(target_root: Path, backup_path: Path) -> None:
    """Copy ``target_root`` to ``backup_path`` tolerating mid-copy disappearance/locks.

    ``symlinks=True`` preserves symlinks as symlinks rather than dereferencing;
    combined with ``ignore_dangling_symlinks=True`` this future-proofs against
    broken junctions inside the target tree (Claude Code can create them).
    """
    shutil.copytree(
        target_root,
        backup_path,
        copy_function=_copy_tolerant,
        symlinks=True,
        ignore_dangling_symlinks=True,
    )


def apply_plan(
    plan: Plan,
    manifest: dict[str, Any],
    run_env: Callable[[str, str, str], None] | None = _set_env,
    register_mcp: Callable[[str, dict[str, Any]], None] | None = _register_mcp_user,
) -> None:
    if plan.state == "current":
        return
    if plan.backup_path is not None:
        _backup_target_root(plan.target_root, plan.backup_path)

    plan.target_root.mkdir(parents=True, exist_ok=True)

    for action in plan.actions:
        if action.kind == "copy_file":
            _copy_file(
                Path(action.source),
                Path(action.dest),
                action.template,
                plan.repo_root,
                plan.target_root,
            )
        elif action.kind == "merge_json":
            _merge_json_file(
                Path(action.source),
                Path(action.dest),
                action.template,
                plan.repo_root,
                plan.target_root,
            )
        elif action.kind == "copy_dir":
            # Re-derive include from manifest — cheaper than threading it through.
            include = _include_for(manifest, action.group, action.source, plan.repo_root)
            _copy_dir(
                Path(action.source),
                Path(action.dest),
                include,
                action.template,
                plan.repo_root,
                plan.target_root,
            )
        elif action.kind == "quarantine_file":
            src = Path(action.source)
            dst = Path(action.dest)
            if src.exists():
                src.rename(dst)
                print(f"quarantined legacy {src} -> {dst}", file=sys.stderr)
        elif action.kind == "register_mcp_user":
            if register_mcp is not None:
                payload = json.loads(action.note)
                register_mcp(payload["name"], payload["spec"])
        elif action.kind == "write_version":
            Path(action.dest).write_text(action.note + "\n", encoding="utf-8")
        elif action.kind == "set_env":
            if run_env is not None:
                run_env(action.dest, action.note, _platform())


def _include_for(
    manifest: dict[str, Any],
    group_id: str,
    source: str,
    repo_root: Path,
) -> list[str] | None:
    """Return include filter for a directory group if source matches.

    Compares as absolute paths (action.source is absolute via build_plan;
    entry['source'] is repo-relative in the manifest, resolved against
    repo_root here). Earlier revisions compared a relative manifest path
    against an absolute action path and silently never matched, disabling
    every directory-group whitelist in production (caught by
    `test_apply_plan_creates_files_and_version_marker` after #413).
    """
    source_abs = Path(source).resolve()
    for group in manifest.get("groups") or []:
        if group.get("id") != group_id:
            continue
        for entry in group.get("directories") or []:
            entry_abs = (repo_root / entry["source"]).resolve()
            if entry_abs == source_abs:
                return entry.get("include")
    return None


# ---------- rollback / health ----------


def prune_backups(target_root: Path, prefix: str, retain: int) -> list[Path]:
    parent = target_root.parent
    if not parent.exists():
        return []
    backups = sorted(
        (p for p in parent.iterdir() if p.is_dir() and p.name.startswith(prefix)),
        key=lambda p: p.name,
    )
    dropped: list[Path] = []
    while len(backups) > retain:
        victim = backups.pop(0)
        shutil.rmtree(victim, ignore_errors=True)
        dropped.append(victim)
    return dropped


def rollback(target_root: Path, backup_path: Path) -> None:
    if not backup_path.exists():
        raise FileNotFoundError(f"backup {backup_path} not found")
    if target_root.exists():
        shutil.rmtree(target_root)
    shutil.copytree(backup_path, target_root)


def _rollback_failed_apply(plan: Plan) -> None:
    """Restore target_root to pre-apply state after a failed apply.

    - outdated/current path → restore from backup (backup_path is set).
    - fresh path → backup_path is None (nothing to restore from), so rmtree
      the half-written target so the next run starts clean. Without this,
      a failed fresh install leaves a stub that `detect_state` reads as
      outdated, masking the real failure.
    """
    if plan.backup_path and plan.backup_path.exists():
        print(f"rolling back from {plan.backup_path}", file=sys.stderr)
        rollback(plan.target_root, plan.backup_path)
        return
    if plan.state == "fresh" and plan.target_root.exists():
        print(
            f"fresh install failed — removing {plan.target_root}", file=sys.stderr
        )
        shutil.rmtree(plan.target_root, ignore_errors=True)


def run_health_check(manifest: dict[str, Any], repo_root: Path) -> tuple[bool, list[str]]:
    hc = manifest.get("health_check") or {}
    if not hc.get("enabled"):
        return True, []
    logs: list[str] = []
    for cmd in hc.get("commands") or []:
        # Use shlex so paths with spaces survive — `cmd.split()` breaks them.
        # posix=False on Windows keeps backslashes intact.
        argv = shlex.split(cmd, posix=(os.name != "nt"))
        try:
            # Force UTF-8 for subprocess I/O — text=True alone defaults to
            # locale.getpreferredencoding(False), which on Russian Windows is
            # cp1251 and can't decode the em-dashes / Cyrillic that session
            # scripts emit. errors="replace" keeps the reader threads alive
            # even if a rogue script ever emits garbage bytes (#352).
            result = subprocess.run(
                argv,
                cwd=repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logs.append(f"FAIL {cmd}: {exc}")
            return False, logs
        if result.returncode != 0:
            logs.append(
                f"FAIL {cmd} exit={result.returncode} stderr={result.stderr[:200]}"
            )
            return False, logs
        logs.append(f"OK   {cmd}")
    return True, logs


# ---------- printing ----------


def format_plan(plan: Plan) -> str:
    lines = [
        f"state:        {plan.state}",
        f"repo_root:    {plan.repo_root}",
        f"target_root:  {plan.target_root}",
        f"current_sha:  {plan.current_sha}",
        f"previous_sha: {plan.previous_sha or '(none)'}",
        f"backup:       {plan.backup_path or '(not needed)'}",
        f"actions:      {len(plan.actions)}",
    ]
    if plan.actions:
        lines.append("")
        for a in plan.actions:
            if a.kind == "copy_file":
                lines.append(
                    f"  copy_file  [{a.group:>14}] {a.source} -> {a.dest}"
                    + ("  (template)" if a.template else "")
                )
            elif a.kind == "merge_json":
                lines.append(
                    f"  merge_json [{a.group:>14}] {a.source} -> {a.dest}"
                    + ("  (template)" if a.template else "")
                )
            elif a.kind == "copy_dir":
                extra = f"  {a.note}" if a.note else ""
                lines.append(
                    f"  copy_dir   [{a.group:>14}] {a.source} -> {a.dest}{extra}"
                )
            elif a.kind == "quarantine_file":
                lines.append(
                    f"  quarantine [{a.group:>14}] {a.source} -> {a.dest}"
                    + (f"  ({a.note})" if a.note else "")
                )
            elif a.kind == "register_mcp_user":
                lines.append(
                    f"  mcp_user   [{a.group:>14}] claude mcp add -s user {a.dest}"
                )
            elif a.kind == "write_version":
                lines.append(f"  write_ver  -> {a.dest}  sha={a.note[:12]}")
            elif a.kind == "set_env":
                lines.append(f"  set_env    {a.dest}={a.note}")
    return "\n".join(lines)


# ---------- CLI ----------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jarvis-installer",
        description="Install/sync Jarvis agent machinery into ~/.claude/.",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help=f"Path to manifest (default: {DEFAULT_MANIFEST} next to repo root)",
    )
    parser.add_argument("--target", default=None, help="Override target_root")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform the install. Default is dry-run (plan only).",
    )
    parser.add_argument(
        "--skip-env",
        action="store_true",
        help="Skip env-var writes even on --apply (useful in CI/tests).",
    )
    parser.add_argument(
        "--rollback",
        metavar="BACKUP_PATH",
        default=None,
        help="Restore target_root from BACKUP_PATH and exit.",
    )
    parser.add_argument(
        "--skip-health-check",
        action="store_true",
        help="Skip post-install health check (not recommended).",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    manifest_path = Path(args.manifest) if args.manifest else repo_root / DEFAULT_MANIFEST
    manifest = load_manifest(manifest_path)

    if args.rollback:
        target_root = _expand(args.target or manifest.get("target_root", "~/.claude"))
        rollback(target_root, Path(args.rollback))
        print(f"rolled back {target_root} from {args.rollback}")
        return 0

    plan = build_plan(manifest, repo_root, args.target)
    print(format_plan(plan))

    if not args.apply:
        print("\n(dry-run — re-run with --apply to execute)")
        return 0

    if plan.state == "current":
        print("\nno-op — target already at current SHA")
        return 0

    env_runner = None if args.skip_env else _set_env
    try:
        apply_plan(plan, manifest, run_env=env_runner)
    except Exception as exc:  # noqa: BLE001
        print(f"\napply failed: {exc}", file=sys.stderr)
        _rollback_failed_apply(plan)
        return 2

    if not args.skip_health_check:
        ok, logs = run_health_check(manifest, repo_root)
        for line in logs:
            print(line)
        if not ok:
            print("\nhealth check failed", file=sys.stderr)
            _rollback_failed_apply(plan)
            return 3

    backup_cfg = manifest.get("backup") or {}
    dropped = prune_backups(
        plan.target_root,
        backup_cfg.get("prefix", ".claude.backup-"),
        int(backup_cfg.get("retain", 5)),
    )
    for d in dropped:
        print(f"pruned old backup: {d}")

    print("\napply complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())

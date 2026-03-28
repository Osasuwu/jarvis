"""Skill auto-discovery and unified dispatch.

Skills are defined by SKILL.md files in skills/*/ directories.
Frontmatter in SKILL.md declares agent configuration and optional Python handler.

Two execution modes:
1. Prompt-based (default): SKILL.md body is sent to Claude as a prompt
2. Handler-based: a Python async function handles the full pipeline

Adding a new skill = create skills/<name>/SKILL.md with frontmatter. Done.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from jarvis.config import RuntimeConfig
from jarvis.costs import check_daily_budget, record_execution
from jarvis.executor import execute_query


ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"

JARVIS_IDENTITY = (
    "You are Jarvis, a personal AI agent. "
    "Be concise, direct, and respond in the user's language."
)


class UnsupportedCommandError(ValueError):
    pass


@dataclass(frozen=True)
class SkillSpec:
    name: str
    command: str
    description: str
    model: str = "haiku"
    tools: tuple[str, ...] = ()
    max_budget_usd: float = 0.10
    handler: str = ""
    background: bool = False
    skill_file: Path = field(default_factory=Path)


@dataclass
class SkillResult:
    text: str
    success: bool = True
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


# Built-in chat fallback (no SKILL.md needed).
CHAT_SPEC = SkillSpec(
    name="chat",
    command="chat",
    description="General conversation",
    model="haiku",
    tools=(),
    max_budget_usd=0.05,
)


# ── Frontmatter parsing ────────────────────────────────────────────────


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split SKILL.md into (frontmatter_dict, body_content)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text

    fm_block = text[3:end].strip()
    body = text[end + 3:].strip()

    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    return fm, body


def _unquote(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        return raw[1:-1]
    return raw


def _parse_tools(raw: str) -> tuple[str, ...]:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        items = raw[1:-1].split(",")
        return tuple(item.strip().strip("\"'") for item in items if item.strip())
    return ()


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"true", "yes", "1"}


def _parse_float(raw: str, default: float) -> float:
    try:
        return float(raw.strip())
    except (ValueError, TypeError):
        return default


# ── Auto-discovery ──────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def discover_skills() -> dict[str, SkillSpec]:
    """Auto-discover all skills from skills/*/SKILL.md.

    Returns dict mapping command (e.g. "/triage") to SkillSpec.
    Cached after first call; restart to pick up new skills.
    """
    skills: dict[str, SkillSpec] = {}
    if not SKILLS_DIR.exists():
        return skills

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        text = skill_file.read_text(encoding="utf-8")
        fm, _body = _split_frontmatter(text)

        command = f"/{skill_dir.name}"
        name = _unquote(fm.get("name", skill_dir.name))
        description = _unquote(fm.get("description", f"Run {command}"))

        spec = SkillSpec(
            name=name,
            command=command,
            description=description,
            model=fm.get("model", "haiku"),
            tools=_parse_tools(fm.get("tools", "")),
            max_budget_usd=_parse_float(fm.get("max_budget_usd", ""), 0.10),
            handler=fm.get("handler", ""),
            background=_parse_bool(fm.get("background", "")),
            skill_file=skill_file,
        )
        skills[command] = spec

    return skills


def get_skill(command: str) -> SkillSpec | None:
    """Look up a skill by command name. Returns None if not found."""
    return discover_skills().get(command)


def supported_commands() -> list[str]:
    """Return sorted list of all discovered skill commands."""
    return sorted(discover_skills().keys())


# Keep old name for any remaining callers.
def get_skill_command_map() -> dict[str, Path]:
    """Backwards-compatible: returns {command: skill_file_path}."""
    return {cmd: spec.skill_file for cmd, spec in discover_skills().items()}


# ── Handler resolution ──────────────────────────────────────────────────


def _resolve_handler(handler_path: str):
    """Import 'module.path:function_name' and return the callable."""
    if ":" not in handler_path:
        raise ImportError(f"Handler must be 'module:function', got: {handler_path}")
    module_path, func_name = handler_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    func = getattr(module, func_name)
    return func


# ── Prompt building ─────────────────────────────────────────────────────


def _build_prompt(skill: SkillSpec, args: str) -> str:
    """Build a prompt from SKILL.md body for prompt-based skills."""
    text = skill.skill_file.read_text(encoding="utf-8")
    _fm, body = _split_frontmatter(text)

    prompt = f"{JARVIS_IDENTITY}\n\nExecute: {skill.command}"
    if args:
        prompt += f"\nTopic/arguments: {args}"
    prompt += f"\n\n{body}\n"
    return prompt


def build_prompt_for_user_input(user_input: str) -> str:
    """Build prompt for any user input. Used by dry-run mode."""
    text = user_input.strip()
    if not text:
        raise UnsupportedCommandError("Input is empty.")

    if text.startswith("/"):
        command = text.split(maxsplit=1)[0]
        args = text[len(command):].strip()
        skill = get_skill(command)
        if skill is None:
            available = ", ".join(supported_commands())
            raise UnsupportedCommandError(
                f"Unsupported command: {command}. Available: {available}"
            )
        return _build_prompt(skill, args)

    return f"{JARVIS_IDENTITY}\n\n{text}\n"


# ── Unified dispatch ────────────────────────────────────────────────────


def _parse_command_input(user_input: str) -> tuple[str, str]:
    """Parse user input into (command, args). Non-commands return ('chat', text)."""
    text = user_input.strip()
    if not text:
        return "chat", ""
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        command = parts[0]
        args = parts[1].strip() if len(parts) > 1 else ""
        return command, args
    return "chat", text


async def dispatch_skill(
    user_input: str,
    config: RuntimeConfig,
    *,
    session_id: str = "",
) -> SkillResult:
    """Unified dispatch: auto-routes to handler or prompt-based execution.

    This is the single entry point for all skill execution.
    - Handler skills: imports and calls the Python handler function
    - Prompt skills: builds prompt from SKILL.md, sends to Claude via SDK
    - Chat: sends plain text to Claude
    - Plain text: intent-classified and routed to matching skill when confident

    Budget checking and cost recording are handled here.
    """
    command, args = _parse_command_input(user_input)

    # ── Intent routing for plain text ──
    routing_footer = ""
    if command == "chat":
        from jarvis.intent_router import (  # noqa: WPS433
            format_routing_transparency,
            route_user_input_async,
        )
        route = await route_user_input_async(user_input)
        routing_footer = "\n\n" + format_routing_transparency(route)
        if route.was_routed:
            command, args = _parse_command_input(route.resolved_input)

    # Resolve skill spec
    if command == "chat":
        skill = CHAT_SPEC
    else:
        skill = get_skill(command)
        if skill is None:
            available = ", ".join(supported_commands())
            return SkillResult(
                text=f"Unknown command: {command}. Available: {available}",
                success=False,
            )

    # Budget gate
    allowed, remaining = check_daily_budget(config.budget.per_day_usd)
    if not allowed:
        return SkillResult(
            text=f"Daily budget exhausted (${config.budget.per_day_usd:.2f} limit).",
            success=False,
        )

    query_budget = min(skill.max_budget_usd, config.budget.per_query_usd, remaining)

    # ── Handler-based skill ──
    if skill.handler:
        try:
            handler = _resolve_handler(skill.handler)
        except (ImportError, AttributeError) as exc:
            return SkillResult(text=f"Handler import failed: {exc}", success=False)

        try:
            result: SkillResult = await handler(config, args)
        except Exception as exc:
            return SkillResult(text=f"Handler error: {exc}", success=False)

        if result.cost_usd > 0 or result.input_tokens > 0:
            record_execution(
                model=result.model or skill.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                session_id=session_id,
            )

        if routing_footer:
            return SkillResult(
                text=result.text + routing_footer,
                success=result.success,
                cost_usd=result.cost_usd,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                model=result.model,
            )
        return result

    # ── Prompt-based skill ──
    if command == "chat":
        prompt = f"{JARVIS_IDENTITY}\n\n{args}\n"
    else:
        prompt = _build_prompt(skill, args)

    exec_result = await execute_query(
        prompt,
        model=skill.model,
        allowed_tools=skill.tools,
        max_budget_usd=query_budget,
    )

    if exec_result.cost_usd > 0 or exec_result.input_tokens > 0:
        record_execution(
            model=skill.model,
            input_tokens=exec_result.input_tokens,
            output_tokens=exec_result.output_tokens,
            cost_usd=exec_result.cost_usd,
            session_id=session_id,
        )

    result_text = exec_result.text if exec_result.success else exec_result.error
    return SkillResult(
        text=result_text + routing_footer,
        success=exec_result.success,
        cost_usd=exec_result.cost_usd,
        input_tokens=exec_result.input_tokens,
        output_tokens=exec_result.output_tokens,
        model=skill.model,
    )

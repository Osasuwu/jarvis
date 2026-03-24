from __future__ import annotations

from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"

JARVIS_IDENTITY = (
    "You are Jarvis, a personal AI agent. "
    "Be concise, direct, and respond in the user's language."
)


class UnsupportedCommandError(ValueError):
    pass


@lru_cache(maxsize=1)
def get_skill_command_map() -> dict[str, Path]:
    command_map: dict[str, Path] = {}
    if not SKILLS_DIR.exists():
        return command_map

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        command_map[f"/{skill_dir.name}"] = skill_file

    return command_map


def supported_commands() -> list[str]:
    return sorted(get_skill_command_map().keys())


def _parse_command(text: str) -> tuple[str, str]:
    """Parse '/command arg1 arg2' into ('/command', 'arg1 arg2')."""
    parts = text.split(maxsplit=1)
    command = parts[0]
    args = parts[1].strip() if len(parts) > 1 else ""
    return command, args


def build_prompt_for_command(text: str) -> str:
    command, args = _parse_command(text)

    skill_map = get_skill_command_map()
    skill_file = skill_map.get(command)
    if skill_file is None:
        supported = ", ".join(supported_commands())
        raise UnsupportedCommandError(f"Unsupported command: {command}. Supported: {supported}")

    if not skill_file.exists():
        raise FileNotFoundError(f"Skill definition not found: {skill_file}")

    skill_instructions = skill_file.read_text(encoding="utf-8")

    prompt = f"{JARVIS_IDENTITY}\n\nExecute: {command}"
    if args:
        prompt += f"\nTopic/arguments: {args}"
    prompt += f"\n\n{skill_instructions}\n"
    return prompt


def build_prompt_for_user_input(user_input: str) -> str:
    text = user_input.strip()
    if not text:
        raise UnsupportedCommandError("Input is empty.")

    if text.startswith("/"):
        return build_prompt_for_command(text)

    return f"{JARVIS_IDENTITY}\n\n{text}\n"

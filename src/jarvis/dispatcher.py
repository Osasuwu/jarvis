from __future__ import annotations

from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"

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
    return sorted([*get_skill_command_map().keys(), "/research <topic>"])


def _build_research_prompt(command: str) -> str:
    topic = command.removeprefix("/research").strip()
    if not topic:
        raise UnsupportedCommandError("Usage: /research <topic>")

    return (
        "You are Jarvis researcher. Produce source-backed research with confidence score.\n\n"
        f"Topic: {topic}\n\n"
        "Output format:\n"
        "1) Short summary\n"
        "2) Key findings\n"
        "3) Risks and unknowns\n"
        "4) Sources\n"
        "5) Confidence score (0-100) with justification\n"
    )



def build_prompt_for_command(command: str) -> str:
    if command.startswith("/research"):
        return _build_research_prompt(command)

    skill_file = get_skill_command_map().get(command)
    if skill_file is None:
        supported = ", ".join(supported_commands())
        raise UnsupportedCommandError(f"Unsupported command: {command}. Supported: {supported}")

    if not skill_file.exists():
        raise FileNotFoundError(f"Skill definition not found: {skill_file}")

    skill_instructions = skill_file.read_text(encoding="utf-8")
    return (
        "You are Jarvis. Execute the requested command strictly using the skill instructions below.\n\n"
        f"Requested command: {command}\n\n"
        "=== SKILL INSTRUCTIONS START ===\n"
        f"{skill_instructions}\n"
        "=== SKILL INSTRUCTIONS END ===\n"
    )


def build_prompt_for_user_input(user_input: str) -> str:
    text = user_input.strip()
    if not text:
        raise UnsupportedCommandError("Input is empty.")

    if text.startswith("/"):
        return build_prompt_for_command(text)

    return (
        "You are Jarvis, a personal AI assistant for project and research workflows. "
        "Respond clearly in the user's language, and ask brief clarifying questions only when needed.\n\n"
        f"User message:\n{text}\n"
    )

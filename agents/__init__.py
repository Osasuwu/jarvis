"""Jarvis Pillar 7 — persistent LangGraph agents.

Runs alongside Claude Code (not as replacement). Uses Ollama as local LLM
and PostgreSQL checkpointer for state that survives restart.

See docs/agents/ for setup and operational notes.
"""

__all__ = [
    "config",
    "event_monitor",
    "github_client",
    "ollama_client",
    "supabase_client",
]

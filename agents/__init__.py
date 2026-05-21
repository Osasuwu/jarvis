"""Jarvis Pillar 7 — persistent LangGraph agents.

Runs alongside Claude Code (not as replacement). Uses Ollama as local LLM
and PostgreSQL checkpointer for state that survives restart.

See docs/agents/ for setup and operational notes.
"""

__all__ = [
    "config",
    "escalation",
    "event_monitor",
    "executor",
    "github_client",
    "ollama_client",
    "perception_github",
    "safety",
    "scheduler",
    "supabase_client",
    "task_queue",
    "usage_probe",
]

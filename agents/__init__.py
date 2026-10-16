"""Jarvis plan-review pipeline — shared grammar for planner/critic subagents.

The reactive-core agent stack (orchestrator, wake_driver, task_dispatch,
sandcastle, Supabase/Ollama bridges) was demolished in #1802. What remains
here is the plan-lock grammar and classification logic consumed by
``.claude/agents/planner.md``, the ``critic-*`` subagents, lane intake
(``.github/scripts/lane_intake.py``) and ``scripts/to_tickets_afk_fit.py``.
"""

__all__ = [
    "critic_verdict",
    "implement_plan_gate",
    "plan_assumptions",
    "plan_classifier",
    "plan_lock",
    "plan_review_config",
]

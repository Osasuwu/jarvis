"""Dotted-path transport double for agents.notify.resolve_notifier tests (#1547).

Resolvable as ``notify_transport_double:fake_transport`` via the shared
``tests/_support`` pythonpath entry — mirrors how an operator would point
``NOTIFY_TRANSPORT`` at a real ``pkg.mod:fn`` callable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.orchestrator import Decision

calls: list["Decision"] = []


def fake_transport(decision: "Decision") -> bool:
    calls.append(decision)
    return True

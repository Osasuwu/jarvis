"""repo-baseline: canonical, re-syncable GitHub-repo setup.

Pure decision core (Manifest, Renderer, Planner, LabelMigrator) behind
thin gh/REST shells. All dry-run safe — no network or filesystem mutation.
"""

from .manifest import FileClass, Manifest, AxisProfile
from .renderer import Renderer, RenderError
from .planner import Planner, Action, ActionKind

__all__ = [
    "FileClass",
    "Manifest",
    "AxisProfile",
    "Renderer",
    "RenderError",
    "Planner",
    "Action",
    "ActionKind",
]

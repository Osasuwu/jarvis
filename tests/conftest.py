"""Pytest configuration for jarvis tests."""

import sys
from pathlib import Path

# Add scripts directory to path for imports
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "scripts"))
sys.path.insert(0, str(repo_root))

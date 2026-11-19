"""Make the package's test helpers importable by module name.

pytest inserts a test module's directory into sys.path when the directory has no
__init__.py, which is how the agent-teams suite shares helpers. Declaring it
explicitly keeps that behaviour independent of invocation directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

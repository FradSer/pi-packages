"""Dependency-free sanitized legacy Harness configuration fixture."""

from __future__ import annotations


# This fixture is imported by the explicit live smoke, which must be runnable
# without installing the pytest test runner.
LEGACY = {
    "policies": [
        {
            "name": "no-project-memory-local-writes",
            "tools": ["write", "edit"],
            "require": {"path": "path", "pattern": r"(^|/)\.memory\.local(?:/|$)"},
            "paths": ["content", "newText", "edits.newText"],
            "pattern": r"[\s\S]+",
            "action": "block",
            "reason": "Use the canonical private memory root.",
        },
        {
            "name": "pi-kit-no-markdown-agent-run-helper",
            "tools": ["write", "edit"],
            "paths": ["content", "newText"],
            "require": {"path": "path", "pattern": r"^packages/kit/src/.*\.ts$"},
            "pattern": r"\bcreatePackageAgentRun\b",
            "action": "block",
            "reason": "Use the approved structured run API.",
        },
    ],
    "disabled": [],
    "skillPrompts": {},
    "learnedPolicies": {
        name: {"origin": "consolidation", "learnedAt": "2020-01-01T00:00:00Z"}
        for name in [
            "no-project-memory-local-writes",
            "pi-kit-no-markdown-agent-run-helper",
        ]
    },
}

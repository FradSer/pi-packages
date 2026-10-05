# Session Retrospective

The user has asked for a retrospective. Review the coding session and suggest improvements to the agent's environment, not changes to the product code.

Read the primary sources for the session: the current Pi session when available, or the supplied session log. If no session is specified, use the current one. Use the bundled [writing-for-agents](writing-for-agents.md) procedure for the style of any proposed guidance.

Look for candidates in these categories:

- **Navigation:** hidden dependencies, unclear file locations, or missing pointers that made the right source hard to find.
- **Automated checks:** existing test, typecheck, lint, filesystem, or CI gaps that could have caught a mistake.
- **Coding standards:** judgement calls the [code-review](code-review.md) procedure should enforce. Mechanical mistakes belong in deterministic checks instead.
- **Steering files:** rules in `AGENTS.md`, `CLAUDE.md`, or similar files that are too large, duplicated, or ineffective.
- **Tool economy:** expensive or repetitive commands that can be streamlined.
- **No-ops:** instructions that consume attention without changing agent behavior.
- **Information access:** missing read-only access to logs, documentation, or other sources needed to diagnose a problem.

Present the candidates in severity order. For each one, include the observed evidence, the smallest useful change, and whether it belongs in an automated check, a coding standard, or a steering file. Do not modify the repository while producing the retrospective; propose changes for the user to review.

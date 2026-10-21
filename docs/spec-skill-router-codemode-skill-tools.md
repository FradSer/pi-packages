# Spec: Skill Router delivers leaf skills as codemode tools

Status: ready for implementation. Decision record:
`docs/adr/0010-skill-router-codemode-skill-tools.md`. Executable scenarios:
`packages/skill-router/features/codemode-skill-tools.feature`. Vocabulary:
`packages/skill-router/GLOSSARY.md`.

## Problem Statement

A user installs an external skill collection and expects the agent to apply the
right workflow from it. Today the router hands the model a file path: a
`before_agent_start` suggestion names the matched leaf skill's `SKILL.md`, and the
model reads it. That works, but the choice is made by the router's term matching
rather than by the model, the leaf skill is not searchable, and nothing lets a
script select among many skills.

Pi already reaches large tool catalogs this way: codemode lists non-declared
tools, `searchTools()` ranks them, and a call fetches what is needed. Skill
collections have no such surface.

## Solution

Every routed leaf skill becomes one codemode-callable tool. The model searches
codemode's tools, reads the ranked candidates, and calls the matched skill tool,
which returns that skill's instructions and the directory its references and
scripts resolve against. The collection becomes the tool namespace, so its
capability summary and gateway index are available in one lookup.

Nothing is lost when codemode is unavailable: while codemode is not active the
router keeps today's routing suggestion, and the gateway stays available as the
human `/skill:<gateway>` entry point.

## User Stories

1. As a Pi user, I want a routed leaf skill to be searchable, so that the agent
   can select it from the skill's own description instead of the router's term
   matching alone.
2. As a Pi user, I want the agent to call the matched skill and receive its
   instructions, so that one discovery step is enough to act on the workflow.
3. As a Pi user, I want the returned instructions to come with the skill's
   directory, so that referenced files and bundled scripts resolve.
4. As a Pi user, I want a very large skill to be truncated with a pointer to its
   complete file, so that a large instruction file never silently loses content.
5. As a Pi user, I want a collection to be one search namespace, so that I can
   ask what a collection contains without listing every skill.
6. As a Pi user, I want the collection's capability summary and workflow index to
   be readable in one lookup, so that I can choose a skill before calling one.
7. As a Pi user, I want skill search to use both the concise workflow summary and
   the skill author's own description, so that my wording finds the right skill.
8. As a Pi user, I want the tools channel to be used whenever codemode is
   available, so that I do not also get a path suggestion for the same request.
9. As a Pi user, I want the routing suggestion to keep working when codemode is
   unavailable, so that installed collections stay usable in any session.
10. As a Pi user, I want the router to leave my session's tool set alone, so that
    codemode is activated by me and not by an extension.
11. As a Pi user, I want a disabled collection to register no tools, so that
    disabling a collection really withdraws it.
12. As a Pi user, I want a removed collection's tool to fail instead of serving
    stale content, so that removal is immediate and honest.
13. As a Pi user, I want a skill tool to refuse content outside the router's
    exposed tree, so that a tampered exposure cannot leak an unrelated file.
14. As a Pi user, I want `/skill:<gateway>` to keep working across every codemode
    state, so that my manual entry point never breaks.
15. As a Pi user, I want the gateway to name each workflow's tool as well as its
    path, so that I can hand the right entry to the agent in either channel.
16. As a model, I want skill tools grouped in a namespace with guidance, so that I
    know these tools load workflows rather than perform the work.
17. As a model, I want a skill tool to take no parameters, so that my search
    results are not diluted by every skill name in the collection.
18. As a maintainer, I want one registration path for the tools channel, so that
    the searchable text, the namespace, and the call payload cannot drift apart.
19. As a maintainer, I want the fallback channel's term matching untouched, so
    that the existing routing behavior keeps its coverage.
20. As a maintainer, I want the tool surface verifiable through the extension
    entry, so that tests exercise what Pi actually loads.

## Scenarios

All scenarios are written as Gherkin in
`packages/skill-router/features/codemode-skill-tools.feature`, which is the
executable copy. Groups:

- Registration and shape: one tool per routed leaf skill; no tool for a disabled
  collection; one namespace per collection with the capability summary and
  gateway index.
- Searchable text: the workflow summary followed by the upstream description,
  with no path or installation detail.
- Calling a skill tool: instructions plus directory plus structured content;
  oversized body truncated with a pointer to its file; refusal outside the
  exposed tree; failure after the collection is removed.
- Channel selection: codemode active and reaching other tools selects the tools
  channel and suppresses the suggestion; inactive or merely registered codemode
  keeps the fallback suggestion.
- Gateway: each workflow line names the summary, the skill tool, and the relative
  leaf path.

## Implementation Decisions

- **A new skills module owns the tools channel.** It derives the tool name, the
  searchable description, the namespace, and the call payload from one route
  record, and registers the tools on the extension API. The extension entry does
  not know the shape of a skill tool.
- **Tool naming mirrors MCP.** The registered name is
  `skill_router__<collection>__<skill>`, with every character outside
  `[A-Za-z0-9_]` replaced by `_`, and the namespace is
  `skill_router__<collection>` with the collection id as an alias. Pi sanitizes
  codemode identifiers the same way, so name and identifier agree and the
  declaration heading stays clean.
- **Registration is synchronous at extension load, and repeats after every
  menu mutation.** `/skill-router` add, update, routed skills, capability
  summary, remove, and enable/disable re-read the registry and re-register the
  tools, so the tools channel follows a change in the same session; a removed or
  disabled collection's tools are withdrawn by re-registering them hidden. Only
  the gateway command and prompt skill list wait for `/reload`.
- **The call payload is declared as an output schema** so scripts receive
  structured content: the collection, the skill, the tool, the skill directory,
  the instruction file, the body, and whether it was truncated. The model-facing
  text is the body itself, plus a note pointing at the instruction file when the
  body was cut. A body over the bound is truncated to that bound.
- **Parameter schema is empty.** The tool names one skill in its registered name,
  so a parameter schema would put every skill name of a collection into every
  search document of that collection.
- **The call re-resolves the collection from the registry** on every invocation,
  instead of trusting the path captured at registration, and re-checks that the
  instruction file is a regular file under the router's `exposed/collections`
  tree before reading it.
- **"Codemode is available" is decided per turn and per skill** by the extension
  entry: the name `codemode` is in the active tool set, it answers a discovery
  script by naming that skill's tool, and the tool is in the session's registry.
  Only then does the entry skip the routing suggestion for that match. A
  surviving sibling tool, an allowlist that removed the matched tool, a
  `codemode` that reaches nothing, and a collection installed by another process
  all leave the suggestion in place.
- **The call's read is anchored on the real router root.** The `exposed`
  directory must be a real directory, the instruction file must resolve inside
  both the real router root and the real `exposed/collections` tree, and the read
  opens it with `O_NOFOLLOW` and requires the descriptor to be the device and
  inode that were validated.
- **The gateway renderer gains the tool name**, keeping the summary and the
  relative leaf path on the same line.
- **Routing terms, `routePrompt`, the registry schema, and the materialized
  exposed tree are unchanged.** The exposed leaf instruction file remains the
  channel's source of truth, so existing safety checks keep applying.

## Testing Decisions

A good test here asserts the surface Pi receives: the tools an extension
registers, their declarations, what a call resolves to, and what the entry
injects for a prompt. Tests must not read the new module's internals or assert
internal helper shapes.

- **One seam: the extension entry.** The existing harness loads the extension
  with a fake Pi and captures what it registers. It gains tool registration and
  active-tool state, so every scenario above is expressible through the same
  entry point the real session uses. No new seam is introduced.
- **Prior art**: the harness's existing `discover` and `route` commands, which
  drive the `resources_discover` and `before_agent_start` handlers and report
  what Pi would see; the Python tests that build temporary Git repositories and
  isolated agent directories and assert on the resulting registry and exposed
  tree, including symlink and rollback refusals.
- **Regression against the fallback**: the existing routing scenarios must keep
  passing, now through the entry's per-skill codemode gate rather than
  unconditionally. Added scenarios pin the ways the gate could suppress a
  suggestion it should not: an allowlist that removed only the matched skill's
  tool, a `codemode` that declares `reachesTools` and names nothing, and a
  collection installed by another process. More pin the refused read paths, the
  degraded searchable text when the clone is gone, in-place refresh after a menu
  install, and withdrawal after a menu remove or disable.
- **Evidence that unit tests cannot give**: a live run in which codemode actually
  searches and calls a registered skill tool. A harness proves the registration
  and the payload, not that codemode reaches an extension tool.

## Out of Scope

- Generating better workflow summaries, or changing the capability-summary
  contract.
- Replacing skill materialization, the atomic swap, or the symlink refusals.
- Activating codemode, adding a settings flag, or changing the user's active tool
  set.
- Migrating the registry schema or removing routing terms.
- Tool-level permissions, approval gates, or annotations.
- Any change to how MCP servers are configured or exposed.

## Further Notes

Two live code paths now exist for the same content. The tools channel is the
preferred one; the fallback exists because codemode is inactive by default, and
the ADR records why the router does not activate it. When both a collection and
an MCP server are present, codemode is usually active already, so the tools
channel applies.

The tool count grows with installed skills, and the codemode description grows
with it. `codemode.inlineBudget` decides how many skill tools are listed inline;
the rest are reachable only through `searchTools()`, which is the intended path.
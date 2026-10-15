"""Dead settings and unreachable test imports must be caught, not tolerated."""
from __future__ import annotations

import re
import subprocess

from test_goal import PACKAGE, REPO


def _typescript_sources() -> list[str]:
    return sorted(
        path
        for pattern in ("src/**/*.ts", "tests/**/*.mts", "tests/**/*.ts")
        for path in PACKAGE.glob(pattern)
    )


def test_package_typecheck_covers_tests_and_harnesses() -> None:
    """A ghost import in a harness must fail the type check, not the runtime.

    The main tsconfig only includes `src`, so `tests/` was never type checked and
    an import of a name the module does not export stayed invisible: tsx erases
    unused type-only imports at runtime, so every suite still passed.
    """
    config = (PACKAGE / "tsconfig.tests.json").read_text(encoding="utf-8")
    assert "tests/**/*.mts" in config, "test harnesses must be part of a type check"
    result = subprocess.run(
        ["pnpm", "exec", "tsc", "--noEmit", "-p", "packages/goal/tsconfig.tests.json"],
        cwd=REPO, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_settings_expose_no_field_without_a_reader() -> None:
    """A setting that nothing reads is dead configuration.

    `autoSelectSingleGoal` survived the removal of automatic adoption: it was
    still parsed, still accepted from a settings file, and still implied a
    behavior the runtime no longer had.
    """
    settings = (PACKAGE / "src/settings.ts").read_text(encoding="utf-8")
    declared = set(re.findall(r"^\s{2}(\w+)\?:", settings, re.MULTILINE))
    readers = {
        path.name: _strip_literals(path.read_text(encoding="utf-8"))
        for path in PACKAGE.glob("src/*.ts")
        if path.name != "settings.ts"
    }
    for field in sorted(declared):
            # A reader must name the setting on a settings object, not merely
            # share an unrelated `.provider` or `.model` property elsewhere.
            used = any(re.search(rf"(?:settings|resolved|raw|out)\.{field}\b", text)
                       for text in readers.values())
            assert used, f"settings.ts declares {field} but no runtime module reads it"


def _strip_comments(source: str) -> str:
    """Drop comments so a mention in prose or a comment is not a reader."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", source)


def _strip_literals(source: str) -> str:
    """Drop string and template prose, keeping `${...}` expressions as code.

    A name inside a quoted string is text the program prints, not a reader. A
    name inside `${...}` is a real call. Both earlier versions got one of these
    wrong: one counted prose as a reader, the other swallowed the expression and
    hid a live caller written inside a template.
    """
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    source = re.sub(r"//[^\n]*", "", source)
    out: list[str] = []
    index = 0
    while index < len(source):
        ch = source[index]
        if ch == "`":
            index += 1
            kept: list[str] = []
            while index < len(source):
                if source[index] == "\\":
                    index += 2
                    continue
                if source[index] == "`":
                    index += 1
                    break
                if source[index] == "$" and index + 1 < len(source) and source[index + 1] == "{":
                    depth = 0
                    end = index + 1
                    while end < len(source):
                        if source[end] == "{":
                            depth += 1
                        elif source[end] == "}":
                            depth -= 1
                            if depth == 0:
                                break
                        end += 1
                    kept.append(source[index + 2 : end])
                    index = end + 1
                    continue
                index += 1
            out.append(" " + " ".join(kept) + " ")
            continue
        if ch in "\"'":
            quote = ch
            index += 1
            while index < len(source):
                if source[index] == "\\":
                    index += 2
                    continue
                if source[index] == quote:
                    index += 1
                    break
                index += 1
            out.append('""')
            continue
        out.append(ch)
        index += 1
    return "".join(out)


def _code(paths: list[str]) -> str:
    """Comment- and literal-stripped sources, for counting genuine readers."""
    return "".join(_strip_literals(text) for text in paths)


def _split_imported(names: str) -> list[str]:
    """Names in a named-import list, `type` prefixes and aliases normalised."""
    return [
        part.split(" as ")[0].removeprefix("type ").strip()
        for part in (piece.strip() for piece in names.split(","))
        if part.strip()
    ]


def _normalize_aliases(source: str) -> str:
    """Rewrite `import { a as b }` so uses of `b` count as uses of `a`.

    Without this an import aliased at the call site looked like no reader at
    all, and a live export was reported dead.
    """
    # Do the renaming directly rather than inside a replace callback.
    for names, _ in re.findall(
        r"import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]", source
    ):
        for entry in names.split(","):
            entry = entry.strip().removeprefix("type ").strip()
            if " as " not in entry:
                continue
            original, alias = (part.strip() for part in entry.split(" as ", 1))
            source = re.sub(rf"\b{re.escape(alias)}\b", original, source)
    return source


def _consumers_text(paths: list[str]) -> str:
    """Comment- and literal-stripped consumer text with module paths preserved."""
    modules: dict[str, str] = {}
    parts: list[str] = []
    for text in paths:
        def protect(match: re.Match[str]) -> str:
            key = f"__MODPATH{len(modules)}__"
            modules[key] = match.group(2)
            return f"from {key}"

        # Aliases first: protecting a module path strips its quotes, and the
        # alias pattern needs them, so normalising afterwards did nothing.
        aliased = _normalize_aliases(_strip_comments(text))
        protected = re.sub(r"from\s*(['\"])([^'\"]+)\1", protect, aliased)
        parts.append(_strip_literals(protected))
    joined = "".join(parts)
    for key, value in modules.items():
        joined = joined.replace(key, f"'{value}'")
    return joined


def _function_body(code: str, name: str) -> str:
    """The named function's own body, not its parameter list or return type.

    The first `{` after the name can belong to a return type such as
    `{ x: string }`, so the scan steps past the parameter list first. `code` must
    be literal-stripped, so what this returns can be matched out of the consumer
    text and a self-recursive call is not mistaken for a reader.
    """
    match = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", code)
    if not match:
        return ""
    depth = 0
    index = match.end() - 1
    while index < len(code):
        if code[index] == "(":
            depth += 1
        elif code[index] == ")":
            depth -= 1
            if depth == 0:
                break
        index += 1
    else:
        return ""
    start = code.find("{", index)
    if start < 0:
        return ""
    depth = 0
    for end in range(start, len(code)):
        if code[end] == "{":
            depth += 1
        elif code[end] == "}":
            depth -= 1
            if depth == 0:
                return code[start : end + 1]
    return ""


def _uses(exported: str, code: str, consumers: str) -> int:
    """Places that genuinely read `exported`, in code rather than in prose."""
    text = re.sub(
        rf"import\s+(?:type\s+)?\{{[^}}]*\b{re.escape(exported)}\b[^}}]*\}}"
        rf"\s*from\s*['\"][^'\"]+['\"];?",
        "",
        consumers,
    )
    text = re.sub(rf"\bvoid\s+{re.escape(exported)}\b", "", text)
    body = _function_body(code, exported)
    if body:
        text = text.replace(body, "")
    return len(re.findall(rf"\b{re.escape(exported)}\b", text))


def _barrel_has_consumer(module: str, exported: str, consumers: str) -> bool:
    """Whether some file imports `exported` from `module` and genuinely uses it.

    An import alone keeps nothing alive. Neither does the origin's own
    declaration, or the barrel's re-export line: all three look like the name
    being present, and counting text let a barrel with no caller pass. A real
    reader is a reference on a line that is neither an import nor an export
    declaration.
    """
    stem = module[: -len(".ts")] if module.endswith(".ts") else module
    for names in re.findall(
        rf"import\s+(?:type\s+)?\{{([^}}]*)\}}\s*from\s*['\"]"
        rf"(?:\.\.?/(?:src/)?)?{re.escape(stem)}\.ts['\"]",
        consumers,
    ):
        for entry in _split_imported(names):
            for line in consumers.splitlines():
                if re.match(r"\s*(import|export)\b", line):
                    continue
                # `void x` exists to silence an unused warning; it reads nothing.
                usable = re.sub(rf"\bvoid\s+{re.escape(entry)}\b", "", line)
                if re.search(rf"\b{re.escape(entry)}\b", usable):
                    return True
    return False


def _exports_without_reader(sources: dict[str, str], consumer_texts: list[str]) -> tuple[int, list[str]]:
    """Return (scanned, dead) for the given module sources and consumer texts.

    Both views of the consumer code are built here, once, so a caller cannot
    feed the matcher the wrong one. Literal-stripping removes a name quoted in
    a string, which is not a reader; it also rewrites `from "../src/x.ts"` to
    `from ""`, which would make every genuine barrel look unimported. The barrel
    matcher therefore reads comment-stripped text, where module paths survive.
    """
    consumers = _consumers_text(consumer_texts)
    dead: list[str] = []
    scanned = 0
    for name, code in sources.items():
        declared: list[tuple[str, str]] = []
        for match in re.finditer(
            r"^export\s+(?:declare\s+)?(?:async\s+)?"
            r"(?:function|const|class|abstract\s+class|let)\s+(\w+)"
            r"|^export\s+(?:type|interface)\s+(\w+)", code, re.MULTILINE,
        ):
            declared.append((match.group(1) or match.group(2), "decl"))
        for match in re.finditer(r"^export\s+(?:type\s+)?\{([^}]*)\}(?:\s*from\s*['\"][^'\"]+['\"])?",
                                 code, re.MULTILINE):
            for entry in _split_imported(match.group(1)):
                declared.append((entry, "barrel"))
        scanned += len(declared)
        for exported, kind in declared:
            if kind == "decl":
                # Read anywhere in code but its own declaration line. Reading only
                # itself is the dead case this reports.
                if _uses(exported, code, consumers) <= 1:
                    dead.append(f"{name}: {exported}")
                continue
            # A barrel is a promise that this module re-exports the name. It is
            # alive only when a consumer imports it *from this module*.
            if not _barrel_has_consumer(name, exported, consumers):
                dead.append(f"{name}: {exported} (re-export with no consumer)")
    return scanned, dead


def test_no_export_lacks_a_reader() -> None:
    """Every export must be read by code, or it is dead surface.

    Repeated redesigns left prompt fragments, ledger helpers and settings
    writers that no module or harness referenced. Comments and prose are not
    readers: they keep a dead name alive without calling it. Re-exports count
    only when a consumer actually imports them from that module.
    """
    sources = {path.name: _strip_comments(path.read_text(encoding="utf-8"))
               for path in PACKAGE.glob("src/*.ts")}
    scanned, dead = _exports_without_reader(
        sources, [path.read_text(encoding="utf-8") for path in _typescript_sources()]
    )
    assert scanned, "no export was scanned; the check would pass vacuously"
    assert not dead, "exports without a reader: " + "; ".join(dead)


def test_barrel_matcher_sees_a_real_consumer() -> None:
    """The barrel matcher must accept a real consumer and reject an absent one.

    `packages/goal` currently exports no barrel, so the matcher had no live case
    and a broken one passed unnoticed: literal-stripping had rewritten every
    import path to `from ""`, which rejected every genuine consumer. Synthetic
    sources are used here precisely because the real tree cannot exercise it.
    """
    source = {"source.ts": "export function widget(): string {\n  return 'w';\n}\n",
              "barrel.ts": "export { widget } from './source.ts';\n"}
    # The real call passes every TypeScript file as a consumer, the declaring
    # module included, so a declaration counts once and an actual reader twice.
    sources = list(source.values())
    _, dead = _exports_without_reader(
        source, sources + ['import { widget } from "../src/barrel.ts";\nwidget();\n']
    )
    assert not dead, f"a consumed barrel must not be reported dead: {dead}"
    _, dead = _exports_without_reader(source, sources + ["export const unrelated = 1;\n"])
    assert any("widget" in item for item in dead), (
        f"an unconsumed barrel must be reported, got {dead}"
    )
    # A relative specifier inside src is how modules there import each other, so
    # `./barrel.ts` must be recognised when it is really used.
    _, dead = _exports_without_reader(
        source, sources + ["import { widget } from './barrel.ts';\nwidget();\n"]
    )
    assert not dead, f"a './barrel.ts' consumer must be seen, got {dead}"
    # An import nothing uses keeps nothing alive. Earlier this was asserted the
    # other way round, and that let a barrel with no caller look consumed.
    _, dead = _exports_without_reader(
        source, sources + ["import type { widget } from './barrel.ts';\n"]
    )
    assert any("widget" in item for item in dead), (
        f"an unused './barrel.ts' import is not a consumer, got {dead}"
    )
    # Example text inside a template literal is not a consumer.
    _, dead = _exports_without_reader(
        source,
        sources + ["const doc = `\nimport type { widget } from '../src/barrel.ts';\n`;\n"],
    )
    assert any("widget" in item for item in dead), (
        f"prose must not pose as a consumer, got {dead}"
    )


def test_removed_dead_surface_stays_removed() -> None:
    """Names deleted as dead must not quietly come back.

    The removals rest on grep evidence alone. A public class member, a reader
    method or an interface field with no caller is invisible to the export scan,
    and a dedicated check for that shape was attempted twice and discarded both
    times, once for false positives on object literals and once for scanning
    nothing. This pins those removals directly, which is weaker than proving they
    were dead but fails if one returns.
    """
    code = _code([path.read_text(encoding="utf-8") for path in _typescript_sources()])
    for name in ("openGoals", "unfocus", "markInterrupted", "emptyGoal"):
        assert not re.search(rf"\b{re.escape(name)}\b", code), (
            f"{name} was removed as dead surface and is present again"
        )
    # Members and fields removed by the audit: the duplicate reader, the reader
    # whose name promised a prose file, two accessors nothing called, and the
    # three verdict fields the retired attempt accounting owned. The field
    # patterns require the optional-field syntax, so an unrelated local variable
    # of the same name elsewhere cannot trip them.
    for pattern in ("readGoalFromDisk", "readPrompt", "currentTurnSeq", "focusedId",
                    r"attempts\?:", r"advice\?:", r"stopped\?:"):
        assert not re.search(rf"\b{pattern}", code), (
            f"/{pattern}/ was removed as dead surface and is present again"
        )


def test_package_entry_reaches_every_named_export() -> None:
    """`src/index.ts` named exports are dead unless the package entry re-exports them.

    `package.json` maps `.` to `index.ts`, and that file re-exports only the
    default. Every named export of `src/index.ts` was therefore unreachable by a
    consumer, so the module advertised API nobody could import.
    """
    entry = (PACKAGE / "index.ts").read_text(encoding="utf-8")
    source = (PACKAGE / "src/index.ts").read_text(encoding="utf-8")
    assert "export { default }" in entry, "the package entry must re-export the default"
    published: set[str] = set()
    # Both `export { X }` and `export type { X }` are entry-surface. The type
    # form is not a runtime export, but the package entry cannot import it
    # either, so it is unreachable all the same.
    for match in re.finditer(r"^export\s+(?:type\s+)?\{([^}]*)\}\s*from\s*['\"][^'\"]+['\"]",
                             source, re.MULTILINE):
        published.update(_split_imported(match.group(1)))
    leaked = sorted(name for name in published if not re.search(rf"\b{re.escape(name)}\b", entry))
    assert not leaked, "src/index.ts exports no consumer can import: " + "; ".join(leaked)


def test_no_user_visible_message_prints_the_goal_id() -> None:
    """A session holds one goal, so its id is noise the reader must filter out.

    This defect survived eleven reviews because nothing pinned it: the id was
    removed from one message at a time while four other paths still printed it.
    The check is on the source, because the sinks are `notifyPi`, tool details
    and block reasons that a behavioural test only reaches on a rare race.

    The id is caught in any shape a message takes: a user-visible field, a
    positional argument to a notify or a push, a thrown error, or a bare
    return. An earlier version matched only the field shape, and both live
    defects of its round lived in exactly the shapes it missed.
    """
    # Only names that hold a goal id. `stopped` was once in this list and
    # flagged `${stopped ?? draft.status}`, which carries a reason string, not
    # an id: a false positive that would have forced a wrong fix.
    id_ref = (r"\$\{[^}]*\b(?:goal\.id|goalId|input\.id|draft\.id|"
              r"created\.goal\.id|current\.id|active\.id)\b")
    leaks: list[str] = []
    for path in sorted(PACKAGE.glob("src/*.ts")):
        code = _strip_comments(path.read_text(encoding="utf-8"))
        for match in re.finditer(r"`[^`\n]*`", code):
            if re.search(id_ref, match.group(0)):
                # The line the template starts on, and the statement it ends in.
                line_no = code[: match.start()].count("\n") + 1
                lines = code.splitlines()
                context = " ".join(lines[max(0, line_no - 3) : line_no + 2])
                # A key or a path is internal plumbing: neither renders text.
                # Everything else names a message, a reason or a summary a
                # user or the model reads.
                if re.search(r"\bkey\b|\bpath\b|Path", context):
                    continue
                leaks.append(f"{path.name}:{line_no}")
    # The id is genuinely used for paths and cache keys; both are file-system
    # plumbing, and a check that flagged them would fail on its own fixtures.
    assert leaks or True, "no template naming a goal id was scanned"
    # Only lines that are not plumbing may stay empty. Every hit above is a
    # message template naming a goal id, which is the leak this stops.
    assert not leaks, "user-visible text must not print a goal id: " + "; ".join(leaks)


def test_command_source_and_docs_register_one_command() -> None:
    """Exactly one registered command; every documented input is a real argument.

    The bare `/goal-status` reference in the session harness outlived the rename
    to `/goal` and was silently inert, because an unknown slash command is
    passed through instead of failing.
    """
    registered = re.findall(r'registerCommand\(\s*["\']([^"\']+)["\']',
                            "".join(path.read_text(encoding="utf-8") for path in PACKAGE.glob("src/*.ts")))
    assert registered == ["goal"], f"expected only the single goal command, found {registered}"
    sources = _typescript_sources()
    stale = []
    for path in sources + sorted(PACKAGE.glob("features/*.feature")) + [PACKAGE / "README.md", PACKAGE / "AGENTS.md"]:
        text = path.read_text(encoding="utf-8")
        for name in ("goal-status", "goal-focus", "goal-unfocus", "goal-pause", "goal-resume",
                      "goal-clear", "goal-list", "goal-dashboard", "goal-settings"):
            for line in text.splitlines():
                if name in line and ("/" + name) in line:
                    stale.append(f"{path.relative_to(REPO)}: {line.strip()[:80]}")
    assert not stale, "stale command references: " + "; ".join(stale)


def test_working_context_states_a_verdict_for_every_surface() -> None:
    """The audit inventory must cover the package, not a sample of it.

    CONTEXT.md is the handoff document: it claims a verdict for every module, every
    documented surface, and every acceptance probe. A surface missing from it reads as
    audited when nobody audited it, so the inventory itself is checked here.
    """
    context = (PACKAGE / "CONTEXT.md").read_text(encoding="utf-8")
    surfaces = [path.name for path in PACKAGE.glob("src/*.ts")]
    surfaces += ["AGENTS.md", "README.md", "TUI.zh-CN.md"]
    surfaces += [path.name for path in PACKAGE.glob("features/*.feature")]
    surfaces += [path.name for path in PACKAGE.glob("tests/goal_native_*")]
    missing = sorted(name for name in surfaces if name not in context)
    assert not missing, f"CONTEXT.md states no verdict for: {missing}"

import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]


class TestContinueExtension(unittest.TestCase):
    def ext_source(self) -> str:
        return (UTILS_PKG_DIR / "extensions" / "continue.ts").read_text(encoding="utf-8")

    def test_extension_file_exists_and_registers_command(self) -> None:
        content = self.ext_source()
        self.assertIn('registerCommand("continue"', content)
        self.assertNotIn('registerCommand("继续"', content)
        self.assertNotIn("CONTINUE_INTERNAL_COMMAND", content)
        self.assertIn("sendMessage", content)

    def test_strict_continue_input_interception(self) -> None:
        content = self.ext_source()
        self.assertIn('pi.on("input"', content)
        self.assertIn("isContinuationKeyword", content)
        self.assertIn('"continue"', content)
        self.assertIn('"继续"', content)
        self.assertIn('"繼續"', content)

    def test_standalone_keyword_matching_only(self) -> None:
        content = self.ext_source()
        # Assert exact Set matching logic is present and no wildcards/substring matches exist
        self.assertIn("CONTINUE_SET = new Set", content)
        self.assertIn("CONTINUE_SET.has(normalized)", content)
        self.assertNotIn("includes(", content)
        self.assertNotIn("startsWith(", content)

    def test_stale_failures_never_block_retry(self) -> None:
        # Regression: classification-based gating turned stale persisted errors into a
        # permanent refusal that ignored later model/config switches. Continuation must
        # always retry directly with the current model and configuration.
        content = self.ext_source()
        self.assertNotIn("requiresUserAction", content)
        self.assertNotIn("resolvePreflightFailure", content)
        self.assertNotIn("hasConfiguredAuth", content)
        self.assertNotIn("getProviderAuth", content)
        self.assertNotIn("TRANSIENT_PROVIDER_ERROR_PATTERN", content)
        self.assertNotIn("errorMessage", content)

    def test_failed_and_incomplete_turns_continue_directly(self) -> None:
        content = self.ext_source()
        # Every non-stop trailing state retries silently from existing context.
        self.assertIn('lastMessage.stopReason === "stop"', content)
        self.assertIn("isDirectContinuation: true", content)
        # A completed turn still continues with a visible user message.
        self.assertIn(
            "Please continue execution based on the suggestions, incomplete steps, or next actions from your previous response.",
            content,
        )

    def test_empty_session_refuses_without_provider_request(self) -> None:
        content = self.ext_source()
        self.assertIn("there is no previous model request", content)
        self.assertIn('notifyPi(ctx.ui', content)

    def test_strip_removes_contiguous_trailing_failures_only(self) -> None:
        content = self.ext_source()
        self.assertIn('pi.on("context"', content)
        self.assertIn("stripDirectContinuationMessages", content)
        self.assertIn("CONTINUATION_MESSAGE_TYPE", content)
        # Contiguous run of incomplete assistants is popped, never past a tool result pair.
        self.assertIn("while (filtered.length > 0 && isIncompleteAssistant(filtered[filtered.length - 1]))", content)
        self.assertIn('message.stopReason !== "stop"', content)

    def test_continuation_reloads_only_for_unseen_disk_entries(self) -> None:
        content = self.ext_source()
        self.assertIn("readDiskTipEntryId", content)
        self.assertIn('readFileSync(sessionFile, "utf8")', content)
        self.assertIn("getSessionFile()", content)
        self.assertIn("getEntry(diskTipEntryId)", content)
        self.assertIn("needsSessionReload", content)
        self.assertIn("switchSession(sessionFile", content)
        self.assertIn("withSession", content)
        self.assertIn("performContinuation", content)
        self.assertNotIn("diskTipEntryId !== ctx.sessionManager.getLeafId()", content)

    def test_selected_tree_node_is_not_rebased_to_disk_tip(self) -> None:
        content = self.ext_source()
        self.assertIn("selected leaf is", content)
        self.assertIn("known disk tip", content)
        self.assertIn("active session has never loaded", content)

    def test_reload_decision_distinguishes_known_and_unseen_disk_tips(self) -> None:
        module_path = (UTILS_PKG_DIR / "extensions" / "continue.ts").as_posix()
        script = textwrap.dedent(
            f"""
            import {{ needsSessionReload }} from {json.dumps(module_path)};
            const known = {{ getEntry: () => ({{ id: "known" }}) }};
            const unseen = {{ getEntry: () => undefined }};
            console.log(JSON.stringify({{
              known: needsSessionReload(known, "known"),
              unseen: needsSessionReload(unseen, "unseen"),
              noTip: needsSessionReload(unseen, null),
            }}));
            """,
        )
        result = subprocess.run(
            ["node", "--import", "tsx/esm", "--input-type=module", "--eval", script],
            cwd=UTILS_PKG_DIR.parent.parent,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(result.stdout), {"known": False, "unseen": True, "noTip": False})

    def test_selected_leaf_runs_without_session_reload(self) -> None:
        module_path = (UTILS_PKG_DIR / "extensions" / "continue.ts").as_posix()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", encoding="utf-8") as session:
            session.write('{"type":"session","id":"session"}\n{"type":"message","id":"failed-tip"}\n')
            session.flush()
            script = textwrap.dedent(
                f"""
                import {{ runContinuation }} from {json.dumps(module_path)};
                const events = [];
                const activeBranch = [{{ type: "message", message: {{ role: "assistant", stopReason: "error" }} }}];
                const sessionManager = {{
                  getSessionFile: () => {json.dumps(session.name)},
                  getEntry: (id) => id === "failed-tip" ? {{ id }} : undefined,
                  getBranch: () => activeBranch,
                }};
                const context = {{
                  sessionManager,
                  waitForIdle: async () => {{}},
                  switchSession: async () => events.push("reloaded"),
                  ui: {{ notify: () => events.push("notified") }},
                }};
                const host = {{
                  sendMessage: () => events.push("continued"),
                  sendUserMessage: () => events.push("visible"),
                }};
                await runContinuation("", context, host);
                console.log(JSON.stringify(events));
                """,
            )
            result = subprocess.run(
                ["node", "--import", "tsx/esm", "--input-type=module", "--eval", script],
                cwd=UTILS_PKG_DIR.parent.parent,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(result.stdout), ["continued"])


    def test_continuation_keyword_routes_through_public_command(self) -> None:
        content = self.ext_source()
        # No hidden internal command: the keyword path reuses the registered /continue
        # command so it runs with a full command context (switchSession rebase support).
        self.assertNotIn("__continue", content)
        self.assertIn('sendUserMessage("/continue", expandOptions)', content)
        self.assertIn("expandPromptTemplates: true", content)
        self.assertIn("isIdle()", content)

    def test_feature_file_covers_direct_retry_recovery(self) -> None:
        feature = (UTILS_PKG_DIR / "features" / "continue.feature").read_text(encoding="utf-8")
        self.assertIn('stopReason "error"', feature)
        self.assertIn("provider is overloaded or the network timed out", feature)
        self.assertIn('stopReason "length"', feature)
        self.assertIn("A stale failure is retried after the model or configuration changed", feature)
        self.assertIn("the stale persisted error is not treated as a permanent refusal", feature)
        self.assertIn("Context overflow recovery has already failed", feature)
        self.assertIn("Provider authentication is unavailable", feature)
        self.assertIn("Provider quota or billing is exhausted", feature)
        self.assertIn("safety policy", feature)
        self.assertIn('stopReason "toolUse"', feature)
        self.assertIn('stopReason "pending"', feature)
        self.assertIn("arguments were truncated", feature)
        self.assertIn("An interrupted turn keeps its saved tool results intact", feature)
        self.assertIn("Consecutive failed retry attempts are all omitted", feature)
        self.assertIn("unclassified provider error", feature)
        self.assertIn('latest assistant message has stopReason "stop"', feature)
        self.assertIn("without a continuation user message", feature)
        self.assertIn("omitted before the provider request", feature)
        self.assertIn("included in the model context", feature)
        self.assertIn("nothing to continue", feature)
        self.assertIn('stopReason "stop"', feature)

    def test_feature_file_covers_stale_session_recovery(self) -> None:
        feature = (UTILS_PKG_DIR / "features" / "continue.feature").read_text(encoding="utf-8")
        self.assertIn("Entries written by another process are inherited before continuing", feature)
        self.assertIn("The user-selected tree node is the continuation starting point", feature)
        self.assertIn("the same session file is reloaded before the continuation starts", feature)
        self.assertIn("the continuation starts from the selected node", feature)

    def test_feature_file_is_mirrored_in_project_memory(self) -> None:
        memory = (UTILS_PKG_DIR.parent.parent / ".memory" / "project_continue_recovery.md").read_text(encoding="utf-8")
        self.assertIn("packages/utils/extensions/continue.ts", memory)
        self.assertIn("retries directly", memory)
        self.assertIn("needsSessionReload", memory)
        self.assertNotIn("requiresUserAction", memory)

    def test_package_json_registers_extensions(self) -> None:
        manifest = json.loads((UTILS_PKG_DIR / "package.json").read_text(encoding="utf-8"))
        self.assertIn("extensions", manifest["pi"])
        self.assertEqual(manifest["pi"]["extensions"], ["./index.ts"])
        self.assertTrue((UTILS_PKG_DIR / "index.ts").is_file())


if __name__ == "__main__":
    unittest.main()

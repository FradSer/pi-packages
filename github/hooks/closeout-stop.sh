#!/usr/bin/env bash
#
# Stop hook — enforce the /skill:review-pr closeout: the merge decision must be
# resolved before the turn ends.
#
# Background: the review-pr skill runs on prompt alone, so the Phase 5 merge ask
# ("ask the user whether to merge before any closeout ceremony") can be skipped
# by a hallucinated or premature stop. The skill arms a state file
# (.git/review-pr-closeout.json) the moment Phase 4's stop conditions hold and
# clears it once the user's merge choice is in (or the --auto-merge closeout ran
# or aborted). While the file exists, this hook blocks one turn-end per user
# turn with a message naming the PR and the missing step — the ask cannot
# silently vanish, and it does not loop: after the single block the turn ends.
#
# Guard rails (this hook fires on EVERY turn end — Stop has no matcher):
#   - Fails open: no jq, no git repo, no state file, or a subagent stop
#     (agent_id present in the input — a subagent cannot ask the user) all pass.
#   - Fires at most once per user turn: stop_hook_active is true when the turn
#     is already continuing from a stop-hook block — pass through so the turn
#     can end. The single block injects the reminder once; resolving the closeout
#     (the merge ask or clear-closeout) is what removes the state file.
#   - Blocks via hookSpecificOutput.additionalContext (exit 0 + JSON): the
#     message is fed back to the model as "Stop hook feedback" and the turn
#     continues — same loop protections as a decision:block, without the
#     hook-error label.
#
# Input (stdin JSON): Stop common fields + stop_hook_active,
#   last_assistant_message, background_tasks, session_crons.
# Reference: https://code.claude.com/docs/en/hooks (Stop)

set -uo pipefail

input=$(</dev/stdin)

# Fail open: without jq there is nothing to parse.
command -v jq >/dev/null 2>&1 || exit 0
[ -n "$input" ] || exit 0

# Subagent stops cannot ask the merge question — enforcement is the main turn's job.
agent_id=$(printf '%s' "$input" | jq -r '.agent_id // empty')
[ -z "$agent_id" ] || exit 0

# At most one reminder per user turn. stop_hook_active is true when the turn is
# already continuing from a stop-hook block — passing through lets the turn end
# instead of re-blocking every end attempt. The reminder was already injected
# once; resolving the closeout (the merge ask, or clear-closeout) is what clears
# the state file on its own schedule. Official anti-loop pattern per
# https://code.claude.com/docs/en/hooks-guide.md.
stop_hook_active=$(printf '%s' "$input" | jq -r '.stop_hook_active // false')
[ "$stop_hook_active" = "true" ] && exit 0

# The state file lives in the repo's gitdir; resolve it from the hook cwd
# (the session's working directory). Outside a git repo there is no closeout.
GITDIR=$(git rev-parse --git-dir 2>/dev/null) || exit 0
case "$GITDIR" in
  /*) ;;
  *)  GITDIR="$PWD/$GITDIR" ;;
esac

STATE="$GITDIR/review-pr-closeout.json"
[ -f "$STATE" ] || exit 0

# Read-side validation: only a well-formed, digits-PR state may block. Anything
# else (malformed file, foreign content) fails open — the file was not written
# by the skill's arm script, so it is not a closeout this hook should enforce.
PR=$(jq -r '.pr // empty' "$STATE")
MODE=$(jq -r '.mode // "ask"' "$STATE")
[[ "$PR" =~ ^[0-9]+$ ]] || exit 0
[ "$MODE" = "ask" ] || [ "$MODE" = "auto" ] || MODE="ask"

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLEAR_SCRIPT="$PLUGIN_ROOT/skills/review-pr/scripts/clear-closeout.sh"

if [ "$MODE" = "auto" ]; then
  msg="review-pr closeout for PR #${PR} is pending in --auto-merge mode: verify the pre-merge gate still holds (CI green, no open escalate comments), then run the closeout — post the summary comment, rewrite the title/body, then gh pr merge --merge. First verify the pending closeout is real: the state file is stale (a false alarm) if the closeout was already resolved — ask already answered, summary already posted, or the PR already merged. Judge simple checks directly (e.g. gh pr view --json state,mergedAt, the <!-- review-pr:summary --> marker lookup); for complex or ambiguous situations run an independent clean verification pass. If the state is stale, the merge already failed, the user interrupted, or the gate does not hold (new comments, CI re-ran red), do NOT merge: run bash ${CLEAR_SCRIPT} ${PR} and fall back to an explicit merge question in conversation, or stop if the user declined."
else
  msg="review-pr closeout for PR #${PR} is pending: ask the user whether to merge in conversation before ending this turn — the closeout ceremony (summary comment + body rewrite) runs only on a merge choice, and \"Don't merge\" skips it. First verify the pending closeout is real: the state file is stale (a false alarm) if the closeout was already resolved — ask already answered, summary already posted, or the PR already merged. Judge simple checks directly (e.g. gh pr view --json state,mergedAt, the <!-- review-pr:summary --> marker lookup); for complex or ambiguous situations run an independent clean verification pass. If the state is stale, or the user already answered or explicitly declined, run bash ${CLEAR_SCRIPT} ${PR} to release the closeout."
fi
msg="${msg} Full verification procedure: ${PLUGIN_ROOT}/skills/review-pr/references/closeout.md (When the hook fires)."

jq -n --arg c "$msg" '{hookSpecificOutput:{hookEventName:"Stop",additionalContext:$c}}'
exit 0

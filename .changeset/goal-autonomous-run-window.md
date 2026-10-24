---
"@fradser/pi-goal": patch
---

Automatic continuation now bounds itself by whether a run added anything, instead of by whether it
changed the workspace. The two stops that punished real work are gone, replaced by one rule:

- A settled run no longer ends the goal for lacking a tool receipt. A continuation run that reports
  where it got to, and a provider that returns an empty completion, used to stop the goal with
  `No effective work was recorded. Use /goal resume to continue.` in the very turn that explained the
  work — which for a long-running goal (large accumulated context) is a common shape, not a rare one.
- The window no longer counts only an unseen successful `edit` or `write`. It counted a run that ran
  the whole gate suite and read its output as "nothing observable", so three verification runs in a row
  stopped a goal that was working; the window is now filled by runs that produced **nothing new**, and
  reset by a receipt this session had not already produced, whatever the tool.

The message follows the rule: `3 consecutive runs produced nothing new. Use /goal resume to continue.`
A failed or interrupted run is still the only immediate stop, so a provider outage cannot become a retry
storm. Repeated receipts, an answer with no tool call, and a run that produced nothing at all are what
fill the window, so a stagnant loop still stops by itself. Goal introspection (`create_goal`, `get_goal`,
`update_goal`, `monitor_stop`) and a monitor that has not reached a terminal status are not work, and a
requirement revision no longer clears the receipt memory (re-wording the objective must not reset the
loop's only bound). `GoalScheduler.settled` takes `(goal, settings, successful, didWork)`,
`GoalCore.performedWork` is again the one progress fact, and `GoalCore.changedWork`/`runChangedState`
are deleted with the tool allowlist they read. `NO_CHANGE_RUN_LIMIT` is renamed
`NO_NEW_WORK_RUN_LIMIT`, and the run-start policy block now tells the model the rule the runtime
actually uses. A user's own turn is still always new work, so a `/goal <text>` request keeps the full
window for the work that follows. `maxAutonomousRuns` remains the only optional ceiling; raising it is
now the way to bound a goal that keeps doing new things.
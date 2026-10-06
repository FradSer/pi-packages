/**
 * The Pi extension body for `@fradser/pi-subagents`.
 *
 * Lives in `src/` so `index.ts` can re-export it as the package's default export,
 * which is what lets one file serve as both the library entry and the extension
 * entry. A separate top-level extension file would split that, and the root
 * `index.ts` is what every other runtime package here loads.
 *
 * It registers the intent tool family and owns the delivery of a settled child's
 * Session Result back into this session. A team runtime can publish a richer
 * spawn path through `setAgentHost`; without one, the intent tools fall back to
 * the raw spawner, which is what makes this package usable alone.
 *
 * Deliberately keeps the tool library TUI-free, and injects only the row
 * binding from `./rows.ts`. `child-execution.ts` is imported by the headless suites
 * and by other packages, so the geometry it needs has to arrive as a parameter;
 * the entry is the one layer that is only ever loaded by Pi, so it is the one
 * layer allowed to import pi-tui. A row without real geometry is worse than no
 * row at all — it renders in an offline fixture and takes the terminal down on
 * the first repaint — which is why this file supplies it instead of leaving the
 * intent result to Pi's default receipt rendering.
 *
 * The entry is also where a Session Result is sent. A tool's execution context
 * has no `sendMessage`, so the session API reaches the library only from here,
 * and a consumer embedding the library without this entry gets spawning without
 * delivery. See ADR-0007.
 */

import { retireAgentControls } from "./child-execution.ts";
import { registerSubagentToolActivation } from "./tool-activation.ts";
import { registerIntentTools } from "./intent-tools.ts";
import { endInputSequence } from "./input-sequences.ts";
import { createAgentActivityWidget, createAgentResultRenderer, createParentMessageRenderer, createSessionMessageRenderer } from "./rows.ts";
import { terminateAllAgents } from "./spawner.ts";
import { getAgent, listAgents, livingAgents, observeAgentRoster, updateAgent } from "./roster.ts";
import { exactSessionRoute } from "./session-route.ts";
import { clearSessionAgents } from "./agents.ts";
import type { LifecycleRendererBindings, PiLiveWidgetContext } from "@fradser/pi-kit";
import {
  SESSION_ENDED_MESSAGE_TYPE,
  INPUT_CANCELLED_MESSAGE_TYPE,
  SESSION_RESULT_MESSAGE_TYPE,
  SESSION_UNANSWERED_MESSAGE_TYPE,
  formatSessionNotice,
  readSessionNotice,
  sessionNoticeMessageType,
  sessionNoticeSpec,
  unreadableSessionNoticeSpec,
  type SessionNoticeSender,
} from "./session-result.ts";
import { formatParentMessageNotice, type ParentMessageNotice } from "./parent-message.ts";
import { publishParticipantRegistryFromRoster } from "./participant-registry.ts";

export const PARENT_MESSAGE_MESSAGE_TYPE = "subagents-parent-message";

export default function piSubagents(pi: Parameters<typeof registerIntentTools>[0]): void {
  // Read per render: only a live session has a `ui` and a `cwd` for the host
  // wrapper, and a row rendered without them is a row the host cannot expand.
  let host: Pick<LifecycleRendererBindings, "ui" | "cwd"> = {};
  let shuttingDown = false;
  const activityWidget = createAgentActivityWidget();
  let activityContext: PiLiveWidgetContext | undefined;
  let stopObserving: (() => void) | undefined;
  const latestLine = (text?: string): string | undefined => text?.split("\n").reverse().find(line => line.trim())?.trim();
  const refreshActivity = (): void => {
    activityWidget.update(activityContext, livingAgents()
      // Only work in flight occupies the activity area. A settled child leaves it:
      // an idle resident is still addressable through the roster and can take
      // its next input, so keeping a static row would spend the reader's
      // attention on a child that is doing nothing. Its previous stream output
      // belongs to the result row above, and it goes stale while the child waits.
      .filter(child => child.standalone
        && (child.status === "starting" || child.status === "working"))
      .map(child => {
        const stopping = child.leaderRequestedEnd === true;
        return {
          id: child.spawnId,
          identity: child.label ?? child.identity ?? child.name,
          ...(stopping ? { status: "working" as const, activity: "Stopping..." } : {
            status: "working" as const,
            activity: child.activeTool || latestLine(child.liveThinking) || latestLine(child.liveText)
              || (child.status === "starting" ? "Starting..." : "Working..."),
          }),
        };
      }));
  };
  const noticeRenderer = () => createSessionMessageRenderer((details) => {
    const notice = readSessionNotice(details);
    return notice ? sessionNoticeSpec(notice) : unreadableSessionNoticeSpec();
  }, () => host);
  // Rendering a notice and delivering one are separate capabilities. A host that
  // cannot render still receives the result and paints it with its own default,
  // so the missing renderer must not take delivery down with it.
  if (typeof pi.registerMessageRenderer === "function") {
    pi.registerMessageRenderer(SESSION_RESULT_MESSAGE_TYPE, (message, state, theme) =>
      noticeRenderer()(message as never, state, theme));
    pi.registerMessageRenderer(SESSION_UNANSWERED_MESSAGE_TYPE, (message, state, theme) =>
      noticeRenderer()(message as never, state, theme));
    pi.registerMessageRenderer(SESSION_ENDED_MESSAGE_TYPE, (message, state, theme) =>
      noticeRenderer()(message as never, state, theme));
    pi.registerMessageRenderer(INPUT_CANCELLED_MESSAGE_TYPE, (message, state, theme) =>
      noticeRenderer()(message as never, state, theme));
    const parentRenderer = createParentMessageRenderer(() => host);
    pi.registerMessageRenderer(PARENT_MESSAGE_MESSAGE_TYPE, (message, state, theme) =>
      parentRenderer(message as never, state, theme));
  }

  // Likewise a host with no session API still gets working intent tools: it
  // spawns, records, and answers status questions, and delivers nothing. That is the library's
  // documented behaviour, not a degraded mode worth failing over.
  //
  // This is the only place a delivery can fail, so nothing is swallowed here: a
  // synchronous throw propagates to the caller, which records it on the roster,
  // and the promise `sendMessage` actually returns is consumed so an async
  // failure is never an unhandled rejection.
  const sender: SessionNoticeSender = typeof pi.sendMessage !== "function" ? () => {} : (notice) => {
    pi.sendMessage(
      {
        customType: sessionNoticeMessageType(notice),
        content: formatSessionNotice(notice),
        display: true,
        details: notice,
      },
      // A result is work the Leader asked for and is waiting on, so it enters
      // the next turn as a follow-up rather than interrupting a turn in flight.
      //
      // An ended Work Session is a terminal fact a person must be able to see,
      // never one the Leader has to decide about, and `triggerTurn: false` is
      // spelled out rather than left absent: absent means "not false", which pi
      // reads as permission to steer the turn in flight (ADR-0002). `nextTurn`
      // queues it without interrupting, so the line is visible in the next
      // turn's context and costs no turn of its own.
      notice.kind !== "ended" && !shuttingDown
        ? { deliverAs: "followUp", triggerTurn: true }
        : { deliverAs: "nextTurn", triggerTurn: false },
    );
  };

  const parentMessageSender = typeof pi.sendMessage !== "function" ? undefined
    : (notice: ParentMessageNotice): Promise<void> => {
      const result = pi.sendMessage(
        {
          customType: PARENT_MESSAGE_MESSAGE_TYPE,
          content: formatParentMessageNotice(notice),
          display: true,
          details: notice,
        },
        shuttingDown
          ? { deliverAs: "nextTurn", triggerTurn: false }
          : { deliverAs: "followUp", triggerTurn: true },
      );
      return Promise.resolve(result).then(() => undefined);
    };

  registerIntentTools(pi, { renderResult: createAgentResultRenderer, deliverSessionResult: sender, deliverParentMessage: parentMessageSender });
  registerSubagentToolActivation(pi, { renderResult: createAgentResultRenderer });
  pi.on("model_select", async (_event, ctx) => { if (ctx) host = ctx; });
  pi.on("thinking_level_select", async (_event, ctx) => { if (ctx) host = ctx; });
  pi.on("session_start", async (_event, ctx) => {
    if (ctx) host = ctx;
    activityWidget.clear(activityContext);
    activityContext = ctx;
    stopObserving?.();
    stopObserving = observeAgentRoster(() => {
      // Every roster change republishes: the installed task store reads this
      // roster as its participant registry, and a child that started, settled or
      // closed is only visible there after this runs.
      publishParticipantRegistryFromRoster();
      refreshActivity();
    });
    refreshActivity();
    // Shutdown retires actual incarnations; startup never forgets uncertain
    // closure authority merely to make the roster look empty.
    pi.events.emit("pi-subagents:ready", {});
  });

  // Pi disposes the extension runtime on exit, reload and session replacement.
  // Temporary roles/context end with that parent; durable data is left intact.
  pi.on("session_shutdown", async () => {
    shuttingDown = true;
    stopObserving?.();
    stopObserving = undefined;
    activityWidget.clear(activityContext);
    activityContext = undefined;
    // Copy exact incarnation facts before awaiting close. A late replacement
    // must not inherit shutdown intent or lose its new runtime controls.
    const children = listAgents().map(({ name, spawnId, status }) => ({
      name, spawnId, status, session: exactSessionRoute(name, spawnId),
    }));
    for (const child of children) {
      endInputSequence(child.session, "The parent session is shutting down; queued input did not start.");
      if (child.status !== "stopped" && getAgent(child.name)?.spawnId === child.spawnId) {
        updateAgent(child.name, { leaderRequestedEnd: true });
      }
    }
    const closed = await terminateAllAgents();
    for (const child of children) {
      const confirmed = child.status === "stopped"
        || closed.some(outcome => outcome.name === child.name && outcome.confirmedClosed);
      if (!confirmed) continue;
      if (getAgent(child.name)?.spawnId === child.spawnId) updateAgent(child.name, { status: "stopped" });
      retireAgentControls(child.session);
    }
    clearSessionAgents();
    const unconfirmed = closed.filter((entry) => !entry.confirmedClosed);
    if (unconfirmed.length > 0) {
      // Console telemetry, not a notification: the session is already tearing
      // down and a message here would arrive with nowhere to be read.
      console.warn(`[pi-subagents] ${unconfirmed.length} child process(es) did not confirm they closed: ${unconfirmed.map((entry) => entry.name).join(", ")}`);
    }
  });
}

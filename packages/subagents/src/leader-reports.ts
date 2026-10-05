export const AGENT_REPORT_MESSAGE_TYPE = "agent-teams-report";
export const AGENT_HARNESS_MESSAGE_TYPE = "agent-teams-harness";

/**
 * A report as it may still be found in a transcript written before the sender's
 * key was renamed. Read, never written: the old key is kept for transcripts alone,
 * and it lives in one reader rather than in the domain type, so a report is
 * described in one word everywhere else.
 */
type LegacyLeaderReport = LeaderReport & { teammate?: string };

/** Whose report this is. The one key, on the way in and on the way out. */
function senderOf(report: LeaderReport | LegacyLeaderReport): string | undefined {
  return report.agent ?? (report as LegacyLeaderReport).teammate;
}

export interface LeaderReport {
  /** Who sent it. The name the recipient addresses. */
  agent?: string;
  /** The role it ran, when the sender's role is worth recording. */
  role?: string;
  inputId?: string;
  spawnId?: string;
  assignmentId?: string;
  workId?: string;
  body: string;
  /** Agent-authored reports are the default; harness events use a separate
   *  envelope. A report written before the rename carries the previous word for
   *  this origin, which reads as an agent report either way. */
  origin?: "agent" | "harness";
  harnessEvent?: {
    type: string;
    subject: string;
  };
  finished?: boolean;
  /** Original append-only outbox event identifier, retained for session forensics. */
  eventId?: string;
  /** Original Agent status, including omitted status, retained for session forensics. */
  status?: "in_progress" | "completed" | "failed" | "inform" | "request" | "handoff";
  runId?: string;
  /** Wall-clock time the message was authored, not when Pi consumed it. */
  timestamp?: number;
  deliveredAt?: number;
  processStoppedAt?: number;
  deliveredAfterStop?: boolean;
}

export interface LeaderReportGroup {
  agent: string;
  reports: LeaderReport[];
}

export function groupReportsByAgent(reports: LeaderReport[]): LeaderReportGroup[] {
  const groups = new Map<string, LeaderReportGroup>();
  for (const report of reports) {
    const agent = senderOf(report) ?? "agent";
    if (report.origin === "harness" || report.harnessEvent) {
      groups.set(`harness:${groups.size}:${agent}`, { agent, reports: [report] });
      continue;
    }
    const key = `message:${agent}`;
    const group = groups.get(key);
    if (group) {
      group.reports.push(report);
    } else {
      groups.set(key, { agent, reports: [report] });
    }
  }
  return [...groups.values()];
}

export function annotateReportDelivery(report: LeaderReport, deliveredAt: number, processStoppedAt?: number): LeaderReport {
  if (processStoppedAt === undefined || deliveredAt < processStoppedAt) return { ...report, deliveredAt };
  return { ...report, deliveredAt, processStoppedAt, deliveredAfterStop: true };
}

function timestampAttribute(name: string, timestamp: number | undefined): string {
  return validTimestamp(timestamp)
    ? ` ${name}="${new Date(timestamp).toISOString()}"`
    : "";
}

// Date#toISOString throws outside ECMAScript's representable time range even
// when the report carries a finite number. Report formatting is a readback
// boundary, so omit malformed timestamps while preserving the authored body.
const MAX_DATE_MILLISECONDS = 8_640_000_000_000_000;

function validTimestamp(timestamp: number | undefined): timestamp is number {
  return timestamp !== undefined && Number.isFinite(timestamp)
    && Math.abs(timestamp) <= MAX_DATE_MILLISECONDS;
}

export function formatReports(reports: LeaderReport[]): string {
  return reports
    .map((report) => {
      const { body, timestamp, origin, harnessEvent } = report;
      const at = timestampAttribute("at", timestamp);
      if (origin === "harness" || harnessEvent) {
        const type = escapeAttribute(harnessEvent?.type ?? "event");
        const subject = escapeAttribute(harnessEvent?.subject ?? "Agent Teams event");
        return `<harness-event type="${type}" subject="${subject}"${at}>\n${body}\n</harness-event>`;
      }
      // Grouping already resolves the sender, so the envelope has to as well: a
      // delivered report reading `from="agent"` attributes a message to nobody
      // while the group it sits in is labelled with the Agent that sent it.
      const name = senderOf(report) ?? "agent";
      const delivery = timestampAttribute("delivered-at", report.deliveredAt);
      const stopped = timestampAttribute("process-stopped-at", report.processStoppedAt);
      const late = report.deliveredAfterStop ? ' delivery="after-stop"' : "";
      const input = report.inputId ? ` input="${escapeAttribute(report.inputId)}"` : "";
      const work = report.workId ? ` work="${escapeAttribute(report.workId)}"` : "";
      const assignment = report.assignmentId ? ` assignment="${escapeAttribute(report.assignmentId)}"` : "";
      const status = report.status ? ` status="${escapeAttribute(report.status)}"` : "";
      const note = report.deliveredAfterStop
        ? "Delivery note: this report was queued before shutdown and delivered after the process stopped. It does not reopen the assignment.\n\n"
        : "";
      return `<agent-message from="${escapeAttribute(name)}"${at}${delivery}${stopped}${late}${input}${work}${assignment}${status}>\n${note}${body}\n</agent-message>`;
    })
    .join("\n\n");
}

function escapeAttribute(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

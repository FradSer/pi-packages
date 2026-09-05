export const TEAMMATE_REPORT_MESSAGE_TYPE = "agent-teams-report";
export const TEAMMATE_HARNESS_MESSAGE_TYPE = "agent-teams-harness";

export interface LeaderReport {
  teammate?: string;
  agent?: string;
  spawnId?: string;
  body: string;
  /** Worker-authored reports are the default; harness events use a separate envelope. */
  origin?: "teammate" | "harness";
  harnessEvent?: {
    type: string;
    subject: string;
  };
  finished?: boolean;
  /** Original append-only outbox event identifier, retained for session forensics. */
  eventId?: string;
  /** Original worker status, including omitted status, retained for session forensics. */
  status?: "in_progress" | "completed" | "failed";
  health?: {
    state: "stalled";
    silenceMs: number;
  };
  runId?: string;
  /** Wall-clock time the message was authored, not when Pi consumed it. */
  timestamp?: number;
}

export interface LeaderReportGroup {
  teammate: string;
  reports: LeaderReport[];
}

export function groupReportsByTeammate(reports: LeaderReport[]): LeaderReportGroup[] {
  const groups = new Map<string, LeaderReportGroup>();
  for (const report of reports) {
    const teammate = report.teammate ?? report.agent ?? "teammate";
    if (report.health) {
      groups.set(`health:${groups.size}:${teammate}`, { teammate, reports: [report] });
      continue;
    }
    if (report.origin === "harness" || report.harnessEvent) {
      groups.set(`harness:${groups.size}:${teammate}`, { teammate, reports: [report] });
      continue;
    }
    const key = `message:${teammate}`;
    const group = groups.get(key);
    if (group) {
      group.reports.push(report);
    } else {
      groups.set(key, { teammate, reports: [report] });
    }
  }
  return [...groups.values()];
}

export function formatReports(reports: LeaderReport[]): string {
  return reports
    .map((report) => {
      const { teammate, body, timestamp, origin, harnessEvent } = report;
      const at = timestamp !== undefined && Number.isFinite(timestamp)
        ? ` at="${new Date(timestamp).toISOString()}"`
        : "";
      if (origin === "harness" || harnessEvent) {
        const type = escapeAttribute(harnessEvent?.type ?? "event");
        const subject = escapeAttribute(harnessEvent?.subject ?? "Agent Teams event");
        return `<harness-event type="${type}" subject="${subject}"${at}>\n${body}\n</harness-event>`;
      }
      const name = teammate ?? "teammate";
      return `<agent-message from="${escapeAttribute(name)}"${at}>\n${body}\n</agent-message>`;
    })
    .join("\n\n");
}

function escapeAttribute(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

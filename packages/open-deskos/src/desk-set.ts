import type { DeskLinkSnapshot } from "./reporter.ts";
import type { DeskLinkConfig } from "./types.ts";

/** A desk's own snapshot plus the endpoint it belongs to, so an aggregate can name it. */
export interface DeskSnapshot extends DeskLinkSnapshot {
  endpoint: string;
}

/**
 * The desk the Console drives. Only a desk that issued a control credential can
 * be driven, so that desk is chosen by default; an operator who names one gets
 * that one, even when it has no credential, because quietly driving a different
 * desk than the one asked for would be worse than saying a credential is needed.
 */
export function selectConsoleDesk(configs: DeskLinkConfig[], preferred = ""): DeskLinkConfig | null {
  const wanted = preferred.trim();
  if (wanted.length > 0) {
    return configs.find((config) => `${config.host}:${config.port}` === wanted || config.host === wanted) ?? null;
  }
  return configs.find((config) => Boolean(config.controlToken)) ?? null;
}

/**
 * One state for a machine that reports to several desks.
 *
 * `connected` is claimed only when every desk is connected, and `offline` only
 * when every desk is offline, because a set that is half up is neither. Counts
 * come from the desks that are up, so a desk that is down cannot make this
 * machine look like it is reporting nothing.
 */
export function aggregateDeskSnapshots(snapshots: DeskSnapshot[]): DeskLinkSnapshot | null {
  if (snapshots.length === 0) return null;
  if (snapshots.length === 1) {
    const only = snapshots[0];
    if (only === undefined) return null;
    const { endpoint: _endpoint, ...snapshot } = only;
    return { ...snapshot, desks: [{ endpoint: only.endpoint, link: only.link, ...(only.lastError === undefined ? {} : { lastError: only.lastError }) }] };
  }

  const connected = snapshots.filter((snapshot) => snapshot.link === "connected");
  const link: DeskLinkSnapshot["link"] = connected.length === snapshots.length
    ? "connected"
    : connected.length === 0 && snapshots.every((snapshot) => snapshot.link === "offline")
      ? "offline"
      : "connecting";

  const reporting = connected.length > 0 ? connected : snapshots;
  const total = (pick: (snapshot: DeskSnapshot) => number): number => reporting.reduce((sum, snapshot) => sum + pick(snapshot), 0);
  const firstError = snapshots.find((snapshot) => snapshot.lastError !== undefined)?.lastError;

  return {
    link,
    machine: snapshots[0]?.machine ?? "",
    sessions: total((snapshot) => snapshot.sessions),
    events: total((snapshot) => snapshot.events),
    attempts: snapshots.reduce((most, snapshot) => Math.max(most, snapshot.attempts), 0),
    omittedSessions: total((snapshot) => snapshot.omittedSessions),
    ...(firstError === undefined ? {} : { lastError: firstError }),
    desks: snapshots.map((snapshot) => ({
      endpoint: snapshot.endpoint,
      link: snapshot.link,
      ...(snapshot.lastError === undefined ? {} : { lastError: snapshot.lastError }),
    })),
  };
}
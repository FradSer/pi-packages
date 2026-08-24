/**
 * Keystroke routing for the teammate-model picker. Pure mapping from raw
 * terminal input to picker actions so the collision-prone decision table is
 * unit-testable without a TUI: every printable character (letters included)
 * must route to typing, never to a shortcut.
 */

import { Key, matchesKey } from "@earendil-works/pi-tui";

export type PickerKeyAction =
  | { kind: "type"; text: string }
  | { kind: "backspace" }
  | { kind: "up" }
  | { kind: "down" }
  | { kind: "confirm" }
  | { kind: "cancel" };

/** Map one raw input event to a picker action, or undefined when the event
 *  is not a picker key (multi-byte pastes, unhandled control sequences). */
export function mapPickerKey(data: string): PickerKeyAction | undefined {
  if (matchesKey(data, Key.escape)) return { kind: "cancel" };
  if (matchesKey(data, Key.enter)) return { kind: "confirm" };
  if (matchesKey(data, Key.up)) return { kind: "up" };
  if (matchesKey(data, Key.down)) return { kind: "down" };
  if (matchesKey(data, Key.backspace) || matchesKey(data, Key.delete)) return { kind: "backspace" };
  // Printable characters are always search text — letters like "c" must
  // never double as shortcuts in a type-to-filter list.
  if (data.length === 1 && data >= " ") return { kind: "type", text: data };
  return undefined;
}

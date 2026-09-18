/** Registry writers use either a Pi UUID or the timestamp_UUID log basename. */
export function normalizeSessionId(value: unknown): string {
  if (typeof value !== "string") return "";
  const id = value.trim();
  // Never truncate identity: doing so could collapse two different sessions.
  if (!id || id.length > 200 || /[\x00-\x1f\x7f]/.test(id)) return "";
  for (const character of id) {
    const code = character.codePointAt(0)!;
    if (code >= 0xd800 && code <= 0xdfff) return "";
  }
  const uuid = id.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
  return uuid ? uuid[1]!.toLowerCase() : id;
}

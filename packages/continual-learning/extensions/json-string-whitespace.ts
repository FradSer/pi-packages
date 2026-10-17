/** Recover only literal JSON string whitespace; never change a field's value. */
export function normalizeJsonStringWhitespace(text: string, maxBytes: number): {
  text: string; counts: { newline: number; carriageReturn: number; tab: number };
} | undefined {
  if (Buffer.byteLength(text, "utf8") > maxBytes) return undefined;
  const counts = {newline:0, carriageReturn:0, tab:0};
  let quoted = false, escaped = false, normalized = "";
  for (const character of text) {
    if (escaped) {
      // A backslash followed by a raw control is not a recoverable escape.
      if (character.charCodeAt(0) < 0x20) return undefined;
      escaped = false;
      normalized += character;
      continue;
    }
    if (quoted && character === "\\") {
      escaped = true;
      normalized += character;
      continue;
    }
    if (character === '"') quoted = !quoted;
    if (quoted && character.charCodeAt(0) < 0x20) {
      if (character === "\n") { counts.newline++; normalized += "\\n"; }
      else if (character === "\r") { counts.carriageReturn++; normalized += "\\r"; }
      else if (character === "\t") { counts.tab++; normalized += "\\t"; }
      else return undefined;
    } else normalized += character;
  }
  if (quoted || escaped || !Object.values(counts).some(Boolean)
    || Buffer.byteLength(normalized, "utf8") > maxBytes) return undefined;
  try {
    // Require exactly one complete object. Do not repair punctuation, escapes,
    // prose, arrays, truncated drafts or multiple responses.
    const value: unknown = JSON.parse(normalized);
    if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
    return {text:normalized, counts};
  } catch { return undefined; }
}

/** Entry-scoped intent routing for the single learn tool.
 *
 * This is deliberately NOT screenLearningEntries. That function is the frozen
 * evidence screen used by the consolidation pipeline and its historical proofs;
 * its constraint -> {memory, harness} truth table is unchanged. This classifier
 * only decides which parent-owned deep-module entry an EXPLICIT user request
 * should call. It reads one real user entry, never a recursive text blob, and
 * never receives model-supplied intent, content or path.
 */
import { entryRole } from "./incremental-learning";

export type LearnRoute = "harness" | "memory" | "none";

/** Explicit requests to add, correct, retire or permanently constrain a rule. */
const HARNESS_REQUEST = /以后(?:禁止|不得|严禁|不要)|永久(?:禁止|约束|规则|生效)|今后(?:禁止|不得)|给后续(?:加|添加)规则|添加规则|加一条规则|纠正(?:旧|现有)?规则|退役(?:旧|现有)?规则|撤销(?:旧|现有)?规则|永久约束|持久约束|要求[^\n]{0,24}(?:回归测试|检查|验证)|\bretire\s+(?:the\s+)?(?:old\s+)?rule\b|\bcorrect\s+(?:the\s+)?(?:old\s+)?rule\b|\badd\s+(?:a\s+)?(?:lasting\s+|permanent\s+|durable\s+)?rule\b|\brequire\s+a\s+regression\s+test\s+before\s+publishing\b|\bpermanently\s+(?:constrain|prohibit|block)\b|(?:never|always|do\s+not)\b[^\n]{0,80}\b(?:future\s+tasks?|from\s+now\s+on|before\s+committing|before\s+publishing)\b|\bfrom\s+now\s+on\b[^\n]{0,80}\b(?:always|never|run|require|use)\b/iu;

/** Explicit requests to organize or remember Memory. */
const MEMORY_REQUEST = /整理记忆|梳理记忆|整理一下记忆|记住这个|记住以下|把这些记住|\bremember\s+this\b|\bconsolidate\s+memory\b|\borganize\s+memory\b|\btidy\s+(?:the\s+)?memory\b/iu;

/** A negation that governs the request phrase itself, not an unrelated
 * privacy caveat elsewhere in the same message. */
const NEGATED_HARNESS = /不(?:要|用|必)(?:加|添加|纠正|退役|撤销|约束|禁止)|别(?:加|禁止|约束)|无需(?:加|禁止)|do\s+not\s+(?:add|correct|retire|require|permanently)|don['’]t\s+(?:add|correct|retire|require)|no\s+need\s+to\s+(?:add|correct|require)/iu;
const NEGATED_MEMORY = /不(?:要|用|必)(?:整理|记住|梳理)|别(?:整理|记住)|无需整理|do\s+not\s+(?:remember|organize|consolidate|tidy)\s+(?:this|memory)|don['’]t\s+(?:remember|organize|consolidate|tidy)\s+(?:this|memory)|no\s+need\s+to\s+(?:remember|organize|consolidate)/iu;

/** A quoted command name inside an explanation is not a request. */
const EXPLANATION = /explain|describe|what\s+(?:does|is)|meaning|documentation|readme|quote|quoted|written\s+in|解释|意思是|文档|引用|引号|说明/iu;
const QUOTED = /["'「『]([^"'」』]+)["'」』]/gu;

/** Only the last real user entry can name the request. */
export function lastUserText(entries: readonly unknown[]): string {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const entry = entries[index];
    if (entryRole(entry) !== "user" || !entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const record = entry as Record<string, unknown>;
    const message = record.message && typeof record.message === "object" && !Array.isArray(record.message)
      ? record.message as Record<string, unknown> : record;
    const content = message.content;
    if (typeof content === "string") return content.trim();
    if (!Array.isArray(content)) continue;
    const text = content
      .filter((block): block is { type: string; text: string } => Boolean(block) && typeof block === "object"
        && (block as Record<string, unknown>).type === "text" && typeof (block as Record<string, unknown>).text === "string")
      .map((block) => block.text).join("\n");
    return text.trim();
  }
  return "";
}

/** True when every matched request phrase lies inside a quoted span. */
function onlyQuoted(text: string, pattern: RegExp): boolean {
  const quotedSpans: Array<[number, number]> = [];
  for (const match of text.matchAll(QUOTED)) {
    const index = match.index ?? 0;
    quotedSpans.push([index, index + match[0].length]);
  }
  if (!quotedSpans.length) return false;
  const global = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`);
  const matches = [...text.matchAll(global)];
  if (!matches.length) return false;
  return matches.every(match => {
    const start = match.index ?? 0;
    const end = start + match[0].length;
    return quotedSpans.some(([from, to]) => from <= start && end <= to);
  });
}

export function classifyLearnRoute(text: string): LearnRoute {
  const value = text.trim();
  if (!value) return "none";
  const harness = HARNESS_REQUEST.test(value);
  const memory = MEMORY_REQUEST.test(value);
  if (EXPLANATION.test(value)) {
    if (harness && !memory && onlyQuoted(value, HARNESS_REQUEST)) return "none";
    if (memory && !harness && onlyQuoted(value, MEMORY_REQUEST)) return "none";
  }
  if (harness && !NEGATED_HARNESS.test(value)) return "harness";
  if (memory && !NEGATED_MEMORY.test(value)) return "memory";
  return "none";
}

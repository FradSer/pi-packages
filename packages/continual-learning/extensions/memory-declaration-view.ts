import {parse} from "@babel/parser";
import {createHash} from "node:crypto";

type Row = Record<string, unknown>;
const row = (value: unknown): Row | undefined => value && typeof value === "object" && !Array.isArray(value) ? value as Row : undefined;
const message = (value: unknown): Row | undefined => row(row(value)?.message) ?? row(value);
const hash = (text: string) => createHash("sha256").update(text).digest("hex");
const MAX_SOURCE_BYTES = 128_000;
const MAX_VIEW_BYTES = 32_000;
const MAX_NODES = 128;
export interface DeclarationBlock {block: number; text: string; lines: readonly Row[]}

/** Syntax of the observed region only. No resolver, filesystem access, inferred
 * runtime behavior, complete-file claim or Memory/citation mutation belongs here. */
export function memoryDeclarationViews(entries: readonly unknown[], index: number, blocks: readonly DeclarationBlock[]): Row[] | undefined {
  const result = message(entries[index]);
  if (result?.role !== "toolResult" || result.isError !== false || !["read", "learning_read"].includes(String(result.toolName))
    || typeof result.toolCallId !== "string") return;
  const calls = entries.flatMap((entry, position) => {
    const m = message(entry);
    return m?.role === "assistant" && Array.isArray(m.content) ? m.content.flatMap(value => {
      const call = row(value);
      return call?.type === "toolCall" && call.id === result.toolCallId ? [{call, position}] : [];
    }) : [];
  });
  if (calls.length !== 1 || calls[0].position >= index || calls[0].call.name !== result.toolName
    || entries.filter(entry => {const m = message(entry);return m?.role === "toolResult" && m.toolCallId === result.toolCallId;}).length !== 1) return;
  const args = row(calls[0].call.arguments), path = args?.path;
  if ([args?.offset, args?.limit].some(value => value !== undefined && (!Number.isSafeInteger(value) || Number(value) < 1))) return;
  if (typeof path !== "string" || !/\.d\.(?:ts|mts|cts)$/.test(path)
    || path.split(/[\\/]/).some(part => [".memory", ".pi", ".git", ".."].includes(part.toLowerCase()))) return;
  if (blocks.length > 32 || blocks.reduce((sum, block) => sum + Buffer.byteLength(block.text), 0) > MAX_SOURCE_BYTES) {
    return [{version: 1, sourceEntry: index, scope: "observed-region", status: "omitted",
      reason: "entry-source-limit", omittedRegionCount: blocks.length}];
  }
  const views = blocks.map(block => declarationView(block, index, String(result.toolName), args!));
  return Buffer.byteLength(JSON.stringify(views)) <= MAX_VIEW_BYTES ? views : [
    {version: 1, sourceEntry: index, scope: "observed-region", status: "omitted", reason: "entry-view-size-limit", omittedRegionCount: blocks.length}];
}

function declarationView(block: DeclarationBlock, index: number, tool: string, args: Row): Row {
  const base = {version: 1, sourceEntry: index, block: block.block, sourceTextSha256: hash(block.text),
    scope: "observed-region", coverage: "supported-top-level-syntax-only", authority: "untrusted-reference-data", readOffset: args.offset ?? 1, meaning: "Observed top-level function, interface and type-alias syntax only; omitted families or members do not establish absence. Local candidates do not resolve imports or establish runtime behavior."};
  const omitted = (reason: string, count: number | null = null): Row => ({...base, status: "omitted", reason, omittedNodeCount: count});
  if (Buffer.byteLength(block.text) > MAX_SOURCE_BYTES) return omitted("source-size-limit");
  let text = block.text;
  // This suffix belongs to the existing scoped reader. Removing only its footer
  // preserves every source character and its original result-block coordinates.
  const footer = /\n\[lines (\d+)-(\d+) of (\d+)(; byte limit reached)?\]$/.exec(text);
  if (tool === "learning_read" && footer) {
    if (footer[4]) return omitted("truncated-region");
    if (Number(footer[1]) !== (args.offset ?? 1) || Number(footer[2]) < Number(footer[1])
      || Number(footer[2]) > Number(footer[3])) return omitted("invalid-read-envelope");
    text = text.slice(0, footer.index);
    if (text.split("\n").length !== Number(footer[2]) - Number(footer[1]) + 1) return omitted("invalid-read-envelope");
  }
  let statements: Row[];
  try {
    statements = parse(text, {sourceType: "module", plugins: [["typescript", {dts: true}]], errorRecovery: false}).program.body as unknown as Row[];
  } catch {return omitted("parse-error");}
  const bindings = new Map<string, number>();
  const declarations: {node: Row; whole: Row}[] = [];
  const nameOf = (value: unknown) => {const n = row(value);return n?.type === "Identifier" && typeof n.name === "string" ? n.name : undefined;};
  for (const whole of statements) {
    const node = row(whole.declaration) ?? whole;
    const name = nameOf(node.id);
    if (name) bindings.set(name, (bindings.get(name) ?? 0) + 1);
    if (node.type === "ImportDeclaration" && Array.isArray(node.specifiers)) for (const specifier of node.specifiers) {
      const name = nameOf(row(specifier)?.local);
      if (name) bindings.set(name, (bindings.get(name) ?? 0) + 1);
    }
    if (["TSTypeAliasDeclaration", "TSInterfaceDeclaration", "TSDeclareFunction", "FunctionDeclaration"].includes(String(node.type))) declarations.push({node, whole});
  }
  const directMembers = (node: Row): unknown[] => {
    const body = row(node.typeAnnotation) ?? row(node.body);
    const values = body?.type === "TSTypeLiteral" ? body.members : body?.type === "TSInterfaceBody" ? body.body : [];
    return Array.isArray(values) ? values : [];
  };
  const nodeCount = declarations.reduce((count, {node}) => count + 1 + directMembers(node).length, 0);
  if (nodeCount > MAX_NODES) return omitted("node-count-limit", nodeCount);
  const starts = [0];for (let i = 0; i < block.text.length; i++) if (block.text[i] === "\n") starts.push(i + 1);
  const lineAt = (offset: number) => {
    let low = 0, high = starts.length;
    while (low + 1 < high) {const middle = (low + high) >>> 1;if (starts[middle] <= offset) low = middle;else high = middle;}
    return low;
  };
  const source = (node: Row): Row | undefined => {
    if (!Number.isSafeInteger(node.start) || !Number.isSafeInteger(node.end) || Number(node.start) < 0
      || Number(node.end) <= Number(node.start) || Number(node.end) > text.length) return;
    const first = lineAt(Number(node.start)), last = lineAt(Number(node.end) - 1);
    const a = block.lines[first], b = block.lines[last];
    // Long-line chunks remain in the original view; do not invent a mixed
    // chunk/line range which the ordinary citation interface cannot resolve.
    if (typeof a?.ref !== "string" || typeof b?.ref !== "string") return;
    const quote = block.text.slice(starts[first], last + 1 < starts.length ? starts[last + 1] - 1 : block.text.length);
    return {ref: a.ref, endRef: b.ref, quote, characters: quote.length, withinCitationLimit: quote.length <= 2000,
      syntaxStart: node.start, syntaxEnd: node.end};
  };
  let omittedNodes = 0;
  const nodes: Row[] = [];
  for (const {node, whole} of declarations) {
    const position = source(whole), name = nameOf(node.id);
    if (!position || !name) {omittedNodes++;continue;}
    const value: Row = {id: `e${index}.b${block.block}.s${whole.start}-${whole.end}`, name, syntaxKind: node.type,
      syntax: text.slice(Number(whole.start), Number(whole.end)), source: position};
    if (["TSDeclareFunction", "FunctionDeclaration"].includes(String(node.type))) {
      const annotation = row(row(node.returnType)?.typeAnnotation);
      if (annotation) {
        value.outerReturnKind = annotation.type;
        value.outerReturnSyntax = text.slice(Number(annotation.start), Number(annotation.end));
        value.outerReturnSource = source(annotation);
      }
      const named = annotation?.type === "TSTypeReference" ? nameOf(annotation.typeName) : undefined;
      if (named) {
        value.namedReturn = named;
        const parameters = row(node.typeParameters)?.params;
        if (Array.isArray(parameters) && parameters.some(parameter => row(parameter)?.name === named)) {
          value.namedReturnScope = "function-type-parameter";
        }
      }
    } else {
      value.members = directMembers(node).flatMap(member => {
        const m = row(member), position = m && source(m);
        if (!m || !position) {omittedNodes++;return [];}
        const key = row(m.key), name = m.computed ? undefined : nameOf(key) ?? (key?.type === "StringLiteral" ? key.value : undefined);
        return [{...(typeof name === "string" ? {name} : {}), syntaxKind: m.type, source: position}];
      });
    }
    nodes.push(value);
  }
  for (const node of nodes) if (typeof node.namedReturn === "string" && node.namedReturnScope !== "function-type-parameter" && bindings.get(node.namedReturn) === 1) {
    const target = nodes.find(other => other.name === node.namedReturn && ["TSTypeAliasDeclaration", "TSInterfaceDeclaration"].includes(String(other.syntaxKind)));
    if (target) node.observedTypeCandidate = target.id;
  }
  const view = {...base, status: "available", declarations: nodes, omittedNodeCount: omittedNodes};
  if (Buffer.byteLength(JSON.stringify(view)) > MAX_VIEW_BYTES) return omitted("view-size-limit", nodeCount);
  return view;
}

/** A selected reference is body-copy eligible only for one whole observed outer
 * function declaration. This chooses no reference and infers no runtime fact. */
export function isObservedFunctionDeclaration(snapshot: unknown, selection: unknown): boolean {
  const entries = row(snapshot)?.entries, citation = row(selection);
  if (!Array.isArray(entries) || typeof citation?.ref !== "string") return false;
  const start = /^e(\d+)\.b(\d+)\.l(\d+)$/.exec(citation.ref);
  if (!start) return false;
  const index = Number(start[1]), block = Number(start[2]), result = message(entries[index]);
  const content = result?.content, part = Array.isArray(content) ? content[block] : block === 0 ? content : undefined;
  const text = typeof part === "string" ? part : row(part)?.type === "text" ? row(part)?.text : undefined;
  if (typeof text !== "string") return false;
  const lines = text.split("\n").map((text, line) => ({text, ...(text.trim() && text.length <= 2000 ? {ref: `e${index}.b${block}.l${line + 1}`} : {})}));
  const views = memoryDeclarationViews(entries, index, [{block, text, lines}]);
  return !!views?.some(view => Array.isArray(view.declarations) && view.declarations.some(value => {
    const node = row(value), source = row(node?.source);
    return ["TSDeclareFunction", "FunctionDeclaration"].includes(String(node?.syntaxKind))
      && source?.ref === citation.ref && source?.endRef === (citation.endRef ?? citation.ref)
      && typeof source?.quote === "string" && typeof node?.syntax === "string" && source.quote.trim() === node.syntax.trim();
  }));
}

/** Recheck outer syntax against the complete current source already read by the
 * source-binding path. Exact selected line coordinates prevent borrowing an
 * equal outer declaration from a different comment or namespace occurrence. */
export function isCompleteOuterFunctionDeclaration(text: string, quote: string, firstLine: number, lastLine: number): boolean {
  if (Buffer.byteLength(text) > MAX_SOURCE_BYTES || !quote.trim() || !Number.isSafeInteger(firstLine)
    || !Number.isSafeInteger(lastLine) || firstLine < 1 || lastLine < firstLine
    || text.split("\n").slice(firstLine - 1, lastLine).join("\n") !== quote) return false;
  try {
    const statements = parse(text, {sourceType: "module", plugins: [["typescript", {dts: true}]], errorRecovery: false}).program.body;
    return statements.filter(whole => {
      const node = row(whole)?.declaration ?? whole;
      return ["TSDeclareFunction", "FunctionDeclaration"].includes(String(row(node)?.type))
        && whole.loc?.start.line === firstLine && whole.loc?.end.line === lastLine
        && text.slice(whole.start!, whole.end!).trim() === quote.trim();
    }).length === 1;
  } catch {return false;}
}

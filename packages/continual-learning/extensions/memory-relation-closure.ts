import {parse} from "@babel/parser";
import path from "node:path";
import {createHash} from "node:crypto";

type Node = Record<string, any>;
type Source = {index: number; aliases: number[]; file: string; text: string; digest: string; ast: Node};
type Span = {ref: string; endRef?: string; sourceSpan?: {start: number; end: number}};
type ImplementationSource = {owner: string; file: string; sourcePath: string; sourceSha256: string};
type ImplementationRequirement = ImplementationSource & {roles: {role: string; alternatives: Span[]}[]};
export type SelectedMemoryRelation = {factory: string; owner: string; member: string; file: string; sourcePath: string; sourceSha256: string; indexes: number[]; sourceSelections?: (Span & {index: number})[];
  implementation?: ImplementationSource & {indexes: number[]; sourceSelections: (Span & {index: number})[]}};
export type MemoryRelationRequirement = Omit<SelectedMemoryRelation, "indexes" | "implementation"> & {
  wrapper?: string; roles: {role: string; alternatives: Span[]}[];
  initiatingWrapperWitness?: {alternatives: Span[]};
  implementation?: ImplementationRequirement;
};
export type SourceRoleRangeChoice = {ref: string; endRef?: string; utf16Length: number; coversRoles: string[]; coversOriginalSupports: string[]};
export type MemoryRelationObligations = {snapshotProjectionDigest: string; requirements: MemoryRelationRequirement[]; sourceRangeChoices?: SourceRoleRangeChoice[]};
export class MemoryRelationClosureError extends Error {
  constructor(message: string, readonly snapshotProjectionDigest?: string, readonly obligations?: MemoryRelationObligations) {super(message);this.name = "MemoryRelationClosureError";}
}
const object = (value: unknown): Node | undefined => value && typeof value === "object" && !Array.isArray(value) ? value as Node : undefined;
const message = (value: unknown): Node | undefined => object(object(value)?.message) ?? object(value);
const identifier = (value: any): string | undefined => value?.type === "Identifier" ? value.name : undefined;
const MAX_SOURCE = 128_000;
function walk(node: any, visit: (node: Node) => void, outerCallsOnly = false): void {
  let count = 0;
  const next = (value: any) => {
    if (!value || typeof value !== "object") return;
    if (++count > 30_000) throw new Error("Bounded syntax traversal");
    if (outerCallsOnly && ["FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression", "ObjectMethod", "ClassMethod", "ClassPrivateMethod", "ClassDeclaration", "ClassExpression"].includes(value.type)) return;
    if (typeof value.type === "string") visit(value);
    for (const [key, child] of Object.entries(value)) {
      if (["loc", "tokens", "comments", "leadingComments", "trailingComments", "innerComments"].includes(key)) continue;
      if (Array.isArray(child)) child.forEach(next);else if (child && typeof child === "object") next(child);
    }
  };
  next(node);
}
function names(pattern: any): string[] {
  if (!pattern) return [];
  if (pattern.type === "Identifier") return [pattern.name];
  if (pattern.type === "RestElement") return names(pattern.argument);
  if (pattern.type === "AssignmentPattern") return names(pattern.left);
  if (pattern.type === "ArrayPattern") return pattern.elements.flatMap(names);
  if (pattern.type === "ObjectPattern") return pattern.properties.flatMap((p: any) => names(p.type === "RestElement" ? p.argument : p.value));
  return [];
}
function bindings(node: Node): string[] {
  if (["FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression"].includes(node.type)) return [...names(node.id), ...(node.params ?? []).flatMap(names)];
  if (node.type === "VariableDeclarator") return names(node.id);
  if (node.type === "ClassDeclaration" || node.type === "ClassExpression") return names(node.id);
  if (node.type === "CatchClause") return names(node.param);
  if (/^Import.*Specifier$/.test(node.type)) return names(node.local);
  return [];
}
function top(ast: Node): {node: Node; whole: Node; exported?: string}[] {
  return ast.program.body.map((whole: Node) => ({whole, node: whole.declaration ?? whole,
    exported: whole.type === "ExportDefaultDeclaration" ? "default" : whole.type === "ExportNamedDeclaration" ? "named" : undefined}));
}
function span(source: Source, node: Node): Span {
  const ref = `e${source.index}.b0.l${node.loc.start.line}`, endRef = `e${source.index}.b0.l${node.loc.end.line}`;
  const lineStart = source.text.lastIndexOf("\n", node.start - 1) + 1;
  const start = /^[\t ]*$/.test(source.text.slice(lineStart, node.start)) ? lineStart : node.start;
  return {ref, ...(ref === endRef ? {} : {endRef}), sourceSpan: {start, end: node.end}};
}
function publicSpan(value: Span): {ref: string; endRef?: string} {
  return {ref: value.ref, ...(value.endRef === undefined ? {} : {endRef: value.endRef})};
}
function covers(citation: any, required: Span): boolean {
  const a = /^(e\d+\.b0\.l)(\d+)$/.exec(citation?.ref), b = /^(e\d+\.b0\.l)(\d+)$/.exec(citation?.endRef ?? citation?.ref);
  const x = /^(e\d+\.b0\.l)(\d+)$/.exec(required.ref), y = /^(e\d+\.b0\.l)(\d+)$/.exec(required.endRef ?? required.ref);
  return !!a && !!b && !!x && !!y && a[1] === b[1] && a[1] === x[1] && x[1] === y[1] && Number(a[2]) <= Number(x[2]) && Number(b[2]) >= Number(y[2]);
}
function visible(text: string): string {
  const cleaned = text.replace(/<(?:file|pre)\b[^>]*>[\s\S]*?(?:<\/(?:file|pre)>|$)/gi, "")
    .replace(/<!--(?:[\s\S]*?-->|[\s\S]*$)/g, "");
  let fence: {character: string; length: number} | undefined;
  const prose: string[] = [];
  for (const line of cleaned.split("\n")) {
    if (fence) {
      if (new RegExp(`^ {0,3}${fence.character}{${fence.length},}[ \\t]*$`).test(line)) fence = undefined;
      continue;
    }
    if (/^(?: {0,3}>| {4}|\t)/.test(line)) continue;
    const opening = /^ {0,3}(`{3,}|~{3,})/.exec(line);
    if (opening) {fence = {character: opening[1][0], length: opening[1].length};continue;}
    if (line.replace(/`[^`]*`/g, "").replace(/[\s.,:;!?]/g, "")) prose.push(line);
  }
  return prose.join("\n").replace(/"[^"\n]*"|(?<![\p{ID_Continue}\u200c\u200d$])'[^\n]*?'(?![\p{ID_Continue}\u200c\u200d$])|“[^”\n]*”|‘[^’\n]*’/gu, "");
}
function mentions(text: string, name: string): boolean {
  return new RegExp(`(^|[^\\p{ID_Continue}\\u200c\\u200d$])${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}($|[^\\p{ID_Continue}\\u200c\\u200d$])`, "u").test(text);
}
function sources(snapshot: unknown, cwd: string, selectedEntries: Set<number>): Source[] {
  const entries = object(snapshot)?.entries;
  if (!Array.isArray(entries)) return [];
  const out: Source[] = [];
  // Keep the original selected AST groups and their bound. A second pass only
  // recognizes complete same-path/same-digest observations as reference aliases.
  for (const aliasesOnly of [false, true]) entries.forEach((entry, index) => {
    if (aliasesOnly && selectedEntries.has(index)) return;
    const result = message(entry);
    if (result?.role !== "toolResult" || result.isError !== false || !["read", "learning_read"].includes(result.toolName)) return;
    const calls = entries.flatMap((value, at) => {
      const m = message(value);return m?.role === "assistant" && Array.isArray(m.content)
        ? m.content.filter((c: any) => c?.type === "toolCall" && c.id === result.toolCallId).map((call: Node) => ({call, at})) : [];
    });
    if (calls.length !== 1 || calls[0].at >= index || calls[0].call.name !== result.toolName
      || entries.filter(value => message(value)?.role === "toolResult" && message(value)?.toolCallId === result.toolCallId).length !== 1) return;
    const args = object(calls[0].call.arguments);
    if (typeof args?.path !== "string" || (args.offset ?? 1) !== 1) return;
    const file = path.resolve(cwd, args.path), relative = path.relative(path.resolve(cwd), file);
    if (!relative || path.isAbsolute(relative) || relative.split(path.sep).some(p => ["..", ".memory", ".pi", ".git"].includes(p.toLowerCase()))) return;
    if (!file.endsWith(`${path.sep}package.json`) && (!aliasesOnly && !selectedEntries.has(index) || !/\.(?:js|mjs|d\.ts|d\.mts|d\.cts)$/.test(file))) return;
    const content = result.content;
    let text = typeof content === "string" ? content : Array.isArray(content) && content.length === 1 && content[0]?.type === "text" ? content[0].text : undefined;
    if (typeof text !== "string" || Buffer.byteLength(text) > MAX_SOURCE) return;
    const footer = /\n\[lines (\d+)-(\d+) of (\d+)(; byte limit reached)?\]$/.exec(text);
    if (result.toolName === "learning_read") {
      if (!footer || footer[1] !== "1" || footer[2] !== footer[3] || footer[4]) return;
      text = text.slice(0, footer.index);
      if (text.split("\n").length !== Number(footer[3])) return;
    } else if (text.split("\n").length >= (args.limit ?? 2000) || /\[(?:Showing|Output truncated|lines )/.test(text) || Buffer.byteLength(text) >= 50_000) return;
    const digest = createHash("sha256").update(text).digest("hex");
    const prior = out.find(source => source.file === file && source.digest === digest);
    if (prior) {if (!prior.aliases.includes(index)) prior.aliases.push(index);return;}
    if (aliasesOnly || out.length >= 32) return;
    try {
      const ast = file.endsWith("package.json") ? JSON.parse(text) : parse(text, {sourceType: "module", plugins: /\.d\.(?:ts|mts|cts)$/.test(file) ? [["typescript", {dts: true}]] : [], errorRecovery: false});
      out.push({index, aliases: [index], file, text, digest, ast});
    } catch { /* An unsupported or incomplete observation grants no relation. */ }
  });
  return out;
}

/** Equal text alone cannot alias an original supporting observation. Reuse the
 * complete, uniquely paired, root-scoped read grouping used by relation roles. */
export function observedMemorySourceAliases(snapshot: unknown, cwd: string, indices: readonly number[]): readonly (readonly number[])[] {
  if (indices.length > 16 || indices.some(index => !Number.isSafeInteger(index) || index < 0)) return [];
  return sources(snapshot, cwd, new Set(indices)).map(source => source.aliases);
}

// Original human topic matching stays sentence-local: separate glossary/topic
// mentions do not establish intent. A cited knowledge unit may span sentences.
function related(text: string, subject: string, member: string): boolean {
  return visible(text).split(/[!?。！？\n]+|\.(?=\s|$)/).some(sentence => mentions(sentence, subject) && mentions(sentence, member));
}

/** A bounded syntax relationship, not a claim that any source was executed.
 * Only a direct local callable, direct descriptor and unique direct return qualify. */
function implementationRoles(source: Source, factory: Node, wholeFactory: Node, member: string, cwd: string,
  alternatives: (value: Span) => Span[]): ImplementationRequirement | undefined {
  const body = factory.body?.body;
  if (!Array.isArray(body)) return;
  const returned = body.at(-1), owner = returned?.type === "ReturnStatement" ? identifier(returned.argument) : undefined;
  if (!owner || owner === "Object" || (factory.params ?? []).flatMap(names).some((name: string) => name === owner || name === "Object")) return;
  const declarations = body.flatMap((statement: Node, index: number) => statement.type === "VariableDeclaration"
    ? statement.declarations.filter((node: Node) => identifier(node.id) === owner).map((node: Node) => ({statement, node, index})) : []);
  if (declarations.length !== 1 || declarations[0].statement.kind !== "const"
    || !["ArrowFunctionExpression", "FunctionExpression"].includes(declarations[0].node.init?.type)) return;
  let invalid = false, ownerBindings = 0, returns = 0, descriptorCalls = 0;
  const root = (node: Node): string | undefined => node?.type === "MemberExpression"
    ? identifier(node.object) === "globalThis" && (identifier(node.property) ?? node.property?.value) === "Object" ? "Object" : root(node.object)
    : identifier(node);
  try {
    walk(source.ast, node => {
      if (bindings(node).includes("Object")) invalid = true;
      if (node.type === "AssignmentExpression" && root(node.left) === "Object"
        || node.type === "UpdateExpression" && root(node.argument) === "Object"
        || node.type === "UnaryExpression" && node.operator === "delete" && root(node.argument) === "Object"
        || ["ForInStatement", "ForOfStatement"].includes(node.type) && (root(node.left) === "Object" || names(node.left).includes("Object"))
        || node.type === "VariableDeclarator" && identifier(node.init) === "Object"
        || ["CallExpression", "OptionalCallExpression", "NewExpression"].includes(node.type)
          && node.arguments?.some((argument: Node) => identifier(argument) === "Object")) invalid = true;
    });
    walk(factory.body, node => {
      if (bindings(node).includes(owner)) ownerBindings++;
      if (node.type === "AssignmentExpression" && (root(node.left) === owner || names(node.left).includes(owner))
        || node.type === "UpdateExpression" && root(node.argument) === owner
        || node.type === "UnaryExpression" && node.operator === "delete" && root(node.argument) === owner
        || node.type === "VariableDeclarator" && identifier(node.init) === owner
        || ["ForInStatement", "ForOfStatement"].includes(node.type) && (root(node.left) === owner || names(node.left).includes(owner))) invalid = true;
      if (["CallExpression", "OptionalCallExpression", "NewExpression"].includes(node.type)
        && node.arguments?.some((argument: Node) => identifier(argument) === owner)) {
        if (node.type === "CallExpression" && node.callee?.type === "MemberExpression" && !node.callee.computed
          && identifier(node.callee.object) === "Object" && identifier(node.callee.property) === "defineProperties"
          && identifier(node.arguments[0]) === owner) descriptorCalls++;
        else invalid = true;
      }
      if (node.type === "CallExpression" && identifier(node.callee) === "eval") invalid = true;
    });
    walk(factory.body, node => {if (node.type === "ReturnStatement") returns++;}, true);
  } catch {return;}
  if (invalid || ownerBindings !== 1 || returns !== 1 || descriptorCalls !== 1) return;
  const definitions = body.flatMap((statement: Node, index: number) => {
    const call = statement.type === "ExpressionStatement" ? statement.expression : undefined;
    return call?.type === "CallExpression" && call.callee?.type === "MemberExpression" && !call.callee.computed
      && identifier(call.callee.object) === "Object" && identifier(call.callee.property) === "defineProperties"
      && identifier(call.arguments?.[0]) === owner ? [{call, index}] : [];
  });
  if (definitions.length !== 1 || definitions[0].index <= declarations[0].index) return;
  const {call} = definitions[0], descriptor = call.arguments?.[1];
  if (call.arguments.length !== 2 || descriptor?.type !== "ObjectExpression"
    || descriptor.properties.some((property: Node) => property.type !== "ObjectProperty" || property.computed)) return;
  const members = descriptor.properties.filter((property: Node) => (identifier(property.key) ?? property.key?.value) === member);
  if (members.length !== 1 || members[0].value?.type !== "ObjectExpression") return;
  const values = members[0].value.properties;
  if (values.some((property: Node) => !["ObjectProperty", "ObjectMethod"].includes(property.type) || property.computed
    || !["value", "writable", "enumerable", "configurable"].includes(identifier(property.key) ?? property.key?.value))
    || new Set(values.map((property: Node) => identifier(property.key) ?? property.key?.value)).size !== values.length
    || values.filter((property: Node) => (identifier(property.key) ?? property.key?.value) === "value").length !== 1) return;
  const value = values.find((property: Node) => (identifier(property.key) ?? property.key?.value) === "value");
  if (value.type === "ObjectMethod" ? value.kind !== "method"
    : !["ArrowFunctionExpression", "FunctionExpression"].includes(value.value?.type)) return;
  const heading = {...call, end: descriptor.start + 1, loc: {...call.loc, end: descriptor.loc.start}};
  const factoryHeading = {...wholeFactory, end: factory.body.start + 1, loc: {...wholeFactory.loc, end: factory.body.loc.start}};
  return {owner, file: path.relative(cwd, source.file).split(path.sep).join("/"), sourcePath: source.file, sourceSha256: source.digest,
    roles: [{role: "implementation-factory", alternatives: alternatives(span(source, factoryHeading))},
      {role: "implementation-owner-declaration", alternatives: alternatives(span(source, declarations[0].statement))},
      {role: "implementation-owner", alternatives: alternatives(span(source, heading))},
      {role: "implementation-member-definition", alternatives: alternatives(span(source, members[0]))},
      {role: "implementation-return", alternatives: alternatives(span(source, returned))}]};
}
function validateObligations(snapshot: unknown, knowledge: Node, obligations: MemoryRelationObligations): SelectedMemoryRelation[] {
  const digest = createHash("sha256").update(JSON.stringify(snapshot)).digest("hex");
  if (digest !== obligations.snapshotProjectionDigest) throw new MemoryRelationClosureError("Selected API relation snapshot projection changed", digest);
  const citations = knowledge.sourceCitations as any[];
  const used = new Set(knowledge.units.flatMap((u: any) => Array.isArray(u?.citationIndexes) ? u.citationIndexes : Number.isSafeInteger(u?.sourceCitationIndex) ? [u.sourceCitationIndex] : []));
  const complete: SelectedMemoryRelation[] = [], missing: unknown[] = [];
  for (const requirement of obligations.requirements) {
    // Preserve the original role witness when selected; equivalent alternatives
    // are fallbacks, independent of the model's catalog ordering.
    const match = (alternatives: Span[]) => alternatives.map(reference => ({...reference,
      index: citations.findIndex((citation, index) => used.has(index) && covers(citation, reference))})).find(value => value.index >= 0);
    const selectedRoles = requirement.roles.map(role => match(role.alternatives));
    const indexes = selectedRoles.map(value => value?.index ?? -1);
    const witness = requirement.initiatingWrapperWitness;
    const selectedWitness = witness ? match(witness.alternatives) : undefined;
    const witnessIndex = selectedWitness?.index ?? -1;
    const implementationSelections = requirement.implementation?.roles.map(role => match(role.alternatives)) ?? [];
    if (indexes.some(index => index < 0) || witness && witnessIndex < 0 || implementationSelections.some(value => !value)) missing.push({wrapper: requirement.wrapper,
      factory: requirement.factory, owner: requirement.owner, member: requirement.member,
      missingRoles: [...requirement.roles.flatMap((role, index) => indexes[index] < 0 ? [{role: role.role, ...publicSpan(role.alternatives[0])}] : []),
        ...(witness && witnessIndex < 0 ? [{role: "initiating-wrapper-declaration", ...publicSpan(witness.alternatives[0])}] : []),
        ...(requirement.implementation?.roles.flatMap((role, index) => !implementationSelections[index]
          ? [{role: role.role, ...publicSpan(role.alternatives[0])}] : []) ?? [])]});
    else {const {wrapper: _wrapper, roles: _roles, initiatingWrapperWitness: _witness, implementation, ...relation} = requirement;
      complete.push({...relation, indexes: [...indexes, ...(witness ? [witnessIndex] : [])],
        sourceSelections: [...selectedRoles.filter((value): value is NonNullable<typeof value> => value !== undefined),
          ...(selectedWitness ? [selectedWitness] : [])],
        ...(implementation ? {implementation: {owner: implementation.owner, file: implementation.file,
          sourcePath: implementation.sourcePath, sourceSha256: implementation.sourceSha256,
          indexes: implementationSelections.map(value => value!.index), sourceSelections: implementationSelections.map(value => value!)}} : {})});}
  }
  if (missing.length) {
    const text = `Selected API relation source roles are incomplete: ${JSON.stringify(missing)}. Snapshot projection digest: ${digest}. Explicitly select and use each supported role in the existing catalog; the parent will not add references.`;
    throw new MemoryRelationClosureError(Buffer.byteLength(text) <= 32_000 ? text : "Selected API relation source-role diagnostics exceed the unchanged 32KB metadata bound", digest, obligations);
  }
  return complete;
}

/** Source-derived obligations only for an already selected and explicitly named
 * wrapper/member topic. No source lookup, inferred runtime fact or added ref. */
export function selectedMemoryRelationClosures(snapshot: unknown, knowledge: unknown, cwd: string, obligations?: MemoryRelationObligations, capture?: (value: MemoryRelationObligations) => void): SelectedMemoryRelation[] {
  const catalog = object(knowledge), entries = object(snapshot)?.entries;
  if (!catalog || !Array.isArray(catalog.sourceCitations) || !Array.isArray(catalog.units) || !Array.isArray(entries)) return [];
  if (obligations) {capture?.(structuredClone(obligations));return validateObligations(snapshot, catalog, obligations);}
  const snapshotProjectionDigest = createHash("sha256").update(JSON.stringify(snapshot)).digest("hex");
  const failure = (text: string) => new MemoryRelationClosureError(text, snapshotProjectionDigest);
  const citations = catalog.sourceCitations as any[], prose = catalog.units.filter((u: any) => typeof u?.text === "string" && Array.isArray(u.citationIndexes));
  const used = new Set(catalog.units.flatMap((u: any) => Array.isArray(u?.citationIndexes) ? u.citationIndexes : Number.isSafeInteger(u?.sourceCitationIndex) ? [u.sourceCitationIndex] : []));
  const selectedEntries = new Set<number>(citations.flatMap((c, i) => used.has(i) && typeof c?.ref === "string"
    ? [Number(/^e(\d+)/.exec(c.ref)?.[1])] : []));
  const observed = sources(snapshot, cwd, selectedEntries);
  const alternatives = (required: Span): Span[] => {
    const index = Number(/^e(\d+)/.exec(required.ref)?.[1]);
    const source = observed.find(s => s.aliases.includes(index));
    return (source?.aliases ?? [index]).map(alias => ({ref: required.ref.replace(/^e\d+/, `e${alias}`),
      ...(required.endRef === undefined ? {} : {endRef: required.endRef.replace(/^e\d+/, `e${alias}`)}),
      ...(required.sourceSpan ? {sourceSpan: required.sourceSpan} : {})}));
  };
  const coversObserved = (citation: unknown, required: Span) => alternatives(required).some(ref => covers(citation, ref));
  const selected = (required: Span) => citations.findIndex((c, i) => used.has(i) && coversObserved(c, required));
  const users = entries.flatMap(e => {
    const m = message(e);
    if (m?.role !== "user") return [];
    const text = typeof m.content === "string" ? m.content : Array.isArray(m.content)
      ? m.content.filter((part: any) => part?.type === "text" && typeof part.text === "string").map((part: any) => part.text).join("\n") : "";
    return text ? [visible(text)] : [];
  });
  const requirementsFound: MemoryRelationRequirement[] = [], seen = new Set<string>();
  let inspectedRelations = 0;
  const packages = observed.filter(s => s.file.endsWith(`${path.sep}package.json`));
  for (const pkg of packages) {
    const map = pkg.ast.exports;
    if (pkg.ast.type !== "module" || !object(map) || Object.keys(map).sort().join(",") !== "default,types"
      || ![map.types, map.default].every(v => typeof v === "string" && v.startsWith("./") && !v.split("/").includes(".."))) continue;
    if (packages.some(other => other.file === pkg.file && other.text !== pkg.text)) continue;
    const dir = path.dirname(pkg.file), jsFile = path.resolve(dir, map.default), dtsFile = path.resolve(dir, map.types);
    if (!/\.(?:js|mjs)$/.test(jsFile) || !/\.d\.(?:ts|mts|cts)$/.test(dtsFile)) continue;
    for (const js of observed.filter(s => s.file === jsFile)) for (const dts of observed.filter(s => s.file === dtsFile)) {
      const functions = top(js.ast), types = top(dts.ast);
      if (functions.length + types.reduce((count, t) => count + 1 + (t.node.typeAnnotation?.members ?? t.node.body?.body ?? []).length, 0) > 128) continue;
      if (observed.some(s => (s.file === js.file && s.text !== js.text) || (s.file === dts.file && s.text !== dts.text))) continue;
      for (const wrapper of functions.filter(f => f.node.type === "FunctionDeclaration" && f.exported)) {
        const wrapperName = identifier(wrapper.node.id);
        if (!wrapperName || !users.some(u => mentions(u, wrapperName))) continue;
        const declarations = types.filter(t => t.node.type === "TSDeclareFunction" && identifier(t.node.id) === wrapperName && t.exported === wrapper.exported);
        if (declarations.length !== 1 || selected(span(dts, declarations[0].whole)) < 0) continue;
        const calls: Node[] = [];
        try {walk(wrapper.node.body, node => {if (node.type === "CallExpression" && identifier(node.callee)) calls.push(node);}, true);} catch {continue;}
        for (const call of calls) {
          const factoryName = identifier(call.callee)!;
          if (factoryName === wrapperName) continue;
          const callSpan = span(js, call);
          const contexts = prose.filter((u: any) => u.citationIndexes.some((i: any) => used.has(i) && coversObserved(citations[i], callSpan)));
          if (!contexts.length) continue;
          const factory = functions.filter(f => f.node.type === "FunctionDeclaration" && identifier(f.node.id) === factoryName);
          const topBindings = functions.flatMap(f => f.node.type === "VariableDeclaration" ? f.node.declarations.flatMap((n: Node) => bindings(n)) : f.node.type === "ImportDeclaration" ? f.node.specifiers.flatMap(bindings) : bindings(f.node));
          if (factory.length !== 1 || topBindings.filter(n => n === factoryName).length !== 1) continue;
          let shadow = false, dynamic = false;
          try {
            walk(wrapper.node, node => {if (bindings(node).includes(factoryName)) shadow = true;if (node.type === "CallExpression" && identifier(node.callee) === "eval") dynamic = true;});
            walk(js.ast.program, node => {
              if (node.type === "AssignmentExpression" && names(node.left).includes(factoryName)
                || node.type === "UpdateExpression" && names(node.argument).includes(factoryName)
                || ["ForInStatement", "ForOfStatement"].includes(node.type) && names(node.left).includes(factoryName)
                || node.type === "CallExpression" && identifier(node.callee) === "eval") dynamic = true;
            });
          } catch {continue;}
          if (shadow || dynamic || functions.some(f => ["ExportAllDeclaration"].includes(f.whole.type)
            || f.whole.specifiers?.some((s: Node) => [factoryName, wrapperName].includes(identifier(s.local) ?? "")))) continue;
          const factoryTypes = types.filter(t => t.node.type === "TSDeclareFunction" && identifier(t.node.id) === factoryName && t.exported === factory[0].exported);
          if (factoryTypes.length !== 1) continue;
          const f = factoryTypes[0], annotation = f.node.returnType?.typeAnnotation;
          const ownerName = annotation?.type === "TSTypeReference" ? identifier(annotation.typeName) : undefined;
          if (!ownerName || f.node.typeParameters?.params?.some((p: Node) => p.name === ownerName)) continue;
          const ownerNodes = types.filter(t => identifier(t.node.id) === ownerName || t.node.type === "ImportDeclaration" && t.node.specifiers.some((s: Node) => identifier(s.local) === ownerName));
          if (ownerNodes.length !== 1 || !["TSTypeAliasDeclaration", "TSInterfaceDeclaration"].includes(ownerNodes[0].node.type)) continue;
          const owner = ownerNodes[0], body = owner.node.type === "TSTypeAliasDeclaration" ? owner.node.typeAnnotation : owner.node.body;
          if (!["TSTypeLiteral", "TSInterfaceBody"].includes(body?.type)) continue;
          const members = (body.members ?? body.body) as Node[];
          for (const member of members) {
            const memberName = !member.computed && (identifier(member.key) ?? (member.key?.type === "StringLiteral" ? member.key.value : undefined));
            if (typeof memberName !== "string" || !/^[$_\p{ID_Start}][$_\u200c\u200d\p{ID_Continue}]*$/u.test(memberName) || members.filter(m => !m.computed && (identifier(m.key) ?? m.key?.value) === memberName).length !== 1
              || !users.some(u => related(u, wrapperName, memberName))
              || !contexts.some((u: any) => {const text = visible(u.text);return mentions(text, memberName) && (mentions(text, wrapperName) || mentions(text, factoryName));})) continue;
            const key = `${js.index}:${dts.index}:${wrapper.node.start}:${factoryName}:${ownerName}:${memberName}`;
            if (seen.has(key)) continue;seen.add(key);
            if (++inspectedRelations > 128) throw failure("Selected API relation inspection exceeds the unchanged 128-node syntax bound");
            const heading = {...owner.whole, end: body.start + 1, loc: {...owner.whole.loc, end: body.loc.start}};
            const requirements = {factory: span(dts, f.whole), owner: span(dts, heading), member: span(dts, member)};
            if (requirementsFound.some(row => `${row.sourcePath}:${row.wrapper}:${row.factory}:${row.member}` === `${dts.file}:${wrapperName}:${factoryName}:${memberName}`)) continue;
            const implementation = implementationRoles(js, factory[0].node, factory[0].whole, memberName, cwd, alternatives);
            requirementsFound.push({wrapper: wrapperName, factory: factoryName, owner: ownerName, member: memberName,
              file: path.relative(cwd, dts.file).split(path.sep).join("/"), sourcePath: dts.file, sourceSha256: dts.digest,
              ...(implementation ? {implementation} : {}),
              initiatingWrapperWitness: {alternatives: alternatives(span(dts, declarations[0].whole))},
              roles: Object.entries(requirements).map(([role, reference]) => ({role, alternatives: [...alternatives(reference),
                ...(role === "owner" && !f.node.typeParameters && !annotation.typeParameters && !owner.node.typeParameters && !owner.node.extends?.length && !member.typeParameters
                  ? alternatives(requirements.factory) : [])]}))});
            if (Buffer.byteLength(JSON.stringify(requirementsFound)) > 32_000) throw failure("Selected API relation requirements exceed the unchanged 32KB metadata bound");
          }
        }
      }
    }
  }
  const derived = {snapshotProjectionDigest, requirements: requirementsFound};
  capture?.(structuredClone(derived));
  return validateObligations(snapshot, catalog, derived);
}

/** Validate the three explicitly chosen file spans before existing materialization.
 * No omitted source is selected and no implementation/runtime relation is inferred. */
export function declaredMemoryRelation(snapshot: unknown, unit: unknown, cwd: string): {relation: SelectedMemoryRelation; refs: Span[]; obligations: MemoryRelationObligations} {
  const value = object(unit), fail = (): never => {throw new MemoryRelationClosureError("Declared API relation requires exact factory, named owner identity and direct member from one observed declaration file");};
  if (!value || Object.keys(value).sort().join(",") !== "factory,kind,member,owner" || value.kind !== "declared-api-relation") return fail();
  const refs = [value.factory, value.owner, value.member].map(value => {
    const ref = object(value);
    if (!ref || Object.keys(ref).some(key => !["ref", "endRef"].includes(key)) || typeof ref.ref !== "string"
      || !/^e\d+\.b0\.l[1-9]\d*$/.test(ref.ref) || ref.endRef !== undefined && (typeof ref.endRef !== "string"
        || !/^e\d+\.b0\.l[1-9]\d*$/.test(ref.endRef) || ref.endRef.split(".")[0] !== ref.ref.split(".")[0])) return fail();
    return ref as Span;
  });
  const indices = refs.map(ref => Number(/^e(\d+)/.exec(ref.ref)![1]));
  const observed = sources(snapshot, cwd, new Set(indices));
  const source = observed.find(source => /\.d\.(?:ts|mts|cts)$/.test(source.file) && indices.every(index => source.aliases.includes(index)));
  if (!source || observed.some(other => other.file === source.file && other.digest !== source.digest)) return fail();
  const canonical = (ref: Span): Span => ({ref: ref.ref.replace(/^e\d+/, `e${source.index}`), ...(ref.endRef ? {endRef: ref.endRef.replace(/^e\d+/, `e${source.index}`)} : {})});
  const exact = (ref: Span, node: Node) => {const expected = span(source, node), actual = canonical(ref);return actual.ref === expected.ref && (actual.endRef ?? actual.ref) === (expected.endRef ?? expected.ref);};
  const declarations = top(source.ast);
  if (declarations.reduce((count, row) => count + 1 + (row.node.typeAnnotation?.members ?? row.node.body?.body ?? []).length, 0) > 128) return fail();
  const factories = declarations.filter(row => row.node.type === "TSDeclareFunction" && exact(refs[0], row.whole));
  if (factories.length !== 1) return fail();
  const factory = factories[0].node, factoryName = identifier(factory.id), annotation = factory.returnType?.typeAnnotation;
  const ownerName = annotation?.type === "TSTypeReference" ? identifier(annotation.typeName) : undefined;
  if (!factoryName || !ownerName || factory.typeParameters?.params?.some((p: Node) => p.name === ownerName)
    || declarations.filter(row => identifier(row.node.id) === factoryName).length !== 1) return fail();
  const owners = declarations.filter(row => identifier(row.node.id) === ownerName);
  if (owners.length !== 1 || !["TSTypeAliasDeclaration", "TSInterfaceDeclaration"].includes(owners[0].node.type)) return fail();
  const owner = owners[0].node, body = owner.type === "TSTypeAliasDeclaration" ? owner.typeAnnotation : owner.body;
  if (!["TSTypeLiteral", "TSInterfaceBody"].includes(body?.type)) return fail();
  const heading = {...owners[0].whole, end: body.start + 1, loc: {...owners[0].whole.loc, end: body.loc.start}};
  const factoryOwnerWitness = exact(refs[1], factories[0].whole) && !factory.typeParameters && !annotation.typeParameters
    && !owner.typeParameters && !owner.extends?.length && !declarations.some(row => row.node.type === "ImportDeclaration"
      && row.node.specifiers.some((specifier: Node) => identifier(specifier.local) === ownerName));
  if (!exact(refs[1], heading) && !exact(refs[1], owners[0].whole) && !factoryOwnerWitness) return fail();
  const members = (body.members ?? body.body) as Node[], selected = members.filter(member => exact(refs[2], member));
  if (selected.length !== 1 || selected[0].computed
    || factoryOwnerWitness && !exact(refs[1], heading) && !exact(refs[1], owners[0].whole) && selected[0].typeParameters) return fail();
  const memberName = identifier(selected[0].key) ?? (selected[0].key?.type === "StringLiteral" ? selected[0].key.value : undefined);
  if (typeof memberName !== "string" || !/^[$_\p{ID_Start}][$_\u200c\u200d\p{ID_Continue}]*$/u.test(memberName) || members.filter(member => !member.computed && (identifier(member.key) ?? member.key?.value) === memberName).length !== 1) return fail();
  const relation = {factory: factoryName, owner: ownerName, member: memberName, file: path.relative(cwd, source.file).split(path.sep).join("/"),
    sourcePath: source.file, sourceSha256: source.digest, indexes: []};
  const alternatives = (node: Node) => source.aliases.map(alias => {
    const reference = span(source, node);
    return {ref: reference.ref.replace(/^e\d+/, `e${alias}`),
      ...(reference.endRef ? {endRef: reference.endRef.replace(/^e\d+/, `e${alias}`)} : {}),
      ...(reference.sourceSpan ? {sourceSpan: reference.sourceSpan} : {})};
  });
  const ownerFactoryAlternative = !factory.typeParameters && !annotation.typeParameters && !owner.typeParameters
    && !owner.extends?.length && !selected[0].typeParameters && !declarations.some(row => row.node.type === "ImportDeclaration"
      && row.node.specifiers.some((specifier: Node) => identifier(specifier.local) === ownerName));
  const {indexes: _indexes, ...proof} = relation;
  return {refs, relation, obligations: {snapshotProjectionDigest: createHash("sha256").update(JSON.stringify(snapshot)).digest("hex"),
    requirements: [{...proof, roles: [{role: "factory", alternatives: alternatives(factories[0].whole)},
      {role: "owner", alternatives: [...alternatives(heading), ...(ownerFactoryAlternative ? alternatives(factories[0].whole) : [])]},
      {role: "member", alternatives: alternatives(selected[0])}]}]}};
}

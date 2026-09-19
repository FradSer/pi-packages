// One canonical widget row language: identity from pi-kit's per-name accent
// palette, and exactly two activity formats (plain, markdown) with one
// implementation each. Rendered with a real-ANSI theme so width math is exact.
import assert from "node:assert/strict";
import { stripVTControlCharacters } from "node:util";
import { truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import {
  agentColor,
  createLiveActivityWidget,
  renderLiveActivityIdentity,
  renderLiveActivityMarkdown,
  type PiLiveActivity,
  type PiLiveActivityTextFormat,
  type PiLiveWidgetComponent,
  type PiLiveWidgetUi,
} from "../src/index.ts";

const CODES: Record<string, string> = {
  muted: "2",
  mdCode: "36",
  mdHeading: "35",
  mdLink: "34",
  mdLinkUrl: "90",
  mdQuote: "33",
  mdListBullet: "31",
  mdHr: "32",
  mdCodeBlock: "36",
  mdCodeBlockBorder: "90",
  mdQuoteBorder: "90",
  accent: "94",
  borderAccent: "95",
};

const SGR = (code: string) => `\u001b[${code}m`;
const theme = {
  fg: (color: string, text: string) => `${SGR(CODES[color] ?? "0")}${text}${SGR("39")}`,
  bold: (text: string) => `${SGR("1")}${text}${SGR("22")}`,
  italic: (text: string) => `${SGR("3")}${text}${SGR("23")}`,
  underline: (text: string) => `${SGR("4")}${text}${SGR("24")}`,
  strikethrough: (text: string) => `${SGR("9")}${text}${SGR("29")}`,
};

let mounted: PiLiveWidgetComponent | undefined;
const ui: PiLiveWidgetUi = {
  setWidget(_key, factory) {
    mounted = factory ? factory({ requestRender() {} }, theme) : undefined;
  },
};

function row(entry: PiLiveActivity, options: { activityFormat?: PiLiveActivityTextFormat } = {}, width = 200): string {
  const widget = createLiveActivityWidget({
    key: "probe",
    fit: truncateToWidth,
    activityFormat: options.activityFormat,
  });
  widget.update({ mode: "tui", ui }, [entry]);
  assert.ok(mounted, "a live entry must mount the widget");
  const lines = mounted!.render(width);
  assert.equal(lines.length, 1, lines.join("\n"));
  assert.equal(visibleWidth(lines[0]), Math.min(width, visibleWidth(lines[0])));
  assert.ok(visibleWidth(lines[0]) <= width, lines[0]);
  return lines[0];
}

// Identity: one canonical, bold, stable per-name accent shared with @name segments.
const identity = renderLiveActivityIdentity("researcher", theme);
assert.equal(identity, theme.fg(agentColor("researcher"), theme.bold("researcher")));
assert.ok(identity.startsWith(SGR(CODES[agentColor("researcher")]) + SGR("1")), identity);
assert.equal(renderLiveActivityIdentity("researcher", theme), identity, "identity must be stable per name");

// Plain activity: muted, literal, width-bounded, no markdown processing.
const plain = row({ id: "a", identity: "researcher", activity: "**Scanning** `rg` output" });
assert.ok(plain.startsWith(` ${theme.fg("warning", "⠋")} `), plain);
assert.ok(plain.includes(identity), plain);
assert.ok(plain.includes(theme.fg("muted", "**Scanning** `rg` output")), plain);
assert.ok(!plain.includes(SGR("36")), plain);

// Markdown activity: native markdown element colors, literal markup gone, one line.
const markdown = row({ id: "a", identity: "researcher", activity: "**Scanning** `rg` output" }, { activityFormat: "markdown" });
const markdownPlain = stripVTControlCharacters(markdown);
assert.ok(markdown.includes(identity), markdown);
assert.ok(markdown.includes(theme.fg("mdCode", "rg")), markdown);
assert.ok(markdownPlain.includes("Scanning rg output"), markdownPlain);
assert.ok(!markdownPlain.includes("**") && !markdownPlain.includes("`"), markdownPlain);
assert.ok(markdownPlain.includes(" · "), markdownPlain);

// Markdown stands alone as the shared renderer for console rows too.
assert.equal(
  stripVTControlCharacters(renderLiveActivityMarkdown("## Heading\nSee [ref](https://example.com)", theme)),
  "Heading See ref",
);
assert.equal(renderLiveActivityMarkdown("\u001b[2Jwiped  \n", theme).includes("\u001b[2J"), false);

// A streamed fence carries no content: the fence line is dropped, the body stays.
assert.equal(stripVTControlCharacters(renderLiveActivityMarkdown("```js\nconst a = 1\n```", theme)), "const a = 1");
assert.equal(renderLiveActivityMarkdown("```js", theme), "");
assert.equal(stripVTControlCharacters(row({ id: "a", identity: "researcher", activity: "```js" }, { activityFormat: "markdown" }, 60)).trimEnd(), " ⠋ researcher");

// A fence nested in a quote or list marker is still a fence.
assert.equal(stripVTControlCharacters(renderLiveActivityMarkdown("> ```bash\n> npm test", theme)), "│ npm test");
assert.equal(stripVTControlCharacters(renderLiveActivityMarkdown("- ```bash\n- npm test", theme)), "- npm test");

// Explicit contract: a fragment that is still arriving mid-inline-markup keeps
// that fragment literally until the next activity replaces it. Only a fence
// line, which carries no content, is removed.
assert.equal(stripVTControlCharacters(renderLiveActivityMarkdown("**bold", theme)), "**bold");

// An activity with no visible width leaves an identity-only row in both formats.
for (const format of ["plain", "markdown"] as const) {
  assert.equal(stripVTControlCharacters(row({ id: "a", identity: "researcher", activity: "\u200b" }, { activityFormat: format }, 60)).trimEnd(), " ⠋ researcher");
}

// The row language is the row's, not the caller's: a consumer cannot restyle a
// row by handing kit a pre-styled or line-broken activity string.
for (const format of ["plain", "markdown"] as const) {
  const styled = row({ id: "a", identity: "researcher", activity: "\u001b[31mRED\u001b[39m code" }, { activityFormat: format });
  assert.ok(!styled.includes("\u001b[31m"), styled);
  const broken = row({ id: "a", identity: "researcher", activity: "safe\rOVERWRITE\u2028next" }, { activityFormat: format });
  assert.ok(!broken.includes("\r") && !broken.includes("\u2028"), JSON.stringify(broken));
  assert.ok(stripVTControlCharacters(broken).includes("safe OVERWRITE next"), broken);
}

// The row identity is the shared per-name accent for any name, not a fixed
// accent: a name that hashes elsewhere keeps its own color.
const otherIdentity = row({ id: "a", identity: "reviewer", activity: "checking" });
assert.equal(agentColor("reviewer"), "mdLink");
assert.ok(otherIdentity.includes(theme.fg("mdLink", theme.bold("reviewer"))), otherIdentity);
assert.ok(!otherIdentity.includes(renderLiveActivityIdentity("researcher", theme)), otherIdentity);

// The identity prefix keeps the accent keyed to the bare name, so a console
// `@name` row matches the widget row and report rows.
assert.equal(
  renderLiveActivityIdentity("reviewer", theme, "@"),
  theme.fg(agentColor("reviewer"), theme.bold("@reviewer")),
);
assert.notEqual(renderLiveActivityIdentity("reviewer", theme, "@"), renderLiveActivityIdentity("@reviewer", theme));

// Hostile and wide input stays one sanitized, width-bounded row.
const long = row(
  { id: "a", identity: "researcher", activity: "**中文** 中文 activity ".repeat(20) },
  { activityFormat: "markdown" },
  40,
);
assert.ok(visibleWidth(long) <= 40, long);
assert.ok(!long.includes("\u001b[2J"), long);

// An empty activity after sanitization leaves the identity-only row intact.
const identityOnly = row({ id: "a", identity: "researcher", activity: "\u001b[2J" }, { activityFormat: "markdown" }, 40);
assert.equal(stripVTControlCharacters(identityOnly).trimEnd(), ` ⠋ researcher`);

console.log("KIT_ACTIVITY_ROW_OK");
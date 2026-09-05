#!/usr/bin/env node
// Modified for @fradser/pi-impeccable: explicit local static detection only.
// Derived from Impeccable, Copyright 2025 Paul Bakaus; Apache-2.0.
import fs from 'node:fs';
import path from 'node:path';
import { detectHtml } from './detector/engines/static-html/detect-html.mjs';
import { detectText } from './detector/engines/regex/detect-text.mjs';

const PRIMARY_RULES = new Set(['low-contrast', 'skipped-heading']);
const EXTENSIONS = new Set(['.html', '.htm', '.css', '.scss', '.sass', '.less', '.jsx', '.tsx', '.vue', '.svelte', '.astro']);

function targets(args) {
  const values = args.filter(arg => arg !== '--json');
  if (!values.length || values.some(arg => arg.startsWith('-') || /^[a-z][a-z0-9+.-]*:/i.test(arg))) {
    throw new Error('Provide explicit local file targets: detect.mjs --json <file>. URL, directory discovery, and browser modes are unavailable.');
  }
  return values.map(value => {
    const target = path.resolve(value);
    if (!fs.existsSync(target) || !fs.statSync(target).isFile() || !EXTENSIONS.has(path.extname(target).toLowerCase())) {
      throw new Error(`Unsupported local target: ${value}. Provide an existing HTML, CSS, or component source file.`);
    }
    return target;
  });
}

async function main() {
  const files = targets(process.argv.slice(2));
  const findings = [];
  for (const file of files) {
    const detected = /\.html?$/i.test(file)
      ? await detectHtml(file)
      : detectText(fs.readFileSync(file, 'utf8'), file);
    findings.push(...detected.map(finding => PRIMARY_RULES.has(finding.antipattern)
      ? finding
      : { ...finding, advisory: true }));
  }
  console.log(JSON.stringify(findings, null, 2));
  process.exitCode = findings.some(finding => !finding.advisory) ? 2 : 0;
}

try { await main(); } catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}

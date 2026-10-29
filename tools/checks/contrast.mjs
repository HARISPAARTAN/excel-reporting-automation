// WCAG 2.x contrast of the colours this repository shows: the vendored kit tokens (web/kit/tokens.css, dark and
// light) used by the Pages page, and the workbook palette (src/buildreport/workbook/styles.py) of the report.
// Every pair is text on its background and must reach 4.5:1. Usage: node tools/checks/contrast.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const css = fs.readFileSync(path.join(ROOT, 'web', 'kit', 'tokens.css'), 'utf8');
const styles = fs.readFileSync(path.join(ROOT, 'src', 'buildreport', 'workbook', 'styles.py'), 'utf8');
const FLOOR = 4.5;

function block(pattern, name) {
  const match = pattern.exec(css);
  if (!match) throw new Error(`web/kit/tokens.css has no ${name} block`);
  const start = match.index + match[0].length;
  const vars = {};
  for (const m of css.slice(start, css.indexOf('}', start)).matchAll(/--([\w-]+)\s*:\s*#([0-9a-fA-F]{6})\b/g)) {
    vars[m[1]] = m[2].toUpperCase();
  }
  return vars;
}

const dark = block(/:root\s*\{/, ':root');
const light = { ...dark, ...block(/:root\[data-theme="light"\]\s*\{/, ':root[data-theme="light"]') };
const palette = {};
for (const m of styles.matchAll(/^([A-Z_]+) = "([0-9A-Fa-f]{6})"\r?$/gm)) palette[m[1]] = m[2].toUpperCase();

function luminance(hex) {
  const [r, g, b] = [0, 2, 4]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const PAGE = [
  ['text', 'bg'], ['text', 'surface'], ['text', 'surface-2'],
  ['muted', 'bg'], ['muted', 'surface'], ['muted', 'surface-2'],
  ['accent', 'bg'], ['accent', 'surface'], ['accent-fg', 'accent'],
  ['ok', 'surface'], ['warn', 'surface'], ['danger', 'surface'],
];
const WORKBOOK = [
  ['header', 'FFFFFF', 'HEADER_FILL'],
  ['title', 'TITLE_COLOUR', 'FFFFFF'],
  ['notes', 'NOTE_COLOUR', 'FFFFFF'],
  ['bad', 'BAD_TEXT', 'BAD_FILL'],
  ['warn', 'WARN_TEXT', 'WARN_FILL'],
  ['positive', 'POSITIVE', 'FFFFFF'],
  ['negative', 'NEGATIVE', 'FFFFFF'],
  ['scale max', '000000', 'ACCENT'],
];

const rows = [];
for (const [theme, tokens] of [['dark', dark], ['light', light]]) {
  for (const [fg, bg] of PAGE) rows.push([theme, `${fg} on ${bg}`, tokens[fg], tokens[bg]]);
}
const colour = (ref) => (/^[0-9A-F]{6}$/.test(ref) ? ref : palette[ref]);
for (const [name, fg, bg] of WORKBOOK) rows.push(['workbook', name, colour(fg), colour(bg)]);

let bad = 0;
for (const [group, name, fg, bg] of rows) {
  if (!fg || !bg) {
    bad += 1;
    console.log(`FAIL ${group.padEnd(8)} ${name.padEnd(20)} colour missing`);
    continue;
  }
  const r = ratio(fg, bg);
  if (r < FLOOR) bad += 1;
  console.log(`${r >= FLOOR ? 'ok  ' : 'FAIL'} ${group.padEnd(8)} ${name.padEnd(20)} #${fg} on #${bg}  ${r.toFixed(2)}:1`);
}
console.log(bad ? `\n${bad} of ${rows.length} pairs below ${FLOOR}:1` : `\nALL ${rows.length} PAIRS PASS (at least ${FLOOR}:1)`);
process.exit(bad ? 1 : 0);

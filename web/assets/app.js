// Demo page of excel-reporting-automation. Reads latest/manifest.json, which the weekly GitHub Actions run
// commits next to the workbook, and shows the latest run, the key figures, the ranking, the findings and the
// sheet previews. The page keeps nothing in storage, so it needs no reset button.
import { fmt, initTabs, mountBanner, mountThemeToggle, pill, renderKpi, renderTable } from '../kit/kit.js';

const REPO_URL = 'https://github.com/HARISPAARTAN/excel-reporting-automation';
const MANIFEST_URL = 'latest/manifest.json';
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const OP_WORDS = { '>': 'above', '>=': 'at or above', '<': 'below', '<=': 'at or below' };
const SHEETS = [
  ['summary', (p) => `Summary sheet of the ${p} report: the seven key figures with last week and the change, the branch ranking, the data notes and three charts (revenue by branch, chain revenue over the last eight weeks, revenue mix by product group).`],
  ['branches', (p) => `Branches sheet of the ${p} report: one row per branch with revenue, change, transactions, average basket, waste, labour and rank, a total row, and the weekly totals of the last eight weeks.`],
  ['products', (p) => `Products sheet of the ${p} report: revenue, share, change, units sold and waste per product group with a total row, and the revenue mix of every branch by product group as a colour scale.`],
  ['data', (p) => `Data sheet of the ${p} report: the first 40 rows of the Excel table tblWeekly with week, week start, branch code and name, category, measure, value and source file.`],
  ['run-info', (p) => `Run info sheet of the ${p} report: period, timestamp, tool and library versions, the configuration hash, the input files with status and SHA-256, and the findings.`],
];

const $ = (id) => document.getElementById(id);

function el(tag, { className, text } = {}, ...children) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  node.append(...children);
  return node;
}

const hidden = (text) => el('span', { className: 'pf-visually-hidden', text });
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const arrow = (change) => (change > 0 ? '▲' : change < 0 ? '▼' : '●');

function formatRange(start, end) {
  const [y1, m1, d1] = start.split('-').map(Number);
  const [y2, m2, d2] = end.split('-').map(Number);
  if (y1 !== y2) return `${d1} ${MONTHS[m1 - 1]} ${y1} to ${d2} ${MONTHS[m2 - 1]} ${y2}`;
  if (m1 !== m2) return `${d1} ${MONTHS[m1 - 1]} to ${d2} ${MONTHS[m2 - 1]} ${y2}`;
  return `${d1} to ${d2} ${MONTHS[m2 - 1]} ${y2}`;
}

function figure(format, value) {
  if (format === 'eur') return fmt.money(value);
  if (format === 'eur2') return fmt.money(value, 'EUR', 2);
  if (format === 'count') return fmt.int(value);
  if (format === 'hours') return fmt.dec(value, 1);
  if (format === 'pct1') return fmt.pct(value, 1);
  return fmt.dec(value, 2);
}

// Changes are shown with one decimal. The sign, the arrow and the colour follow the rounded figure (half away from
// zero, as Intl rounds), so a change that reads 0.0 is neutral.
function tenths(change, type) {
  const steps = (type === 'points' ? change : change * 100) * 10;
  return Math.sign(steps) * Math.round(Math.abs(steps));
}

function relative(change) {
  const steps = tenths(change, 'relative');
  return steps > 0 ? `+${fmt.pct(change)}` : fmt.pct(steps === 0 ? 0 : change);
}

function changeOf(kpi) {
  if (kpi.change === null || kpi.change === undefined) return null;
  return kpi.change_type === 'points' ? fmt.pp(kpi.change / 100) : relative(kpi.change);
}

function tone(kpi) {
  const steps = tenths(kpi.change, kpi.change_type);
  if (!steps || kpi.better === 'neutral') return 'muted';
  return (steps > 0) === (kpi.better === 'higher') ? 'ok' : 'danger';
}

function renderLinks(manifest) {
  const output = (suffix) => manifest.outputs.find((item) => item.file.endsWith(suffix));
  for (const [id, suffix] of [['link-xlsx', '.xlsx'], ['link-eml', '.eml']]) {
    const item = output(suffix);
    if (item) {
      $(id).href = `latest/${encodeURIComponent(item.file)}`;
      $(id).hidden = false;
    }
  }
  $('link-pdf').hidden = false;
}

function renderFacts(manifest) {
  const weeks = manifest.branches_reporting;
  const now = weeks.find((item) => item.week === manifest.period);
  const before = weeks.length > 1 ? weeks[weeks.length - 2] : null;
  const counts = { error: 0, warning: 0 };
  for (const item of manifest.findings) counts[item.severity] += 1;
  $('fact-period').textContent = `${manifest.period} · ${formatRange(manifest.period_start, manifest.period_end)}`;
  $('fact-generated').textContent = `${fmt.dateTime(manifest.generated_at)} UTC`;
  $('fact-tool').textContent = `${manifest.tool.name} ${manifest.tool.version}`;
  $('fact-branches').textContent = now
    ? `${now.reporting} reported, ${now.expected} expected${before ? ` (week before: ${before.reporting})` : ''}`
    : '–';
  $('fact-findings').replaceChildren(
    pill(plural(counts.error, 'error'), counts.error ? 'danger' : 'muted'),
    ' ',
    pill(plural(counts.warning, 'warning'), counts.warning ? 'warn' : 'muted'),
  );
  const run = manifest.ci?.run_url;
  if (typeof run === 'string' && run.startsWith(`${REPO_URL}/actions/runs/`)) {
    const link = el('a', { text: 'GitHub Actions run' });
    link.href = run;
    $('fact-run').replaceChildren(link);
  } else {
    $('fact-run').textContent = 'built outside GitHub Actions';
  }
}

function renderKpis(manifest) {
  const grid = $('kpis');
  grid.replaceChildren();
  for (const [key, kpi] of Object.entries(manifest.kpis)) {
    const cell = el('div');
    cell.dataset.kpi = key;
    grid.append(cell);
    renderKpi(cell, {
      label: kpi.label,
      value: figure(kpi.format, kpi.value),
      caption: `Last week ${figure(kpi.format, kpi.previous)}`,
    });
    const text = changeOf(kpi);
    const kind = text === null ? 'muted' : tone(kpi);
    const badge = pill(text === null ? 'no comparison' : '', kind);
    if (text !== null) {
      const mark = el('span', { text: `${arrow(tenths(kpi.change, kpi.change_type))} ` });
      mark.setAttribute('aria-hidden', 'true');
      badge.append(mark, `${text} week on week`);
      if (kind !== 'muted') badge.append(hidden(kind === 'ok' ? ', favourable' : ', unfavourable'));
    }
    const tile = cell.querySelector('.pf-kpi');
    tile.insertBefore(el('div', { className: 'ra-change' }, badge), tile.querySelector('.pf-kpi__caption'));
  }
}

function flagged(hits, metric, row) {
  const value = row[metric];
  const hit = hits.get(metric);
  if (!hit || !hit.branches.includes(row.code)) return fmt.pct(value);
  const badge = pill('', hit.style === 'bad' ? 'danger' : 'warn');
  badge.append(fmt.pct(value), hidden(`, ${OP_WORDS[hit.op] ?? hit.op} the threshold of ${fmt.pct(hit.value)}`));
  return badge;
}

function renderRanking(manifest) {
  const hits = new Map(manifest.above_threshold.map((hit) => [hit.metric, hit]));
  const rules = manifest.above_threshold.map(
    (hit) => `${hit.label} ${OP_WORDS[hit.op] ?? hit.op} ${fmt.pct(hit.value)} (${hit.style === 'bad' ? 'red' : 'amber'})`,
  );
  $('ranking-note').textContent = `Ranked by revenue; branches without a return come last. Highlighted: ${rules.join('; ') || 'nothing'}.`;
  renderTable($('ranking'), {
    caption: `Branch ranking, ${manifest.period}`,
    columns: [
      { key: 'rank', label: 'Rank', align: 'right', format: (v) => (v === null ? '–' : String(v)) },
      { key: 'name', label: 'Branch', format: (v, row) => `${row.code} ${v}` },
      { key: 'revenue', label: 'Revenue', align: 'right', format: (v) => fmt.money(v) },
      { key: 'change', label: 'WoW', align: 'right', format: (v) => relative(v) },
      { key: 'waste_pct', label: 'Waste %', align: 'right', format: (v, row) => flagged(hits, 'waste_pct', row) },
      { key: 'labour_pct', label: 'Labour %', align: 'right', format: (v, row) => flagged(hits, 'labour_pct', row) },
    ],
    rows: manifest.ranking,
  });
}

function renderFindings(manifest) {
  renderTable($('findings'), {
    caption: `Findings of the ${manifest.period} run`,
    columns: [
      { key: 'severity', label: 'Severity', format: (v) => pill(v, v === 'error' ? 'danger' : 'warn') },
      { key: 'code', label: 'Code', format: (v) => el('code', { text: v }) },
      { key: 'file', label: 'File', format: (v) => v || '–' },
      { key: 'message', label: 'Message', sortable: false },
    ],
    rows: manifest.findings,
    emptyText: 'No findings: every file matched the template.',
  });
}

function renderPreviews(manifest) {
  for (const [sheet, alt] of SHEETS) {
    const img = document.querySelector(`img[data-sheet="${sheet}"]`);
    img.alt = alt(manifest.period);
    img.decoding = 'async';
    img.addEventListener(
      'error',
      () => {
        img.replaceWith(
          el(
            'div',
            { className: 'pf-empty' },
            el('strong', { text: 'Preview not available' }),
            el('span', { text: 'The previews are rendered when the site is deployed. The workbook and the preview PDF are linked at the top.' }),
          ),
        );
      },
      { once: true },
    );
    img.src = `latest/preview/${sheet}.png`;
  }
  initTabs($('sheet-tabs'));
}

async function loadManifest() {
  let response;
  try {
    response = await fetch(MANIFEST_URL, { cache: 'no-store' });
  } catch {
    return { state: 'error', reason: 'the site could not be reached' };
  }
  if (response.status === 404) return { state: 'empty' };
  if (!response.ok) return { state: 'error', reason: `the server answered ${response.status}` };
  try {
    const manifest = await response.json();
    if (manifest.schema !== 1 || manifest.status !== 'built') return { state: 'error', reason: 'the manifest is not a built report' };
    return { state: 'filled', manifest };
  } catch {
    return { state: 'error', reason: 'the manifest is not valid JSON' };
  }
}

async function start() {
  mountBanner({ repoUrl: REPO_URL });
  mountThemeToggle($('theme'));
  const result = await loadManifest();
  if (result.state === 'filled') {
    const manifest = result.manifest;
    renderLinks(manifest);
    renderFacts(manifest);
    renderKpis(manifest);
    renderRanking(manifest);
    renderFindings(manifest);
    renderPreviews(manifest);
    $('run-card').hidden = false;
    for (const section of document.querySelectorAll('[data-needs-run]')) section.hidden = false;
  } else {
    if (result.state === 'error') {
      $('empty-title').textContent = 'The latest run could not be loaded';
      $('empty-text').textContent = `Reason: ${result.reason}. The commands under Run it locally build the same report on your own machine.`;
    }
    $('empty').hidden = false;
  }
  $('main').dataset.state = result.state;
}

start();

// Checks the Pages page in Chrome (umbrella section 12) at 1440 and 390 px, in the dark and the light theme:
// no page errors, no console errors, no failed or external requests and no HTTP errors (except under the
// ALLOW_404 path prefixes), the demo banner on the first screen, the theme applied, no horizontal scrolling,
// every font loaded, the footer line, keyboard focus reaching the theme toggle (and the Summary tab); then the
// content: EXPECT=filled (seven KPI tiles, twelve ranking rows, findings, five preview tabs that follow the arrow
// keys) or EXPECT=empty ("No weekly run yet"). Full-page and first-screen screenshots go to OUT, which must lie
// outside the repository.
//
//   OUT=<scratch>/page LATEST=build/site-latest ALLOW_404=latest/preview/ node tools/checks/verify_page.mjs
//   OUT=<scratch>/page-empty EXPECT=empty ALLOW_404=latest/ node tools/checks/verify_page.mjs
//   OUT=<scratch>/live BASE_URL=https://harispaartan.github.io/excel-reporting-automation/ node tools/checks/verify_page.mjs
//
// LATEST serves another folder (a local publish_latest.py copy) as latest/. PLAYWRIGHT_FROM names a package.json
// whose node_modules holds playwright; createRequire only reads it, nothing in that folder is run or changed.
// Without it, playwright is resolved from this repository (as in a CI job that installs it).
import { createRequire } from 'node:module';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(process.env.PLAYWRIGHT_FROM || import.meta.url);
const { chromium } = require('playwright');

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const WEB = path.join(REPO, 'web');
const OUT = process.env.OUT ? path.resolve(process.env.OUT) : '';
const EXPECT = process.env.EXPECT || 'filled';
const LATEST = process.env.LATEST ? path.resolve(REPO, process.env.LATEST) : null;
const ALLOW_404 = (process.env.ALLOW_404 || '').split(',').map((s) => s.trim()).filter(Boolean);
const LIVE = process.env.BASE_URL || '';
const FOOTER = "Rebuilt from memory as a demo. The original client's name and data are not used.";
const BG = { dark: 'rgb(11, 15, 20)', light: 'rgb(247, 247, 244)' };
const VIEWPORTS = [{ width: 1440, height: 900 }, { width: 390, height: 844 }];
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2',
  '.pdf': 'application/pdf', '.md': 'text/plain; charset=utf-8', '.eml': 'message/rfc822',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
};

const inside = (root, file) => {
  const rel = path.relative(root, file);
  return rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel));
};
if (!OUT || inside(REPO, OUT)) {
  console.error('set OUT to a folder outside the repository, such as the session scratchpad');
  process.exit(2);
}
if (!['filled', 'empty'].includes(EXPECT)) {
  console.error('EXPECT must be filled or empty');
  process.exit(2);
}

function fileFor(urlPath) {
  let p = decodeURIComponent(urlPath);
  if (p.endsWith('/')) p += 'index.html';
  const [root, rest] = LATEST && p.startsWith('/latest/') ? [LATEST, p.slice('/latest/'.length)] : [WEB, p.slice(1)];
  const file = path.resolve(root, rest);
  return inside(root, file) && fs.existsSync(file) && fs.statSync(file).isFile() ? file : null;
}

async function serve() {
  const server = http.createServer((req, res) => {
    const file = fileFor(new URL(req.url, 'http://127.0.0.1').pathname);
    if (!file) {
      res.writeHead(404, { 'content-type': 'text/plain' });
      res.end('not found');
      return;
    }
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream', 'cache-control': 'no-store' });
    fs.createReadStream(file).pipe(res);
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, base: `http://127.0.0.1:${server.address().port}/` };
}

async function reachedByTab(page) {
  const reached = new Set();
  for (let i = 0; i < 80; i += 1) {
    await page.keyboard.press('Tab');
    reached.add(await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return '';
      return el.classList.contains('pf-theme-toggle') ? 'theme-toggle' : el.id || el.tagName.toLowerCase();
    }));
  }
  return reached;
}

async function checkTabs(page) {
  await page.focus('#tab-summary');
  await page.keyboard.press('ArrowRight');
  const state = await page.evaluate(() => ({
    selected: document.querySelector('#sheet-tabs [aria-selected="true"]')?.id,
    focused: document.activeElement?.id,
    shown: !document.getElementById('panel-branches').hidden,
    hiddenSummary: document.getElementById('panel-summary').hidden,
  }));
  await page.keyboard.press('Home');
  const ok = state.selected === 'tab-branches' && state.focused === 'tab-branches' && state.shown && state.hiddenSummary;
  return ok ? [] : [`ArrowRight on the Summary tab gave ${JSON.stringify(state)}`];
}

const { server, base } = LIVE ? { server: null, base: LIVE.endsWith('/') ? LIVE : `${LIVE}/` } : await serve();
const host = new URL(base).host;
const allowed = (url) => {
  const u = new URL(url);
  return u.host === host && ALLOW_404.some((prefix) => u.pathname.startsWith(new URL(prefix, base).pathname));
};
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
let failures = 0;
for (const viewport of VIEWPORTS) {
  for (const theme of ['dark', 'light']) {
    const name = `${EXPECT}-${viewport.width}-${theme}`;
    const context = await browser.newContext({ viewport, colorScheme: theme });
    await context.addInitScript((value) => {
      try { localStorage.setItem('hh-theme', value); } catch { /* storage blocked: the OS scheme decides */ }
    }, theme);
    const page = await context.newPage();
    const problems = [];
    let done = false;
    page.on('pageerror', (e) => problems.push(`page error: ${e.message}`));
    page.on('console', (msg) => {
      if (done || msg.type() !== 'error') return;
      const where = msg.location().url || '';
      if (msg.text().startsWith('Failed to load resource') && where && allowed(where)) return;
      problems.push(`console error: ${msg.text()} ${where}`.trim());
    });
    page.on('request', (req) => {
      const u = new URL(req.url());
      if (u.protocol.startsWith('http') && u.host !== host) problems.push(`external request: ${req.url()}`);
    });
    page.on('requestfailed', (req) => { if (!done) problems.push(`failed request: ${req.url()} ${req.failure()?.errorText ?? ''}`); });
    page.on('response', (res) => { if (res.status() >= 400 && !allowed(res.url())) problems.push(`HTTP ${res.status()}: ${res.url()}`); });

    await page.goto(base, { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForSelector('main[data-state]:not([data-state="loading"])', { timeout: 15000 });
    await page.evaluate(() => document.fonts.ready);
    const info = await page.evaluate(() => {
      const banner = document.querySelector('.pf-banner')?.getBoundingClientRect();
      const empty = document.getElementById('empty');
      return {
        title: document.title,
        theme: document.documentElement.getAttribute('data-theme'),
        bg: getComputedStyle(document.body).backgroundColor,
        banner: Boolean(banner && banner.width > 0 && banner.height > 0 && banner.top >= 0 && banner.bottom <= innerHeight),
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        fontErrors: [...document.fonts].filter((f) => f.status === 'error').map((f) => f.family),
        footer: document.querySelector('.pf-footer')?.textContent ?? '',
        state: document.getElementById('main').dataset.state,
        empty: empty && !empty.hidden ? empty.textContent : '',
        kpis: document.querySelectorAll('#kpis .pf-kpi').length,
        ranking: document.querySelectorAll('#ranking tbody tr').length,
        findings: document.querySelectorAll('#findings tbody tr').length,
        tabs: document.querySelectorAll('#sheet-tabs [role="tab"]').length,
        alts: [...document.querySelectorAll('#previews img')].filter((img) => img.alt.length > 40).length,
      };
    });
    if (!info.title) problems.push('no title');
    if (info.theme !== theme) problems.push(`data-theme is ${info.theme}, expected ${theme}`);
    if (info.bg !== BG[theme]) problems.push(`page background ${info.bg}, expected ${BG[theme]}`);
    if (!info.banner) problems.push('demo banner missing or not on the first screen');
    if (info.overflow > 0) problems.push(`page scrolls sideways by ${info.overflow}px`);
    if (info.fontErrors.length) problems.push(`fonts failed: ${info.fontErrors.join(', ')}`);
    if (!info.footer.includes(FOOTER)) problems.push('footer line missing');
    const reached = await reachedByTab(page);
    if (!reached.has('theme-toggle')) problems.push('Tab never reaches the theme toggle');
    if (EXPECT === 'empty') {
      if (info.state !== 'empty' || !info.empty.includes('No weekly run yet')) problems.push(`expected the empty state, page is ${info.state}`);
    } else {
      if (info.state !== 'filled') problems.push(`expected a loaded report, page is ${info.state}`);
      if (info.kpis !== 7) problems.push(`${info.kpis} KPI tiles, expected 7`);
      if (info.ranking !== 12) problems.push(`${info.ranking} ranking rows, expected 12`);
      if (info.findings < 1) problems.push('findings table is empty');
      if (info.tabs !== 5) problems.push(`${info.tabs} sheet tabs, expected 5`);
      if (info.alts !== 5 && info.alts + (await page.locator('#previews .pf-empty').count()) !== 5) problems.push('preview images without alt text');
      if (!reached.has('tab-summary')) problems.push('Tab never reaches the Summary tab');
      problems.push(...(await checkTabs(page)));
    }
    await page.evaluate(() => {
      document.activeElement?.blur();
      window.scrollTo(0, 0);
    });
    await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
    await page.screenshot({ path: path.join(OUT, `${name}-top.png`) });
    done = true;
    if (problems.length) {
      failures += 1;
      console.log(`FAIL ${name}\n  ${problems.join('\n  ')}`);
    } else {
      console.log(`ok   ${name}  ${info.title}`);
    }
    await context.close();
  }
}
await browser.close();
server?.close();
const total = VIEWPORTS.length * 2;
console.log(failures ? `\n${failures} of ${total} CHECKS FAILED` : `\nALL ${total} CHECKS PASSED (${EXPECT}, ${LIVE ? 'live' : 'local'})`);
process.exit(failures ? 1 : 0);

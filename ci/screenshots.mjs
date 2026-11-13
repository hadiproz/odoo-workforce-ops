// Captures the README screenshots from a live Odoo demo database.
// Driven by .github/workflows/screenshots.yml; expects Odoo on localhost:8069.

import { execFileSync } from 'node:child_process';
import { mkdir, mkdtemp, readdir, rename, stat, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import { chromium } from 'playwright';

const BASE_URL = process.env.ODOO_URL ?? 'http://localhost:8069';
const DB = process.env.ODOO_DB ?? 'workforce_ops_demo';
const LOGIN = process.env.ODOO_LOGIN ?? 'admin';
const PASSWORD = process.env.ODOO_PASSWORD ?? 'admin';
const OUT_DIR = process.env.SCREENSHOT_DIR ?? 'docs/screenshots';
const APP_MENU_XMLID = 'workforce_ops.menu_workforce_ops_root';
const REPORT = 'workforce_ops.report_placement_assignment_letter';

const log = (...args) => console.log('[screenshots]', ...args);

async function waitForServer() {
  const deadline = Date.now() + 180_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${BASE_URL}/web/login`, { redirect: 'manual' });
      if (response.status === 200) {
        log('Odoo answers on', BASE_URL);
        return;
      }
    } catch {
      // server not listening yet
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error(`Odoo did not answer on ${BASE_URL}`);
}

async function settle(page, ms = 1500) {
  await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});
  await page
    .waitForFunction(() => !document.querySelector('.o_loading_indicator, .o_blockUI'), null, {
      timeout: 20_000,
    })
    .catch(() => {});
  await page.waitForTimeout(ms);
}

async function waitForRecords(page, selector, minimum) {
  const records = page.locator(selector);
  await records.first().waitFor({ state: 'visible', timeout: 60_000 });
  let count = await records.count();
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    const next = await records.count();
    if (next >= minimum && next === count) break;
    count = next;
    await page.waitForTimeout(500);
  }
  if (count < minimum) {
    throw new Error(`${selector}: expected at least ${minimum} records, saw ${count}`);
  }
  log(`${selector}: ${count} records rendered`);
}

async function shot(page, name) {
  const file = path.join(OUT_DIR, name);
  await page.screenshot({ path: file });
  log('captured', file);
}

async function login(page) {
  await page.goto(`${BASE_URL}/web/login?db=${encodeURIComponent(DB)}`, {
    waitUntil: 'domcontentloaded',
    timeout: 120_000,
  });
  await page.locator('input[name="login"]').waitFor({ state: 'visible', timeout: 60_000 });
  await page.locator('input[name="login"]').fill(LOGIN);
  await page.locator('input[name="password"]').fill(PASSWORD);
  await page.locator('button[type="submit"]').first().click();
  try {
    await page.locator('.o_main_navbar').waitFor({ state: 'visible', timeout: 120_000 });
  } catch (error) {
    const body = (await page.locator('body').innerText()).slice(0, 1500);
    throw new Error(`login did not reach the web client (${page.url()}):\n${body}`);
  }
  await page.locator('.o_loading_indicator').waitFor({ state: 'hidden', timeout: 20_000 }).catch(() => {});
  log('logged in as', LOGIN);
}

async function openWorkforceApp(page) {
  await page.locator('.o_navbar_apps_menu button').first().click();
  let app = page.locator(`.o_app[data-menu-xmlid="${APP_MENU_XMLID}"]`).first();
  if (!(await app.count())) {
    app = page.locator('.o_app').filter({ hasText: 'Workforce Ops' }).first();
  }
  await app.waitFor({ state: 'visible', timeout: 30_000 });
  await app.click();
  await page.locator('.o_main_navbar').waitFor({ state: 'visible', timeout: 30_000 });
  await settle(page, 800);
  log('opened Workforce Ops');
}

async function openMenu(page, label) {
  await page
    .locator('.o_main_navbar')
    .getByText(label, { exact: true })
    .first()
    .click();
  await settle(page, 800);
  log('opened menu', label);
}

async function switchToKanban(page) {
  const button = page.locator('.o_cp_switch_buttons .o_switch_view.o_kanban').first();
  if (await button.count()) {
    await button.click();
  } else {
    await page.getByRole('button', { name: /kanban/i }).first().click();
  }
  await page.locator('.o_kanban_view').first().waitFor({ state: 'visible', timeout: 30_000 });
  log('switched to kanban');
}

async function captureJobOrders(page) {
  await openMenu(page, 'Job Orders');
  await switchToKanban(page);
  await waitForRecords(page, '.o_kanban_view .o_kanban_record', 9);
  await settle(page, 2500);
  await shot(page, '01-job-orders-kanban.png');

  const card = page.locator('.o_kanban_record').filter({ hasText: 'Warehouse Operator' }).first();
  await card.click();
  await page.locator('.o_form_view').waitFor({ state: 'visible', timeout: 30_000 });
  await page.locator('.o_form_view .o_progressbar').first().waitFor({ state: 'visible', timeout: 30_000 });
  await page.locator('.o_statusbar_status').first().waitFor({ state: 'visible', timeout: 30_000 });
  await settle(page, 1500);
  await shot(page, '02-job-order-form.png');
}

async function captureWorkers(page) {
  await openMenu(page, 'Workers');
  await switchToKanban(page);
  await waitForRecords(page, '.o_kanban_view .o_kanban_record', 10);
  await settle(page, 2000);
  await shot(page, '03-workers.png');
}

async function capturePlacements(page) {
  await openMenu(page, 'Placements');
  await waitForRecords(page, '.o_data_row', 8);
  await settle(page, 2000);
  await shot(page, '04-placements.png');
}

async function captureAssignmentLetter(page) {
  const row = page.locator('.o_data_row').first();
  await row.click();
  await page.locator('.o_form_view').waitFor({ state: 'visible', timeout: 30_000 });
  await settle(page, 1500);
  const placementId = new URL(page.url())
    .pathname.split('/')
    .filter(Boolean)
    .reverse()
    .find((part) => /^\d+$/.test(part));
  if (!placementId) {
    throw new Error(`could not read placement id from ${page.url()}`);
  }
  const response = await page.request.get(`${BASE_URL}/report/pdf/${REPORT}/${placementId}`);
  if (!response.ok()) {
    throw new Error(`assignment letter PDF returned HTTP ${response.status()}`);
  }
  const workDir = await mkdtemp(path.join(os.tmpdir(), 'workforce-letter-'));
  const pdfPath = path.join(workDir, 'assignment-letter.pdf');
  const pngStem = path.join(workDir, 'assignment-letter');
  await writeFile(pdfPath, await response.body());
  execFileSync('pdftoppm', ['-png', '-f', '1', '-l', '1', '-r', '120', pdfPath, pngStem]);
  await rename(`${pngStem}-1.png`, path.join(OUT_DIR, '05-assignment-letter.png'));
  log('captured', path.join(OUT_DIR, '05-assignment-letter.png'));
}

async function run() {
  await mkdir(OUT_DIR, { recursive: true });
  await waitForServer();

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    locale: 'en-US',
  });
  page = await context.newPage();
  page.setDefaultTimeout(60_000);

  try {
    await login(page);
    await openWorkforceApp(page);
    await captureJobOrders(page);
    await captureWorkers(page);
    await capturePlacements(page);
    try {
      await captureAssignmentLetter(page);
    } catch (error) {
      // The letter shot is optional; do not fail the whole run for it.
      log('optional assignment letter capture failed:', error.message);
    }
  } finally {
    const files = await readdir(OUT_DIR);
    for (const name of files.filter((file) => file.endsWith('.png')).sort()) {
      const { size } = await stat(path.join(OUT_DIR, name));
      log(`${name}: ${(size / 1024).toFixed(1)} KiB`);
    }
    await browser.close();
  }
}

let page;
run().catch(async (error) => {
  console.error('[screenshots] FAILED:', error);
  if (page) {
    await page
      .screenshot({ path: path.join(OUT_DIR, 'debug-failure.png') })
      .catch(() => {});
  }
  process.exitCode = 1;
});

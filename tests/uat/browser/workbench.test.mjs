import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import { extname, resolve, sep } from 'node:path';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import {
  analysisTitle, customers, extracted, filename, fixture, historicalNote, jobs, original, password, rationale,
  replacement, reviewsPath, session, sourceContextId, uploadedFilename, uploadedOriginal, version1, version2, version2Hash, workspaces,
} from './fixtures.mjs';

const require = createRequire(import.meta.url);
const playwrightEntry = process.env.UAT_PLAYWRIGHT_ENTRY || 'playwright';
const { chromium } = require(playwrightEntry);
const { expect } = require(process.env.UAT_PLAYWRIGHT_ENTRY
  ? resolve(playwrightEntry, '../test.js')
  : 'playwright/test');

const dist = fileURLToPath(new URL('../../../frontend/dist', import.meta.url));
const mime = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript',
  '.mjs': 'text/javascript', '.svg': 'image/svg+xml', '.woff': 'font/woff', '.woff2': 'font/woff2',
};
const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url, 'http://127.0.0.1');
    const path = resolve(dist, '.' + (url.pathname === '/' ? '/index.html' : url.pathname));
    if (request.method !== 'GET' || url.pathname.startsWith('/api/') || !path.startsWith(dist + sep)) {
      response.writeHead(404).end();
      return;
    }
    const body = await readFile(path);
    response.writeHead(200, { 'Content-Type': mime[extname(path)] || 'application/octet-stream' }).end(body);
  } catch {
    response.writeHead(404).end();
  }
});

let browser;
let origin;
before(async () => {
  await readFile(resolve(dist, 'index.html'));
  await new Promise((onListening, onError) => {
    server.once('error', onError);
    server.listen(0, '127.0.0.1', onListening);
  });
  origin = 'http://127.0.0.1:' + server.address().port;
  browser = await chromium.launch();
});
after(async () => {
  await browser?.close();
  if (server.listening) await new Promise(resolve => server.close(resolve));
});

function scenario(name, run, { signedIn = true, viewport = { width: 1440, height: 900 }, todo } = {}) {
  test(name, { timeout: 30_000, todo }, async () => {
    const context = await browser.newContext({ viewport, locale: 'tr-TR', serviceWorkers: 'block' });
    const runtimeErrors = [];
    try {
      const state = await fixture(context, origin, { signedIn });
      const page = await context.newPage();
      page.setDefaultTimeout(5_000);
      page.on('pageerror', error => runtimeErrors.push(error.message));
      await page.goto(origin);
      try {
        await run(page, state);
      } catch (error) {
        if (state.unexpected.length || runtimeErrors.length) {
          error.message += '\nFixture and browser errors: ' + [...state.unexpected, ...runtimeErrors].join('; ');
        }
        throw error;
      }
      assert.deepEqual(state.unexpected, [], 'Unexpected network traffic or API contract mismatch');
      assert.deepEqual(runtimeErrors, [], 'Uncaught browser error');
    } finally {
      await context.close();
    }
  });
}

const frameNames = ['Gezinme', 'Çalışma alanı', 'Hukuk asistanı'];
const workspaceList = page => page.getByRole('main').getByRole('link', { name: /UAT .* dosyası/ });
const mainHeading = page => page.getByRole('heading', { name: 'Hazırlığın başlangıç noktası.' });
const portfolioFilters = page => page.getByRole('region', { name: 'Portföy filtreleri' });
const workQueue = page => page.getByRole('navigation', { name: 'Ana gezinme' }).getByRole('link', { name: 'İşlerim' });
const passwordInputs = page => ['Mevcut parola', 'Yeni parola', 'Yeni parola (tekrar)']
  .map(label => page.getByLabel(label, { exact: true }));

async function login(page, secret) {
  await page.getByLabel('Kullanıcı adı').fill(session.user.id);
  await page.getByLabel('Parola', { exact: true }).fill(secret);
  await page.getByRole('button', { name: 'Çalışma alanına gir' }).click();
}

scenario('desktop panels collapse, resize by mouse and keyboard, maximize, and persist layout', async page => {
  await expect(mainHeading(page)).toBeVisible();
  for (const name of frameNames) {
    const frame = page.getByRole('region', { name, exact: true });
    await expect(frame).toBeVisible();
    await frame.getByRole('button', { name: name + ' panelini daralt' }).click();
    await expect(frame.locator('.frame-content')).toBeHidden();
    await frame.getByRole('button', { name: name + ' panelini aç' }).click();
    await expect(frame.locator('.frame-content')).toBeVisible();
  }
  const left = page.getByRole('separator', { name: 'Gezinme ve çalışma alanı genişliğini ayarla' });
  const right = page.getByRole('separator', { name: 'Çalışma alanı ve asistan genişliğini ayarla' });
  const leftBefore = Number(await left.getAttribute('aria-valuenow'));
  const rightBefore = Number(await right.getAttribute('aria-valuenow'));
  const navigation = page.getByRole('region', { name: 'Gezinme', exact: true });
  const assistant = page.getByRole('region', { name: 'Hukuk asistanı', exact: true });
  await expect(left).toHaveAttribute('aria-orientation', 'vertical');
  await expect(left).toHaveAttribute('aria-controls', 'frame-navigation frame-main');
  await left.focus();
  await page.keyboard.press('ArrowRight');
  await expect(left).toHaveAttribute('aria-valuenow', String(leftBefore + 24));
  await expect.poll(async () => (await navigation.boundingBox()).width).toBe(leftBefore + 24);
  const bar = await right.boundingBox();
  await page.mouse.move(bar.x + bar.width / 2, bar.y + bar.height / 2);
  await page.mouse.down();
  await page.mouse.move(bar.x + bar.width / 2 - 35, bar.y + bar.height / 2, { steps: 5 });
  await page.mouse.up();
  await expect(right).toHaveAttribute('aria-valuenow', String(rightBefore + 35));
  await expect.poll(async () => (await assistant.boundingBox()).width).toBe(rightBefore + 35);
  for (const name of frameNames) {
    const frame = page.getByRole('region', { name, exact: true });
    const maximize = frame.getByRole('button', { name: name + ' tam ekran' });
    await maximize.focus();
    await page.keyboard.press('Enter');
    await expect(frame.getByRole('button', { name: name + ' normal görünüme dön' })).toBeFocused();
    for (const other of frameNames.filter(value => value !== name)) {
      await expect(page.getByRole('region', { name: other, exact: true })).toBeHidden();
    }
    await expect.poll(async () => (await frame.boundingBox()).width).toBe(1440);
    await page.keyboard.press('Escape');
    await expect(maximize).toBeFocused();
  }
  await assistant.getByRole('button', { name: 'Hukuk asistanı panelini daralt' }).click();
  await page.reload();
  await expect(mainHeading(page)).toBeVisible();
  await expect(assistant.getByRole('button', { name: 'Hukuk asistanı panelini aç' })).toBeVisible();
  await expect(left).toHaveAttribute('aria-valuenow', String(leftBefore + 24));
  await assistant.getByRole('button', { name: 'Hukuk asistanı panelini aç' }).click();
  await expect(right).toHaveAttribute('aria-valuenow', String(rightBefore + 35));
});

scenario('portfolio OR and inclusive date filters scope the workspace list and assistant request', async (page, state) => {
  const filters = portfolioFilters(page);
  await expect(workspaceList(page)).toHaveCount(3);
  await filters.getByRole('checkbox', { name: customers[0].name }).check();
  await expect(workspaceList(page)).toHaveCount(1);
  await expect(workspaceList(page).first()).toContainText(workspaces[0].title);
  await filters.getByRole('checkbox', { name: customers[1].name }).check();
  await expect(workspaceList(page)).toHaveCount(2);
  await expect(workspaceList(page).last()).toContainText(workspaces[1].title);
  await filters.getByLabel('Tarih alanı').selectOption('relevant_date');
  await filters.getByLabel('Filtre başlangıç tarihi').fill('2026-09-01');
  await filters.getByLabel('Filtre bitiş tarihi').fill('2026-09-10');
  await expect(workspaceList(page)).toHaveCount(1);
  await expect(workspaceList(page).first()).toContainText(workspaces[0].title);
  const query = state.calls.filter(call => call.path === '/workspaces').at(-1).params;
  assert.deepEqual(Object.fromEntries(query), {
    date_field: 'relevant_date', customer_ids: customers[0].id + ',' + customers[1].id,
    date_from: '2026-09-01', date_to: '2026-09-10',
  });
  await page.getByRole('button', { name: 'Haftalık Portföy özeti' }).click();
  await expect(page.getByText('UAT özel bağlam yanıtı.')).toBeVisible();
  const summary = state.calls.find(call => call.path === '/assistant/respond');
  assert.deepEqual(summary.body, {
    mode: 'weekly', question: '', context: {
      workspace_id: null, page: 'matters', section: 'overview', customer_ids: [customers[0].id, customers[1].id],
      date_from: '2026-09-01', date_to: '2026-09-10', date_field: 'relevant_date',
    },
  });
  await filters.getByLabel('Filtre başlangıç tarihi').fill('2026-09-11');
  await expect(page.getByText('Başlangıç tarihi bitiş tarihinden sonra olamaz.').first()).toBeVisible();
  await expect(workspaceList(page)).toHaveCount(0);
  await filters.getByRole('button', { name: 'Temizle' }).click();
  await expect(workspaceList(page)).toHaveCount(3);
});

async function openTreeFile(page) {
  const tree = page.getByRole('region', { name: 'Çalışma alanları ve yüklenen dosyalar' });
  await tree.getByRole('button', { name: workspaces[0].title + ': dosyaları göster' }).click();
  await tree.getByRole('link', { name: filename }).click();
}

async function uploadFile(page) {
  const upload = page.getByRole('button', { name: 'Dosya yükle', exact: true });
  const chooser = page.waitForEvent('filechooser');
  await upload.click();
  await (await chooser).setFiles({
    name: uploadedFilename, mimeType: 'text/plain', buffer: Buffer.from(uploadedOriginal),
  });
  await expect(page.getByText(/1 belge yüklendi/)).toBeVisible();
}

scenario('workspace tree opens the selected file, separates original from extraction, and refreshes after upload', async (page, state) => {
  state.blocked = true;
  const tree = page.getByRole('region', { name: 'Çalışma alanları ve yüklenen dosyalar' });
  const branch = tree.getByRole('button', { name: workspaces[0].title + ': dosyaları göster' });
  await expect(branch).toHaveAttribute('aria-expanded', 'false');
  await branch.click();
  await expect(tree.getByRole('button', { name: workspaces[0].title + ': dosyaları gizle' }))
    .toHaveAttribute('aria-expanded', 'true');
  await expect(tree.getByRole('link', { name: 'uat-beta-belgesi.txt' })).toHaveCount(0);
  await tree.getByRole('link', { name: filename }).click();
  await expect(page).toHaveURL(/tab=documents&document=uat-document-selected$/);
  await expect(page.getByRole('heading', { name: filename })).toBeVisible();
  await expect(page.getByText(original)).toBeVisible();
  const selectText = page.getByRole('button', { name: 'Çıkarılan metin' });
  await selectText.click();
  await expect(selectText).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText(extracted)).toBeVisible();
  await expect(page.getByText(original)).toBeHidden();
  const upload = page.getByRole('button', { name: 'Dosya yükle', exact: true });
  await expect(page.getByText('Belge yükleme şu anda kapalı.')).toBeVisible();
  await expect(upload).toBeDisabled();
  state.blocked = false;
  await page.getByRole('button', { name: 'Yeniden denetle' }).click();
  await expect(upload).toBeEnabled();
  await uploadFile(page);
  const newFile = tree.getByRole('link', { name: uploadedFilename });
  await expect(newFile).toBeVisible();
  await newFile.click();
  await expect(page.getByRole('heading', { name: uploadedFilename })).toBeVisible();
  await tree.getByRole('button', { name: workspaces[1].title + ': dosyaları göster' }).click();
  const otherFile = tree.getByRole('link', { name: 'uat-beta-belgesi.txt' });
  await otherFile.click();
  await expect(page.getByRole('heading', { name: 'uat-beta-belgesi.txt' })).toBeVisible();
  await expect(page.getByRole('main').getByText(uploadedFilename)).toHaveCount(0);
});

scenario('upload selects the new file even when opened from a different file’s deep link', async (page, state) => {
  await openTreeFile(page);
  await page.evaluate(() => { window.location.hash += '&view_note=unchanged'; });
  await expect(page.getByText(original)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Dosya yükle', exact: true })).toBeEnabled();
  await uploadFile(page);
  await expect(page.getByRole('heading', { name: uploadedFilename })).toBeVisible();
  await expect(page).toHaveURL(/document=uat-uploaded&view_note=unchanged$/);
  await expect(page.getByText(uploadedOriginal, { exact: true })).toBeVisible();
  await expect(page.getByText(original, { exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('heading', { name: uploadedFilename })).toBeVisible();
  const files = page.getByLabel('Çalışma alanındaki dosyalar');
  await files.getByRole('button', { name: new RegExp(filename) }).click();
  await expect(page).toHaveURL(/document=uat-document-selected&view_note=unchanged$/);
  await expect(page.getByText(original, { exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole('heading', { name: uploadedFilename })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole('heading', { name: filename })).toBeVisible();

  // An invalid exact identifier must not silently substitute the first source.
  await page.evaluate(() => { window.location.hash = window.location.hash.replace('uat-document-selected', 'uat-missing'); });
  await expect(page.getByText('UAT: Belge bulunamadı.')).toBeVisible();
  await expect(page.getByRole('main').getByText(original, { exact: true })).toHaveCount(0);
  await page.goBack();
  await expect(page.getByRole('heading', { name: filename })).toBeVisible();

  // Completing an upload cannot redirect a user who has opened another workspace.
  let release;
  state.lateUpload = new Promise(resolve => { release = resolve; });
  await page.getByLabel('Çalışma alanına dosya yükle').setInputFiles({
    name: uploadedFilename, mimeType: 'text/plain', buffer: Buffer.from(uploadedOriginal),
  });
  await expect.poll(() => state.uploadCount).toBe(2);
  const tree = page.getByRole('region', { name: 'Çalışma alanları ve yüklenen dosyalar' });
  await tree.getByRole('button', { name: workspaces[1].title + ': dosyaları göster' }).click();
  await tree.getByRole('link', { name: 'uat-beta-belgesi.txt' }).click();
  await expect(page.getByRole('heading', { name: 'uat-beta-belgesi.txt' })).toBeVisible();
  release();
  await expect.poll(() => state.uploadResponses).toBe(2);
  await expect(page).toHaveURL(/uat-case-b\?tab=documents&document=uat-document-beta$/);
  await expect(page.getByRole('heading', { name: 'uat-beta-belgesi.txt' })).toBeVisible();
});

scenario('work queue combines workspace scope with due bucket and opens the exact work item', async (page, state) => {
  await workQueue(page).click();
  await expect(page.getByRole('heading', { name: 'İşlerim ve gözetim' })).toBeVisible();
  for (const job of jobs) await expect(page.getByRole('heading', { name: job.title })).toBeVisible();
  const filters = portfolioFilters(page);
  await filters.getByRole('checkbox', { name: customers[1].name }).check();
  await expect(page.getByRole('heading', { name: jobs[2].title })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: jobs[1].title })).toBeVisible();
  await page.getByLabel('İş durumu').selectOption('overdue');
  await expect(page.getByRole('heading', { name: jobs[1].title })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: jobs[0].title })).toBeVisible();
  await filters.getByLabel('Tarih alanı').selectOption('relevant_date');
  await filters.getByLabel('Filtre başlangıç tarihi').fill('2026-09-11');
  await expect(page.getByRole('heading', { name: 'Bu görünümde iş bulunamadı.' })).toBeVisible();
  await filters.getByLabel('Filtre başlangıç tarihi').fill('2026-09-10');
  await page.getByRole('combobox', { name: 'Görünüm' }).selectOption('supervisory');
  await expect(page.getByRole('link', { name: 'Çalışmayı aç' })).toBeVisible();
  const queue = state.calls.filter(call => call.path === '/work').at(-1);
  assert.deepEqual(Object.fromEntries(queue.params), { view: 'supervisory', bucket: 'overdue' });
  await page.getByRole('link', { name: 'Çalışmayı aç' }).click();
  await expect(page).toHaveURL(/tab=workflow&work=uat-task-a$/);
  await expect(page.getByText(jobs[0].description)).toBeVisible();
});

scenario('source-review queue pins both date ranges, retires late scope, and rejects a mismatched echo', async (page, state) => {
  const filters = portfolioFilters(page);
  await filters.getByRole('checkbox', { name: customers[1].name }).check();
  await filters.getByRole('checkbox', { name: customers[0].name }).check();
  await filters.getByLabel('Tarih alanı').selectOption('relevant_date');
  await filters.getByLabel('Filtre başlangıç tarihi').fill('2026-09-10');
  await filters.getByLabel('Filtre bitiş tarihi').fill('2026-09-15');
  await workQueue(page).click();
  await page.getByRole('button', { name: 'Portföy kaynak incelemeleri' }).click();
  await expect(page.getByRole('heading', { name: 'Kaynak incelemeleri' })).toBeVisible();
  const sourceFrom = page.getByLabel('Portföy kaynak kayıt tarihi başlangıcı');
  const sourceTo = page.getByLabel('Portföy kaynak kayıt tarihi bitişi');
  const update = page.getByRole('button', { name: 'Portföy kaynak kuyruğunu güncelle' });
  const results = page.getByRole('region', { name: 'Portföy kaynak inceleme sonuçları' });
  const calls = () => state.calls.filter(call => call.path === '/work/source-reviews');
  await sourceFrom.fill('2026-10-20');
  await sourceTo.fill('2026-10-22');
  await page.getByLabel('Portföy kaynak inceleme durumu').selectOption('action_required');
  assert.equal(calls().length, 0);
  await update.click();
  const open = results.getByRole('link', { name: 'Tam kaynak bağlamını aç' });
  await expect(open).toHaveAttribute('href',
    '#/matters/uat-case-a?tab=source-review&analysis=uat-analysis&source_context=' + sourceContextId);
  await expect(results.getByText('Kamu kaynakları kontrol edilmedi.', { exact: false })).toBeVisible();
  assert.deepEqual(Object.fromEntries(calls()[0].params), {
    bucket: 'action_required', date_field: 'relevant_date', offset: '0', customer_ids: 'uat-alpha,uat-beta',
    date_from: '2026-09-10', date_to: '2026-09-15', source_date_from: '2026-10-20', source_date_to: '2026-10-22',
  });
  const delayed = Promise.withResolvers();
  state.lateQueue = delayed.promise;
  try {
    await update.click();
    await expect.poll(() => calls().length).toBe(2);
    const retired = page.waitForEvent('requestfailed', { predicate: request => request.url().includes('/work/source-reviews?') });
    await filters.getByLabel('Filtre başlangıç tarihi').fill('2026-09-11');
    await expect(update).toBeEnabled();
    delayed.resolve();
    await retired;
    await expect(results).toHaveCount(0);
  } finally {
    delayed.resolve();
    state.lateQueue = null;
  }
  await update.click();
  await expect(results.getByText(/Bu pencerede filtreye uygun kayıt yok/)).toBeVisible();
  await filters.getByLabel('Filtre başlangıç tarihi').fill('2026-09-10');
  await expect(results).toHaveCount(0);
  state.mismatchedQueue = true;
  await update.click();
  await expect(page.getByRole('alert')).toContainText('filtre veya kapsam bağı doğrulanamadı');
  await expect(results).toHaveCount(0);
});

scenario('review examples leave the draft untouched and an explicit change request binds to its exact version', async (page, state) => {
  await workspaceList(page).filter({ hasText: workspaces[0].title }).click();
  await page.getByRole('button', { name: 'Çalışma notları' }).click();
  await page.getByText('Yapılandırılmış analiz taslakları (1)', { exact: true }).click();
  await expect(page.getByRole('heading', { name: analysisTitle })).toBeVisible();
  await expect(page.getByText('Sürüm 2 · İnceleme gerekli')).toBeVisible();
  await page.getByText('Avukat inceleme kararı kaydet', { exact: true }).click();
  await page.getByRole('button', { name: 'Gösterilen sürümün inceleme formunu aç' }).click();
  const note = page.getByLabel('İnceleme kararının gerekçesi');
  const decision = page.getByLabel('İnceleme kararı', { exact: true });
  const submit = page.getByRole('button', { name: 'İnceleme kararını kaydet', exact: true });
  const examples = page.getByText('Gerekçe örneklerini gör (isteğe bağlı)', { exact: true });
  const writes = () => state.calls.filter(call => call.path === reviewsPath && call.method === 'POST');
  const criteria = ['Özgün kaynaklar', 'Gerekçe ve koşullar', 'Olgu rolleri ve çelişkiler',
    'Alternatifler ve kapsam sınırları', 'Model katkısı'].map(label => page.getByLabel(label, { exact: true }));
  await expect(note).toHaveAccessibleDescription(/2–4 cümleyle/);
  await expect(examples.locator('..')).toHaveJSProperty('open', false);
  await examples.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Değişiklik gerekli — örnek' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Koşullu özel taslak incelendi — örnek' })).toBeVisible();
  await expect(note).toHaveValue('');
  await expect(decision).toHaveValue('changes_requested');
  for (const criterion of criteria) await expect(criterion).toHaveValue('');
  await expect(submit).toBeDisabled();
  await expect(page.getByText('Sürüm 2 · İnceleme gerekli')).toBeVisible();
  assert.equal(writes().length, 0);
  await note.fill(rationale);
  await decision.selectOption('reviewed_conditional');
  await expect(submit).toBeDisabled();
  await examples.click();
  await examples.click();
  await expect(note).toHaveValue(rationale);
  await expect(decision).toHaveValue('reviewed_conditional');
  assert.equal(writes().length, 0);

  await decision.selectOption('changes_requested');
  await criteria[0].selectOption('needs_change');
  await page.getByLabel('Özgün kaynaklar notu', { exact: true }).fill('UAT: Dayanak açıklaması eksik.');
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(page.getByText('Sürüm 2 · İnceleme kararı kayıtlı')).toBeVisible();
  await expect(page.getByText('Avukat değişiklik istedi', { exact: true })).toBeVisible();
  assert.equal(writes().length, 1);
  const { request_id, ...body } = writes()[0].body;
  assert.match(request_id, /^[a-f0-9]{32}$/);
  assert.deepEqual(body, {
    version_id: version2, expected_revision: 2, expected_review_id: null, content_sha256: version2Hash,
    decision: 'changes_requested', note: rationale, findings: [],
    criteria: [{ criterion: 'sources', outcome: 'needs_change', note: 'UAT: Dayanak açıklaması eksik.' }],
  });

  await page.getByText('Değiştirilemez sürüm geçmişi', { exact: true }).click();
  await page.getByRole('button', { name: 'Sürümleri getir', exact: true }).click();
  for (const { number, version, expectedNote, otherNote } of [
    { number: 1, version: version1, expectedNote: historicalNote, otherNote: rationale },
    { number: 2, version: version2, expectedNote: rationale, otherNote: historicalNote },
  ]) {
    const summary = page.locator('summary').filter({ hasText: new RegExp('^Sürüm ' + number + ' ·') });
    await summary.click();
    const historicalVersion = summary.locator('..');
    await historicalVersion.getByText('Bu sürümün inceleme kararları', { exact: true }).click();
    const history = historicalVersion.locator('details').filter({
      has: page.locator('summary').getByText('Bu sürümün inceleme kararları', { exact: true }),
    });
    await history.getByRole('button', { name: 'İncelemeleri getir' }).click();
    await history.getByText(/^İnceleme #1 ·/).click();
    await expect(history.getByText(expectedNote, { exact: true })).toBeVisible();
    await expect(history.getByText(otherNote, { exact: true })).toHaveCount(0);
    await history.getByText('İnceleme sürümü ve kayıt bağı', { exact: true }).click();
    await expect(history.getByText('Sürüm: ' + version, { exact: false })).toBeVisible();
    const query = state.calls.filter(call => call.path === reviewsPath && call.method === 'GET').at(-1).params;
    assert.deepEqual(Object.fromEntries(query), { version_id: version, limit: '10', offset: '0' });
  }
});

scenario('password change requires the current password, clears errors, and requires reauthentication', async (page, state) => {
  await login(page, password);
  await expect(mainHeading(page)).toBeVisible();
  await page.getByRole('link', { name: 'Parolayı değiştir' }).click();
  await expect(page.getByText(/bu oturum dahil tüm cihazlardaki oturumlarınız kapatılır/)).toBeVisible();
  const fields = passwordInputs(page);
  const submit = page.getByRole('button', { name: 'Parolayı değiştir ve oturumları kapat' });
  const attempts = () => state.calls.filter(call => call.path === '/auth/password');
  for (const [index, field] of fields.entries()) {
    await expect(field).toHaveValue('');
    await expect(field).toHaveAttribute('type', 'password');
    await expect(field).toHaveAttribute('autocomplete', index === 0 ? 'current-password' : 'new-password');
  }
  await fields[1].fill(replacement);
  await fields[2].fill(replacement);
  await submit.click();
  await expect(fields[0]).toBeFocused();
  assert.equal(attempts().length, 0);

  await fields[0].fill('uat-incorrect-current-password');
  await submit.click();
  await expect(page.getByRole('alert')).toContainText('Mevcut parola doğrulanamadı.');
  for (const field of fields) await expect(field).toHaveValue('');
  assert.equal(state.signedIn, true);
  assert.equal(attempts().length, 1);

  await fields[0].fill(password);
  await fields[1].fill(replacement);
  await fields[2].fill(replacement);
  await submit.click();
  await expect(page.getByRole('status')).toContainText('Parolanız değiştirildi.');
  await expect(page.getByRole('main')).toHaveCount(0);
  assert.deepEqual(attempts()[1].body, {
    current_password: password, new_password: replacement, confirm_password: replacement,
  });
  assert.equal(attempts()[1].csrf, session.csrf_token);
  const storage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  for (const secret of [password, replacement]) {
    assert.equal(storage.includes(secret), false);
    assert.equal(decodeURIComponent(page.url()).includes(secret), false);
  }
  await login(page, password);
  await expect(page.getByRole('alert')).toContainText('Kullanıcı adı veya parola geçersiz.');
  await login(page, replacement);
  await expect(mainHeading(page)).toBeVisible();
}, { signedIn: false });

scenario('401 during session monitoring clears the private workspace and pending assistant state', async (page, state) => {
  await workspaceList(page).filter({ hasText: workspaces[0].title }).click();
  await page.getByRole('button', { name: 'Dosyalar 2' }).click();
  await page.getByRole('button', { name: new RegExp(filename) }).click();
  await expect(page.getByText(original)).toBeVisible();
  await portfolioFilters(page).getByRole('checkbox', { name: customers[1].name }).check();
  await page.getByRole('button', { name: 'Bu ekranda nasıl ilerlerim?' }).click();
  await expect(page.getByText('UAT özel bağlam yanıtı.')).toBeVisible();
  const pending = Promise.withResolvers();
  state.lateGuide = pending.promise;
  try {
    await page.getByLabel('Asistana sorun').fill('UAT özel bekleyen soru');
    await page.getByRole('button', { name: 'Asistana gönder' }).click();
    await expect.poll(() => state.calls.filter(call => call.path === '/assistant/respond').length).toBe(2);
    state.signedIn = false;
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await expect(page.getByRole('alert')).toContainText('Erişim veya oturum değişti.');
    assert.equal(await page.getByText(original).count(), 0);
    assert.equal(await page.getByText('UAT özel bağlam yanıtı.').count(), 0);
  } finally {
    pending.resolve();
  }
  await login(page, password);
  await expect(page.getByRole('heading', { name: workspaces[0].title })).toBeVisible();
  await expect(page.getByText('UAT özel bağlam yanıtı.')).toHaveCount(0);
  await expect(page.getByLabel('Asistana sorun')).toHaveValue('');
  await expect(portfolioFilters(page).getByRole('checkbox', { name: customers[1].name })).not.toBeChecked();
});

scenario('narrow viewport exposes one panel, supports keyboard skip, and keeps navigation usable', async page => {
  await expect(mainHeading(page)).toBeVisible();
  const tabs = page.getByRole('navigation', { name: 'Panel seçimi' });
  const navButton = tabs.getByRole('button', { name: 'Gezinme' });
  const mainButton = tabs.getByRole('button', { name: 'Çalışma alanı' });
  const assistantButton = tabs.getByRole('button', { name: 'Hukuk asistanı' });
  await expect(mainButton).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('separator')).toHaveCount(0);
  await navButton.click();
  await expect(navButton).toHaveAttribute('aria-pressed', 'true');
  await expect(portfolioFilters(page)).toBeVisible();
  await expect(mainHeading(page)).toBeHidden();
  await assistantButton.click();
  await expect(page.getByLabel('Asistana sorun')).toBeVisible();
  await expect(portfolioFilters(page)).toBeHidden();
  const skip = page.getByRole('link', { name: 'İçeriğe geç' });
  await skip.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();
  await expect(mainButton).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByLabel('Asistana sorun')).toBeHidden();
  await navButton.click();
  await workQueue(page).click();
  await expect(page.getByRole('heading', { name: 'İşlerim ve gözetim' })).toBeVisible();
  await expect(mainButton).toHaveAttribute('aria-pressed', 'true');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
}, { viewport: { width: 390, height: 844 } });

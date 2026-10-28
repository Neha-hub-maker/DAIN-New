// Run explicitly: node --test tests/verification.browser.cjs
// Uses the same full-page, intercepted-HTTP setup as the earlier browser checks.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {before, after, test} = require('node:test');
const {chromium} = require('playwright');

const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const FRONTEND = 'https://neha-hub-maker.github.io';
const API = 'https://dain-new.vercel.app';
const apiConfig = fs.readFileSync(path.join(root, 'api-config.js'), 'utf8');
const EMAIL = 'student@cs.du.ac.bd';
const HEADLINE = 'PRIVATE_STORY_MARKER robotics team award';
const SUMMARY = 'PRIVATE_SUMMARY_MARKER university students won the national robotics competition.';
let browser;
before(async () => {
  const executablePath = process.env.DAIN_CHROMIUM_PATH || (fs.existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined);
  browser = await chromium.launch({headless:true, executablePath});
});
after(async () => { await browser?.close(); });

function result(status='verified') {
  return {status, reason:'test_reason', claims:status === 'verification_pending' ? [] : [{text:'A team won the award.', verdict:status === 'verified' ? 'verified' : status === 'rejected' ? 'contradicted' : 'unverified', confidence:0.9, sources:['https://news.example.test/award']}], stages:[
    {id:'identity', status:'passed', detail:'DU author accepted.'},
    {id:'editorial', status:status === 'verified' ? 'passed' : status === 'rejected' ? 'failed' : 'held', detail:'Editorial result.'},
    {id:'routing', status:status === 'verified' ? 'passed' : 'skipped', detail:'Routing result.'},
  ]};
}

async function fixture(t, options={}) {
  const context = await browser.newContext({serviceWorkers:'block'});
  t.after(() => context.close());
  const page = await context.newPage();
  const errors = [], calls = [];
  let healthCount = 0;
  page.on('pageerror', error => errors.push(error.message));
  await context.addInitScript(({API, EMAIL, options}) => {
    localStorage.setItem('dain_user', JSON.stringify({name:'Test Student', email:EMAIL, role:'Student', institution:'University of Dhaka', isVerified:true, isLoggedIn:true}));
    localStorage.setItem('dain_stories', '[]');
    sessionStorage.setItem('dain_api_session', JSON.stringify({email:EMAIL, token:'browser-test-token'}));
    window.__warnings = [];
    const warn = console.warn.bind(console);
    console.warn = (...args) => { window.__warnings.push(args); warn(...args); };
    window.__delays = [];
    const nativeTimeout = window.setTimeout.bind(window);
    window.setTimeout = (fn, delay, ...args) => {
      window.__delays.push(delay);
      const shortened = options.healthTimeout && delay === 5000 ? 60 : ['timeout', 'body_timeout'].includes(options.mode) && delay === 40000 ? 100 : delay;
      return nativeTimeout(fn, shortened, ...args);
    };
    if (options.mode === 'body_timeout') {
      const nativeFetch = window.fetch.bind(window);
      window.fetch = async (url, init) => {
        const response = await nativeFetch(url, init);
        if (String(url).endsWith('/submissions/verify')) {
          response.json = () => new Promise((_resolve, reject) => {
            const abort = () => reject(new DOMException('Synthetic body timeout', 'AbortError'));
            if (init.signal.aborted) abort();
            else init.signal.addEventListener('abort', abort, {once:true});
          });
        }
        return response;
      };
    }
  }, {API, EMAIL, options});
  const cors = {'access-control-allow-origin':FRONTEND, 'access-control-allow-methods':'GET, POST, OPTIONS', 'access-control-allow-headers':'Content-Type, Authorization'};
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin === API) {
      calls.push({method:request.method(), path:url.pathname});
      if (request.method() === 'OPTIONS') return route.fulfill({status:204, headers:cors});
      if (url.pathname === '/health') {
        healthCount++;
        if (options.healthTimeout || options.superseded && healthCount === 1) return;
        if (options.healthFailures && healthCount <= options.healthFailures) return route.abort('connectionrefused');
        return route.fulfill({status:options.healthStatus || 200, headers:cors, contentType:'application/json', body:'{"status":"ok"}'});
      }
      assert.equal(url.pathname, '/submissions/verify');
      assert.equal(request.method(), 'POST');
      assert.equal(request.headers().authorization, 'Bearer browser-test-token');
      if (options.mode === 'timeout') return;
      if (options.mode === 'network') return route.abort('connectionrefused');
      const body = options.mode === 'invalid_json' ? 'not json' : options.mode === 'invalid_schema' ? '{}' : options.mode === 'http' ? '{"detail":"DO_NOT_LOG_RESPONSE browser-test-token"}' : JSON.stringify(options.response || result(options.status));
      return route.fulfill({status:options.httpStatus || 200, headers:options.mode === 'cors' ? {'access-control-allow-origin':'https://unlisted.example.test'} : cors, contentType:'application/json', body});
    }
    if (url.origin === FRONTEND && url.pathname === '/DAIN-New/index.html') return route.fulfill({contentType:'text/html', body:html});
    if (url.origin === FRONTEND && url.pathname === '/DAIN-New/api-config.js') return route.fulfill({contentType:'text/javascript', body:apiConfig});
    if (url.host === 'cdn.tailwindcss.com') return route.fulfill({contentType:'text/javascript', body:'window.tailwind={};'});
    if (url.pathname.endsWith('.png')) return route.fulfill({contentType:'image/png', body:fs.readFileSync(path.join(root, 'assets/dunite-logo.png'))});
    if (url.pathname.endsWith('.woff2')) return route.fulfill({contentType:'font/woff2', body:fs.readFileSync(path.join(root, 'assets/fonts/ProductSans-Regular.woff2'))});
    return route.fulfill({contentType:'text/css', body:'.hidden{display:none!important}'});
  });
  await page.goto(FRONTEND + '/DAIN-New/index.html#submit', {waitUntil:'domcontentloaded'});
  await page.waitForFunction(() => document.querySelector('#view-submit').classList.contains('active'));
  return {page, errors, calls};
}

async function submit(page) {
  await page.locator('#category').selectOption('Academic');
  await page.locator('#sub-type').fill('Awards');
  await page.locator('#headline').fill(HEADLINE);
  await page.locator('#summary').fill(SUMMARY);
  await page.locator('#btn-wizard-next').click();
  await page.locator('#achievement-date').fill('2024-06-01');
  await page.locator('#institution').fill('University of Dhaka');
  await page.locator('#author-email').fill(EMAIL);
  await page.locator('#btn-wizard-next').click();
  await page.locator('#confirm-box').check();
  await page.locator('#btn-wizard-next').click();
  await page.waitForFunction(() => JSON.parse(localStorage.getItem('dain_stories')).length === 1 && !document.querySelector('#btn-wizard-next').disabled);
  return page.evaluate(() => JSON.parse(localStorage.getItem('dain_stories'))[0]);
}

for (const [name, options] of [
  ['network', {healthFailures:1}], ['HTTP failure', {healthStatus:503}], ['5 second timeout', {healthTimeout:true}],
]) {
  test('health banner appears for ' + name, async t => {
    const {page, errors} = await fixture(t, options);
    await page.waitForFunction(() => !document.querySelector('#verification-health-banner').hidden);
    assert.equal(await page.locator('#verification-health-banner').textContent(), 'Verification server unreachable at ' + API);
    assert.ok(await page.evaluate(() => window.__delays.includes(5000)));
    assert.deepEqual(errors, []);
  });
}

test('health succeeds, retries on reopening and hides an earlier failure', async t => {
  const {page, calls, errors} = await fixture(t, {healthFailures:1});
  await page.waitForFunction(() => !document.querySelector('#verification-health-banner').hidden);
  await page.evaluate(() => { switchView('home'); switchView('submit'); });
  await page.waitForFunction(() => document.querySelector('#verification-health-banner').hidden);
  assert.equal(calls.filter(call => call.path === '/health').length, 2);
  assert.deepEqual(errors, []);
});

test('a superseded health request cannot overwrite a successful retry', async t => {
  const {page, calls, errors} = await fixture(t, {superseded:true});
  const healthy = page.waitForResponse(response => response.url() === API + '/health' && response.status() === 200);
  await page.evaluate(() => { switchView('home'); switchView('submit'); });
  await healthy;
  await page.waitForFunction(() => window.__warnings.length === 0 && document.querySelector('#verification-health-banner').hidden);
  assert.equal(calls.filter(call => call.path === '/health').length, 2);
  assert.deepEqual(errors, []);
});

for (const [name, options, message, kind] of [
  ['network', {mode:'network'}, 'Could not reach the verification server (network or CORS)', 'network_or_cors'],
  ['CORS', {mode:'cors'}, 'Could not reach the verification server (network or CORS)', 'network_or_cors'],
  ['timeout', {mode:'timeout'}, 'The verification server took too long', 'timeout'],
  ['body timeout', {mode:'body_timeout'}, 'The verification server took too long', 'timeout'],
  ...[401, 403, 422, 429, 500].map(status => ['HTTP ' + status, {mode:'http', httpStatus:status}, 'Server returned ' + status, 'http_error']),
  ['invalid JSON', {mode:'invalid_json'}, 'The verification server returned an invalid response', 'invalid_json'],
  ['invalid schema', {mode:'invalid_schema'}, 'The verification server returned an invalid response', 'invalid_response'],
]) {
  test(name + ' is explained and held without logging story data', async t => {
    const {page, calls, errors} = await fixture(t, options);
    const story = await submit(page);
    assert.equal(story.status, 'Pending Review');
    assert.equal(story.reach, 0);
    assert.equal(story.verification.failureMessage, message);
    const results = await page.locator('#verification-results').textContent();
    assert.ok(results.includes(message));
    assert.ok(!results.includes('No checkable claims were returned'));
    assert.equal(await page.locator('#verification-results').evaluate(element => element.hidden), false);
    assert.equal(await page.locator('#view-submit').evaluate(element => element.classList.contains('active')), true);
    assert.equal(await page.locator('#headline').inputValue(), '');
    assert.ok(!(await page.locator('#toast-message').textContent()).includes('syndicated'));
    assert.equal(calls.filter(call => call.path === '/submissions/verify' && call.method === 'POST').length, 1);
    const warnings = await page.evaluate(() => window.__warnings);
    assert.ok(warnings.some(([label, detail]) => label === 'DAIN verification request failed' && detail.kind === kind));
    for (const value of [HEADLINE, SUMMARY, 'browser-test-token', 'DO_NOT_LOG_RESPONSE']) assert.ok(!JSON.stringify(warnings).includes(value));
    if (kind === 'timeout') assert.ok(await page.evaluate(() => window.__delays.includes(40000)));
    assert.deepEqual(errors, []);
  });
}

for (const status of ['verified', 'needs_review', 'verification_pending', 'rejected']) {
  test('real ' + status + ' results retain the existing submission behavior', async t => {
    const {page, errors} = await fixture(t, {status});
    const story = await submit(page);
    assert.equal(story.status, {verified:'Approved', rejected:'Rejected'}[status] || 'Pending Review');
    assert.deepEqual(story.verification, result(status));
    assert.equal(await page.locator('#verification-health-banner').evaluate(element => element.hidden), true);
    assert.deepEqual(errors, []);
  });
}

for (const status of ['needs_review', 'verified']) {
  test('unreadable link with search evidence is explained for ' + status, async t => {
    const response = result(status);
    response.reason = (status === 'verified' ? 'claims_verified' : 'insufficient_evidence') + '; evidence_link_unreadable';
    response.claims[0].confidence = status === 'verified' ? 0.9 : 0.6;
    const {page, errors} = await fixture(t, {response});
    const story = await submit(page);
    assert.equal(story.status, status === 'verified' ? 'Approved' : 'Pending Review');
    assert.deepEqual(story.verification, response);
    const results = await page.locator('#verification-results').textContent();
    assert.ok(results.includes(status === 'verified'
      ? "We couldn't open your evidence link; independent search sources support the claims."
      : "We couldn't open your evidence link; editorial review required"));
    assert.ok(!results.includes('invalid_api_response'));
    assert.ok(!results.includes('evidence_link_unreadable'));
    assert.ok(!results.includes('Not found online'));
    assert.ok(!results.includes('No eligible source links'));
    assert.ok(results.includes(status === 'verified' ? '90%' : '60%'));
    const link = page.locator('#verification-results .verification-sources a');
    assert.equal(await link.getAttribute('href'), response.claims[0].sources[0]);
    assert.equal(await link.getAttribute('target'), '_blank');
    assert.equal(await link.getAttribute('rel'), 'noopener noreferrer');
    if (status === 'needs_review') {
      assert.ok(results.includes('Not independently verified'));
      assert.equal(await page.locator('#verification-results .claim-badge').evaluate(element => getComputedStyle(element).color), 'rgb(71, 85, 105)');
      assert.ok(!(await page.locator('#toast-message').textContent()).includes('syndicated'));
      await page.evaluate(id => openPressKit(id), story.id);
      await page.waitForFunction(() => !document.querySelector('#dialog-body').classList.contains('hidden'));
      assert.ok((await page.locator('#dialog-body').textContent()).includes("We couldn't open your evidence link; editorial review required"));
    } else {
      assert.ok(!results.includes('editorial review required'));
    }
    assert.deepEqual(errors, []);
  });
}

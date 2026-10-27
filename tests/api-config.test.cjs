const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

const html = readFileSync(join(__dirname, '../index.html'), 'utf8');
const apiConfig = readFileSync(join(__dirname, '../api-config.js'), 'utf8');
const start = html.indexOf('const isLocalPage =');
const end = html.indexOf('function escapeHTML(', start);
assert.ok(start >= 0 && end > start);
const configuration = html.slice(start, end);
const API = 'https://dain-new.vercel.app';

function loadConfiguration(hostname, {loadFile=true, override}={}) {
  const errors = [];
  const context = vm.createContext({
    window: {location:{hostname}},
    console: {error(message) { errors.push(message); }},
  });
  if (loadFile) vm.runInContext(apiConfig, context);
  if (override !== undefined) context.window.DAIN_API_BASE = override;
  vm.runInContext(`${configuration}\nglobalThis.resolvedBase = API_BASE;`, context);
  return {base:context.resolvedBase, errors};
}

for (const hostname of ['neha-hub-maker.github.io', 'localhost', '127.0.0.1', '[::1]']) {
  test(`the shipped config targets this repository's Vercel API on ${hostname}`, () => {
    assert.deepEqual(loadConfiguration(hostname), {base:API, errors:[]});
  });
}

test('the relative API config loads before the app on the GitHub Pages repository path', () => {
  const scriptTag = '<script src="api-config.js"></script>';
  assert.ok(html.indexOf(scriptTag) >= 0 && html.indexOf(scriptTag) < start);
  assert.equal(new URL('api-config.js', 'https://neha-hub-maker.github.io/DAIN-New/').href,
    'https://neha-hub-maker.github.io/DAIN-New/api-config.js');
  const context = vm.createContext({window:{}});
  vm.runInContext(apiConfig, context);
  assert.equal(context.window.DAIN_API_BASE, API);
  assert.equal(new URL(context.window.DAIN_API_BASE).pathname, '/');
  assert.ok(!context.window.DAIN_API_BASE.endsWith('/'));
});

for (const hostname of ['localhost', '127.0.0.1', '[::1]']) {
  test(`without the shared config, local development on ${hostname} keeps its existing fallback`, () => {
    assert.deepEqual(loadConfiguration(hostname, {loadFile:false}), {base:'http://127.0.0.1:8000', errors:[]});
  });
}

for (const override of [undefined, '', '   ']) {
  test(`missing/blank production config reports an error (${JSON.stringify(override)})`, () => {
    const {base, errors} = loadConfiguration('neha-hub-maker.github.io', {loadFile:false, override});
    assert.equal(base, '');
    assert.equal(errors.length, 1);
    assert.match(errors[0], /api-config\.js/);
  });
}

test('the existing API_BASE logic trims whitespace and trailing slashes', () => {
  assert.deepEqual(loadConfiguration('neha-hub-maker.github.io', {override:` ${API}/// `}), {base:API, errors:[]});
});

const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const html = readFileSync(join(__dirname, "../index.html"), "utf8");
const start = html.indexOf("const DEPLOYED_API_BASE =");
const end = html.indexOf("function escapeHTML(", start);
assert.ok(start >= 0 && end > start);
const configuration = html.slice(start, end);

function loadConfiguration(hostname, override) {
  const warnings = [];
  const context = vm.createContext({
    window: { location: { hostname }, DAIN_API_BASE: override },
    console: { warn(message) { warnings.push(message); } },
  });
  vm.runInContext(`${configuration}\nglobalThis.resolvedBase = API_BASE;`, context);
  return { base: context.resolvedBase, warnings };
}

for (const hostname of ["localhost", "127.0.0.1", "[::1]"]) {
  test(`local development on ${hostname} uses the loopback API`, () => {
    assert.deepEqual(loadConfiguration(hostname), { base: "http://127.0.0.1:8000", warnings: [] });
  });
}

for (const hostname of ["dain.example.test", "localhost.example.test", ""]) {
  test(`unconfigured host '${hostname}' warns instead of using localhost`, () => {
    const { base, warnings } = loadConfiguration(hostname);
    assert.equal(base, "https://YOUR-DAIN-BACKEND.example.com");
    assert.equal(warnings.length, 1);
    assert.match(warnings[0], /window\.DAIN_API_BASE/);
  });
}

for (const hostname of ["localhost", "dain.example.test"]) {
  test(`window.DAIN_API_BASE overrides the default on ${hostname}`, () => {
    assert.deepEqual(loadConfiguration(hostname, " https://api.example.test/// "), {
      base: "https://api.example.test", warnings: [],
    });
  });
}

test("blank overrides do not silently resolve production to localhost", () => {
  const { base, warnings } = loadConfiguration("dain.example.test", " ");
  assert.equal(base, "https://YOUR-DAIN-BACKEND.example.com");
  assert.equal(warnings.length, 1);
});

test("editing the deployment constant configures a static deployment", () => {
  const context = vm.createContext({
    window: { location: { hostname: "dain.example.test" } },
    console: { warn() { assert.fail("Configured deployment should not warn"); } },
  });
  vm.runInContext(`${configuration.replace('const DEPLOYED_API_BASE = "https://YOUR-DAIN-BACKEND.example.com"', 'const DEPLOYED_API_BASE = "https://api.example.test"')}\nglobalThis.resolvedBase = API_BASE;`, context);
  assert.equal(context.resolvedBase, "https://api.example.test");
});

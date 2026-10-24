const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const html = readFileSync(join(__dirname, "../index.html"), "utf8");

// Run the actual inline handlers with DOM/network stubs; no browser dependencies.
function section(start, end) {
  const from = html.indexOf(start);
  const to = html.indexOf(end, from);
  assert.ok(from >= 0 && to > from, `Missing controller section: ${start}`);
  return html.slice(from, to);
}

function loadRegistration(email) {
  const requests = [];
  const elements = new Map();
  const values = {
    "register-email": email,
    "login-email": email,
    "author-email": email,
    "register-name": "Test Student",
    "register-role": "Student",
    "register-password": "secure-password-123",
    "login-password": "secure-password-123",
    "achievement-date": "2026-10-23",
    institution: "University of Dhaka",
  };
  const context = vm.createContext({
    API_BASE: "http://127.0.0.1:8000",
    pipelineBusy: false,
    sessionStorage: { removeItem() {}, setItem() {} },
    document: {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, {
          value: values[id],
          classList: { toggle(_name, hidden) { this.hidden = hidden; } },
        });
        return elements.get(id);
      },
    },
    async fetch(url, options) {
      requests.push({ url, body: JSON.parse(options.body) });
      return { ok: true, async json() { return { access_token: "test-session-token" }; } };
    },
    showToast() {},
    completeAuthSuccess() {},
    clearErrorHighlights() {},
    highlightErrorField() {},
    updateWizardUI() {},
    wizardStep: 2,
    btnNext: { addEventListener(_event, handler) { context.nextStep = handler; } },
  });
  context.window = context;
  vm.runInContext(section("window.isDUInstitutionalEmail =", "window.openAuthModal ="), context);
  vm.runInContext(section("window.handleLoginSubmit =", "window.loginAsDemo ="), context);
  vm.runInContext(section("if (btnNext) {", "if (btnBack) {"), context);
  return { context, requests, elements };
}

const accepted = [
  "student@du.ac.bd",
  "student-2024913694@cs.du.ac.bd",
  "student-19th-2023112801@mis.du.ac.bd",
  "student@another-department.du.ac.bd",
  "student@students.cs.du.ac.bd",
  "  student@CS.DU.AC.BD  ",
];
const rejected = [
  "student@gmail.com",
  "student@evildu.ac.bd",
  "student@csdu.ac.bd",
  "student@du.ac.bd.example.com",
  "student@cs.du.ac.bd.example.com",
  "student@du-ac-bd.com",
  "student@cs..du.ac.bd",
  "student@-cs.du.ac.bd",
  "student@cs-.du.ac.bd",
  "student@@cs.du.ac.bd",
  "@cs.du.ac.bd",
  "student name@cs.du.ac.bd",
];

for (const [allowed, emails] of [[true, accepted], [false, rejected]]) {
  for (const email of emails) {
    test(`${allowed ? "accepts" : "rejects"} ${email.trim()} throughout the frontend`, async () => {
      const { context, requests, elements } = loadRegistration(email);
      context.checkRegisterEmail(email);
      assert.equal(elements.get("register-du-badge").classList.hidden, !allowed);
      await context.handleRegisterSubmit({ preventDefault() {} });
      await context.handleLoginSubmit({ preventDefault() {} });
      assert.equal(requests.length, allowed ? 2 : 0);
      if (allowed) {
        assert.ok(requests[0].url.endsWith("/auth/register"));
        assert.ok(requests[1].url.endsWith("/auth/login"));
        assert.equal(requests[0].body.email, email.trim());
        assert.equal(requests[1].body.email, email.trim());
      }
      context.nextStep();
      assert.equal(context.wizardStep, allowed ? 3 : 2);
    });
  }
}

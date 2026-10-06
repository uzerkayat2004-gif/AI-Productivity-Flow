// Runtime status regressions using the production auth/status functions and a fake DOM.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const appSource = fs.readFileSync(path.join(__dirname, '../src/voice_flow/gui/app.js'), 'utf8');
const videoSource = fs.readFileSync(path.join(__dirname, '../src/voice_flow/gui/video-flow.js'), 'utf8');
const section = (source, start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));

function makeElement() {
  const classes = new Set();
  return {
    className: '', textContent: '', title: '', disabled: false, dataset: {}, onclick: null,
    classList: {
      add(...names) { names.forEach(name => classes.add(name)); },
      remove(...names) { names.forEach(name => classes.delete(name)); },
      toggle(name, force) {
        const shouldAdd = force === undefined ? !classes.has(name) : Boolean(force);
        if (shouldAdd) classes.add(name); else classes.delete(name);
        return shouldAdd;
      },
      contains(name) { return classes.has(name); },
      [Symbol.iterator]() { return classes[Symbol.iterator](); },
    },
  };
}

function harness(response) {
  const ids = [
    'vf-nlm-status-badge', 'vf-nlm-status-dot', 'vf-nlm-status-text', 'vf-nlm-login-btn',
    'vf-nlm-login-label', 'vf-nlm-disconnect-btn', 'vf-nlm-account-desc', 'vf-nlm-check-btn',
    'vf-nlm-check-label', 'vf-nlm-check-icon', 'af-summary-connection-status',
    'af-summary-status-badge',
  ];
  const elements = new Map(ids.map(id => [id, makeElement()]));
  const statusRequests = [];
  const extraFetches = [];
  const context = vm.createContext({
    console: { warn() {}, error() {} },
    document: { getElementById: id => elements.get(id) || null, visibilityState: 'visible' },
    window: { setTimeout, addEventListener() {} },
    setTimeout: () => 1,
    clearTimeout() {},
    setInterval: () => 2,
    clearInterval() {},
    safeFetchJson: async url => { statusRequests.push(url); return response; },
    fetch: async (...args) => { extraFetches.push(args); throw new Error('unexpected fetch'); },
    clearNlmRecoveryPollTimer() {},
    vfToast() {},
    cleanErrorMessage: String,
    vfFlowStatusMod: key => key,
  });
  context.vfNlmAuthStatus = {
    authenticated: false, account_saved: true, online_verified: null, checking: false,
    email: 'reader@example.com', profile: 'video-flow-experiment',
  };
  context.vfNlmAuthRequestSequence = 0;
  context.vfNlmAuthInProgress = false;
  context.vfNlmRecoveryPollTimer = null;
  context.vfNlmRecoveryPollCount = 0;
  context.vfNlmAuthPollTimer = null;

  vm.runInContext(section(appSource, 'function _afMapNlmState', 'try {\n  window.addEventListener("focus"'), context);
  vm.runInContext(section(videoSource, 'function vfNotebookLMConnectionState', 'async function syncNotebookLMBrowser()'), context);
  return { context, elements, statusRequests, extraFetches };
}

test('transient unknown state says connection delayed without claiming offline, expired, or connected', async () => {
  const h = harness({
    success: true, account_saved: true, online_verified: null,
    recovery_state: 'transient_error', verification_unavailable: true,
    email: 'reader@example.com',
  });
  await h.context.checkNotebookLMAuth(false);

  assert.equal(h.elements.get('vf-nlm-status-text').textContent, 'Connection delayed');
  assert.equal(h.elements.get('vf-nlm-login-label').textContent, 'Retry now');
  assert.match(h.elements.get('vf-nlm-account-desc').textContent, /saved account is safe.*retry automatically/i);
  assert.equal(h.elements.get('af-summary-connection-status').textContent, 'Connection delayed');
  for (const id of ['vf-nlm-status-text', 'af-summary-connection-status']) {
    assert.doesNotMatch(h.elements.get(id).textContent, /offline|expired|connected/i);
  }
  assert.deepEqual(h.statusRequests, ['/api/video-flow/notebooklm/status?verify=1']);
  assert.deepEqual(h.extraFetches, []);
});

test('passive status recovery updates Video Flow and both audio summary badges without another check', async () => {
  const h = harness({
    success: true, account_saved: true, authenticated: true, online_verified: true,
    recovery_state: null, email: 'reader@example.com',
  });
  await h.context.checkNotebookLMAuth(false);

  assert.equal(h.elements.get('vf-nlm-status-text').textContent, 'Connected: reader@example.com');
  assert.equal(h.elements.get('af-summary-connection-status').textContent, 'Connected · reader@example.com');
  assert.equal(h.elements.get('af-summary-status-badge').textContent, 'Connected · reader@example.com');
  assert.deepEqual(h.statusRequests, ['/api/video-flow/notebooklm/status?verify=1']);
  assert.deepEqual(h.extraFetches, []);
});

test('audio summary state mapping describes transient errors as delayed connection', () => {
  const context = vm.createContext({});
  vm.runInContext(section(appSource, 'function _afMapNlmState', 'function updateAudioSummaryConnectionUI'), context);
  const mapped = context._afMapNlmState({ account_saved: true, online_verified: null, recovery_state: 'transient_error' });
  assert.deepEqual({ key: mapped.key, label: mapped.label }, { key: 'attention', label: 'Connection delayed' });
});

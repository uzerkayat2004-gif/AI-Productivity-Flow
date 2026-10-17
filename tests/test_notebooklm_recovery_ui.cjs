// Runtime status regressions using the production auth/status functions and a fake DOM.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const appSource = fs.readFileSync(path.join(__dirname, '../src/voice_flow/gui/app.js'), 'utf8').replace(/\r\n/g, '\n');
const videoSource = fs.readFileSync(path.join(__dirname, '../src/voice_flow/gui/video-flow.js'), 'utf8').replace(/\r\n/g, '\n');
const section = (source, start, end) => {
  const from = source.indexOf(start);
  const to = from < 0 ? -1 : source.indexOf(end, from);
  if (from < 0 || to < 0) {
    throw new Error(`UI section not found (${start} .. ${end})`);
  }
  return source.slice(from, to);
};

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

function signInHarness() {
  const ids = [
    'vf-nlm-status-badge', 'vf-nlm-status-dot', 'vf-nlm-status-text', 'vf-nlm-login-btn',
    'vf-nlm-login-label', 'vf-nlm-disconnect-btn', 'vf-nlm-disconnect-label', 'vf-nlm-account-desc',
    'vf-nlm-cancel-login-btn', 'vf-nlm-show-signin-btn',
  ];
  const elements = new Map(ids.map(id => [id, makeElement()]));
  elements.get('vf-nlm-cancel-login-btn').classList.add('hidden');
  const requests = [];
  const toasts = [];
  const timers = [];
  let loginState = {
    running: true, started_at: 1, success: null, window_opened: null, error: null, note: null,
  };
  const context = vm.createContext({
    console: { warn() {}, error() {} },
    document: { getElementById: id => elements.get(id) || null, visibilityState: 'visible' },
    setTimeout(fn) { timers.push(fn); return timers.length; },
    clearTimeout() {},
    setInterval: () => 3,
    clearInterval() {},
    safeFetchJson: async (url, opts) => {
      requests.push({ url: String(url), body: opts && opts.body ? JSON.parse(opts.body) : null });
      if (String(url).includes('/auth/start')) return { success: true, launched: true };
      if (String(url).includes('/auth/state')) return { success: true, login: loginState };
      if (String(url).includes('/auth/cancel')) return { success: true, cancelled: true };
      if (String(url).includes('/auth/disconnect')) return { success: true };
      return { success: true, account_saved: false, online_verified: false, available: true, email: null };
    },
    vfToast(message, isError) { toasts.push({ message: String(message), isError: Boolean(isError) }); },
    cleanErrorMessage: String,
    clearNlmRecoveryPollTimer() {},
    clearNlmAuthPollTimer() {
      context.vfNlmAuthPollTimer = null;
    },
  });
  context.vfNlmAuthStatus = {
    authenticated: false, account_saved: false, online_verified: null, checking: false,
    email: null, profile: 'video-flow-experiment', available: true,
  };
  context.vfNlmAuthRequestSequence = 0;
  context.vfNlmAuthInProgress = false;
  context.vfNlmAuthFocusDelayTimer = null;
  context.vfNlmAuthPollTimer = null;
  context.vfNlmRecoveryPollTimer = null;
  context.vfNlmRecoveryPollCount = 0;
  vm.runInContext(
    section(videoSource, 'function vfNotebookLMConnectionState', 'const VF_PERMANENT_CONFIRMATION'),
    context,
  );
  return {
    context, elements, requests, toasts, timers,
    setLoginState(next) { loginState = next; },
    async flush() {
      while (timers.length) {
        const fn = timers.shift();
        if (fn) await fn();
      }
    },
  };
}

test('sign-in shows waiting and cancel, and a second click does not start another login', async () => {
  const h = signInHarness();
  const first = h.context.startNotebookLMAuth(false);
  const second = h.context.startNotebookLMAuth(false);
  await first;
  await second;
  assert.equal(h.requests.filter(req => req.url.includes('/auth/start')).length, 1);
  assert.equal(h.elements.get('vf-nlm-status-text').textContent, 'Waiting for Google sign-in…');
  assert.equal(h.elements.get('vf-nlm-cancel-login-btn').classList.contains('hidden'), false);

  await h.context.cancelNotebookLMAuth();
  assert.equal(h.requests.filter(req => req.url.includes('/auth/cancel')).length, 1);
  assert.match(h.toasts.at(-1).message, /cancelled/i);
  assert.equal(h.elements.get('vf-nlm-cancel-login-btn').classList.contains('hidden'), true);
});

test('immediate sign-in failure shows the child error instead of a finished-window message', async () => {
  const h = signInHarness();
  h.setLoginState({
    running: false,
    started_at: 1,
    success: false,
    window_opened: false,
    cancelled: false,
    error: 'The Google sign-in window did not open (exit 1): chrome failed to launch',
  });
  await h.context.startNotebookLMAuth(false);
  await h.flush();
  assert.equal(h.toasts.length, 1);
  assert.match(h.toasts[0].message, /did not open/);
  assert.match(h.toasts[0].message, /chrome failed to launch/);
  assert.doesNotMatch(h.toasts[0].message, /Choose your Google account in the Chrome sign-in window/);
  assert.equal(h.toasts[0].isError, true);
});

test('switch account sends switch_account and sign out returns to not connected', async () => {
  const h = signInHarness();
  h.context.vfNlmAuthStatus = {
    authenticated: true, account_saved: true, online_verified: true, checking: false,
    email: 'reader@example.com', profile: 'video-flow-experiment', available: true,
  };
  const pending = h.context.startNotebookLMAuth(true);
  await pending;
  const start = h.requests.find(req => req.url.includes('/auth/start'));
  assert.equal(start.body.switch_account, true);
  assert.equal(start.body.mode, 'cli');

  h.context.vfNlmAuthInProgress = false;
  await h.context.disconnectNotebookLM();
  const disconnect = h.requests.find(req => req.url.includes('/auth/disconnect'));
  assert.ok(disconnect);
  assert.equal(disconnect.body.profile, 'video-flow-experiment');
  assert.equal(h.elements.get('vf-nlm-status-text').textContent, 'Not connected');
  assert.equal(h.elements.get('vf-nlm-login-label').textContent, 'Sign in with Google');
});

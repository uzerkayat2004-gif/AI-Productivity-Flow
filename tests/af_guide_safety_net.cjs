// Node harness for the Audio Flow guide safety net (run by test_mac_launch_fixes.py).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const app = fs.readFileSync(path.join(__dirname, '../src/voice_flow/gui/app.js'), 'utf8');
const start = app.indexOf('let _afGuideNarrationPaused');
// Keep this harness scoped to Audio Flow guide helpers only (Video/Voice guides follow).
let end = app.indexOf('// VIDEO FLOW IN-APP GUIDANCE ENGINE');
if (end < 0) end = app.indexOf('function replayOnboarding()');
assert.ok(start > 0 && end > start, 'guide section not found');
const section = app.slice(start, end);

function classList(initial) {
  const set = new Set(initial);
  return { add: (...n) => n.forEach(x => set.add(x)), remove: (...n) => n.forEach(x => set.delete(x)), contains: n => set.has(n) };
}

function harness({ position, cardRect }) {
  const listeners = new Map();
  const target = () => ({
    addEventListener(type, fn) { listeners.set(type + ':' + fn.name, fn); },
    removeEventListener(type, fn) { listeners.delete(type + ':' + fn.name); },
  });
  const overlay = { classList: classList(['hidden']) };
  const card = { classList: classList([]), contains: () => false, getBoundingClientRect: () => cardRect };
  const ids = { 'audioflow-guide-overlay': overlay, 'af-guide-card': card };
  const doc = Object.assign(target(), {
    getElementById: id => ids[id] || null,
    querySelector: () => null,
    querySelectorAll: () => [],
    body: { classList: classList([]), scrollTop: 0 },
    documentElement: { scrollTop: 0, clientWidth: 1024, clientHeight: 768 },
    activeElement: null,
  });
  const win = Object.assign(target(), {
    innerWidth: 1024, innerHeight: 768, scrollY: 0, scrollTo() {},
    getComputedStyle: el => (el === overlay ? { position, display: 'block', visibility: 'visible' } : { display: 'block', visibility: 'visible' }),
  });
  const flags = {};
  const ctx = vm.createContext({
    window: win, document: doc, console: { warn() {}, log() {}, error() {} },
    setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
    switchPage() {}, setOnboardingFlag: (k, v) => { flags[k] = v; },
    currentAudioProvider: 'edge', afSummaries: [1], Audio: function () {},
  });
  vm.runInContext(section, ctx);
  vm.runInContext('gotoAudioFlowGuideStep = function () {}; stopAudioFlowGuideAudio = function () {}; stopVideoFlowGuide = function () {}; stopVoiceFlowGuide = function () {};', ctx);
  return { ctx, listeners, overlay, flags };
}

// 1. Missing stylesheet (overlay is position:static): the guide never starts.
{
  const h = harness({ position: 'static', cardRect: { width: 0, height: 0, left: 0, top: 0, right: 0, bottom: 0 } });
  vm.runInContext('startAudioFlowGuide({ auto: true })', h.ctx);
  assert.equal(h.listeners.size, 0, 'no blockers may be attached without guide styles');
  assert.ok(h.overlay.classList.contains('hidden'));
}

// 2. Styled overlay but the card never becomes visible: first click releases the lock.
{
  const h = harness({ position: 'fixed', cardRect: { width: 0, height: 0, left: 0, top: 0, right: 0, bottom: 0 } });
  vm.runInContext('startAudioFlowGuide()', h.ctx);
  const blocker = h.listeners.get('click:_afGuideBlockAppEvent');
  assert.ok(blocker, 'blockers attach when styles are present');
  let prevented = false;
  blocker({ target: {}, preventDefault() { prevented = true; }, stopPropagation() {}, stopImmediatePropagation() {} });
  assert.equal(prevented, false, 'click must reach the app when the card is invisible');
  assert.equal(h.listeners.size, 0, 'all blockers removed');
  assert.ok(h.overlay.classList.contains('hidden'));
  assert.notEqual(h.flags['vf_onboarding.af_guided'], '1', 'an unseen guide stays pending');
}

// 3. Visible, styled card: the guide still guards the app (behaviour unchanged).
{
  const h = harness({ position: 'fixed', cardRect: { width: 360, height: 220, left: 600, top: 400, right: 960, bottom: 620 } });
  vm.runInContext('startAudioFlowGuide()', h.ctx);
  let prevented = false;
  h.listeners.get('click:_afGuideBlockAppEvent')({ target: {}, preventDefault() { prevented = true; }, stopPropagation() {}, stopImmediatePropagation() {} });
  assert.equal(prevented, true);
}
console.log('af-guide-safety-net: ok');

// Exercise production preference functions with a fake DOM; no browser.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../src/voice_flow/gui/app.js'), 'utf8');
const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise(r => resolve = r); return { promise, resolve }; };
const reply = value => ({ ok: true, json: async () => value });

function harness(initial = true) {
  const toggle = { checked: initial };
  const cache = new Map([['vf_polishing_enabled', String(initial)]]);
  const requests = [];
  const context = vm.createContext({
    console: { error() {}, warn() {} },
    document: { getElementById: id => id === 'toggle-polishing' ? toggle : null },
    localStorage: { getItem: k => cache.has(k) ? cache.get(k) : null, setItem: (k, v) => cache.set(k, v) },
    fetch: (url, opts) => { const pending = deferred(); requests.push({ url, opts, ...pending }); return pending.promise; },
    featureStates: {}, applyFeatureDisabledUI() {}, vfToast() {},
  });
  vm.runInContext(section('let polishingToggleRevision', 'async function toggleClickToPasteSetting'), context);
  vm.runInContext(section('async function loadFeatureToggleStates()', '// --- Reading speed'), context);
  return { context, toggle, cache, requests };
}

test('rapid on/off writes are serialized and latest preference survives reload', async () => {
  const h = harness(false);
  const on = h.context.togglePolishingSetting(true);
  const off = h.context.togglePolishingSetting(false);
  await tick();
  assert.equal(h.requests.length, 1);
  assert.equal(JSON.parse(h.requests[0].opts.body).value, true);
  h.requests[0].resolve(reply({ success: true }));
  await tick();
  assert.equal(h.requests.length, 2);
  assert.equal(JSON.parse(h.requests[1].opts.body).value, false);
  h.requests[1].resolve(reply({ success: true }));
  await Promise.all([on, off]);
  assert.equal(h.toggle.checked, false);
  assert.equal(h.cache.get('vf_polishing_enabled'), 'false');
});

for (const startedDuringWrite of [false, true]) {
  test(`stale settings response cannot re-enable polishing (during write: ${startedDuringWrite})`, async () => {
    const h = harness(true);
    let loading;
    if (!startedDuringWrite) loading = h.context.loadFeatureToggleStates();
    const saving = h.context.togglePolishingSetting(false);
    await tick();
    if (startedDuringWrite) loading = h.context.loadFeatureToggleStates();
    const write = h.requests.find(r => r.opts);
    write.resolve(reply({ success: true }));
    await saving;
    h.requests.filter(r => !r.opts).forEach(r => r.resolve(reply({ success: true, value: true })));
    await loading;
    assert.equal(h.toggle.checked, false);
    assert.equal(h.cache.get('vf_polishing_enabled'), 'false');
  });
}

test('failed first save rolls back to cached confirmed value, not changed checkbox', async () => {
  const h = harness(false);
  h.toggle.checked = true; // native onchange has already run
  const saving = h.context.togglePolishingSetting(true);
  await tick();
  h.requests[0].resolve({ ok: false, json: async () => ({ success: false, error: 'disk failure' }) });
  await saving;
  assert.equal(h.toggle.checked, false);
  assert.equal(h.cache.get('vf_polishing_enabled'), 'false');
});

test('a new page reads persisted OFF', async () => {
  const h = harness(true);
  const loading = h.context.loadFeatureToggleStates();
  h.requests.forEach(r => r.resolve(reply({ success: true, value: !r.url.includes('polishing_enabled') })));
  await loading;
  assert.equal(h.toggle.checked, false);
});

test('dictionary refresh cannot replace a newer list with a late response', async () => {
  const requests = [];
  const rendered = [];
  const context = vm.createContext({
    console,
    document: { getElementById: id => id === 'dictionary-chips' ? {} : null },
    fetch: url => { const pending = deferred(); requests.push({ url, ...pending }); return pending.promise; },
  });
  vm.runInContext(section('let allDictionaryWords', 'function filterDictionaryChips()'), context);
  context.loadDictionarySuggestions = async () => {};
  context.renderDictionaryFilteredChips = () => rendered.push(vm.runInContext('allDictionaryWords.map(dictionaryWord)', context).join(','));
  const oldLoad = context.loadDictionary();
  await tick();
  const newLoad = context.loadDictionary();
  await tick();
  requests[2].resolve(reply([{ word: 'NewSpelling', category: 'Personal' }]));
  requests[3].resolve(reply([]));
  await newLoad;
  requests[0].resolve(reply([{ word: 'OldSpelling', category: 'Personal' }]));
  requests[1].resolve(reply([]));
  await oldLoad;
  assert.deepEqual(rendered, ['NewSpelling']);
});

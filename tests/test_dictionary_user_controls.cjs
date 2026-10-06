// Offline UI regressions for automatic vocabulary and heard-as controls.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../src/voice_flow/gui/app.js'), 'utf8');
const page = fs.readFileSync(path.join(__dirname, '../src/voice_flow/gui/index.html'), 'utf8');
const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
const reply = value => ({ ok: true, json: async () => value });
const tick = () => new Promise(resolve => setImmediate(resolve));

function harness(responses = {}) {
  const elements = new Map();
  const getElement = id => {
    if (!elements.has(id)) elements.set(id, { id, value: '', textContent: '', innerHTML: '', style: {}, focus() {}, select() {} });
    return elements.get(id);
  };
  const requests = [];
  const context = vm.createContext({
    console: { error() {}, warn() {} },
    document: { getElementById: getElement, querySelector: () => ({ classList: { add() {}, remove() {} } }), createElement: () => ({ setAttribute() {}, addEventListener() {}, focus() {}, replaceWith() {} }) },
    fetch: async (url, options) => { requests.push({ url, options }); return reply(responses[url] || []); },
    showToast() {},
  });
  // Exercise the actual HTML encoders: substitutes can hide attribute bugs.
  vm.runInContext(section('function escapeHtml(str)', '// Ensure vfToast'), context);
  vm.runInContext(section('let allDictionaryWords = []', 'function getDictionaryCasingBadge'), context);
  vm.runInContext(section('function getDictionaryCasingBadge', 'function clearDictionarySearch'), context);
  vm.runInContext(section('let dictionaryAddBusy = false', 'async function addDictionaryWord()'), context);
  context.setDictionaryAddError = () => {};
  return { context, elements, requests, getElement };
}

test('opening the dictionary GETs active words and corrections without a suggestions dependency', async () => {
  const h = harness({
    '/api/dictionary?details=1': [
      { id: 1, word: 'HyperKube', category: 'Personal' },
      { id: 2, word: 'LangGraph', category: 'Learned' },
      { id: 3, word: 'junkword', category: 'Auto-Captured' },
    ],
    '/api/dictionary/corrections': [],
  });
  await h.context.loadDictionary();

  assert.ok(h.requests.every(request => !request.options || request.options.method === 'GET'));
  assert.deepEqual(h.requests.map(request => request.url).sort(), ['/api/dictionary/corrections', '/api/dictionary?details=1'].sort());
  assert.deepEqual(vm.runInContext('allDictionaryWords.map(entry => entry.word)', h.context), ['HyperKube', 'LangGraph']);
  assert.match(h.getElement('dictionary-chips').innerHTML, /LangGraph/);
  assert.equal(h.getElement('dict-active-count').textContent, '2');
  assert.doesNotMatch(source, /loadDictionarySuggestions|decideDictionarySuggestion|approveDictionaryWord|suggestions\/decide/);
  assert.doesNotMatch(page, /dictionary-suggestions-card|Suggested words|Approve words Flow should learn/);
  assert.match(page, /Useful names and technical terms are added automatically after repeated use/);
  assert.match(page, /polishing on or off/i);
  assert.match(page, /manual add is optional/i);
  assert.match(source, /Flow learns useful words as you dictate\. You can also add a word above\./);
});

test('saved active word displays its escaped heard-as correction and edit control', () => {
  const h = harness();
  vm.runInContext(`allDictionaryWords = [{ word: "O'NeilSDK", category: 'Personal' }]; dictionaryHeardAs = { "o'neilsdk": [{ id: 3, wrong: "Oh Neil's D K" }] };`, h.context);
  h.context.renderDictionaryFilteredChips();
  const html = h.getElement('dictionary-chips').innerHTML;
  assert.match(html, /Heard as: Oh Neil(?:&#39;|')s D K/);
  assert.match(html, /Edit heard-as/);
  assert.match(html, /O(?:&#39;|')NeilSDK/);
});

test('entity-like word is passed unchanged by the decoded delete handler', () => {
  const h = harness();
  const word = "O&#39;NeilSDK & Sons";
  vm.runInContext(`allDictionaryWords = [{ word: ${JSON.stringify(word)}, category: 'Personal' }];`, h.context);
  h.context.renderDictionaryFilteredChips();
  const attribute = h.getElement('dictionary-chips').innerHTML.match(/onclick="([^"]*removeDictionaryWord[^" ]*[^\"]*)"/)[1];
  const decoded = attribute.replace(/&(?:amp|quot|lt|gt|#39);/g, entity => ({
    '&amp;': '&', '&quot;': '"', '&lt;': '<', '&gt;': '>', '&#39;': "'",
  }[entity]));
  let received;
  h.context.event = { stopPropagation() {} };
  h.context.removeDictionaryWord = value => { received = value; };
  vm.runInContext(decoded, h.context);
  assert.equal(received, word);
});

test('heard-as phrase can be searched even when it differs from the saved word', () => {
  const h = harness();
  vm.runInContext(`allDictionaryWords = [{ word: 'Kubernetes' }]; dictionaryHeardAs = { kubernetes: [{ id: 1, wrong: 'cuber netties' }] };`, h.context);
  h.getElement('dictionary-search-input').value = 'cuber';
  h.context.renderDictionaryFilteredChips();
  assert.match(h.getElement('dictionary-chips').innerHTML, /Kubernetes/);
});

test('legacy text-expansion shortcut does not offer spelling correction controls', () => {
  const h = harness();
  vm.runInContext(`allDictionaryWords = [{ word: 'myemail -> me@company.com' }];`, h.context);
  h.context.renderDictionaryFilteredChips();
  const html = h.getElement('dictionary-chips').innerHTML;
  assert.match(html, /me@company.com/);
  assert.doesNotMatch(html, /startDictionaryHeardAsEdit|Add heard-as/);
});

test('adding a word sends the optional heard-as phrase with the same save request', async () => {
  const h = harness();
  h.getElement('dictionary-add-input').value = 'HyperKube';
  h.getElement('dictionary-heard-as-input').value = 'Hyper cube';
  h.getElement('dictionary-casing').value = 'keep';
  h.context.loadDictionary = async () => {};
  h.context.addDictionaryWordFromInput = h.context.addDictionaryWordFromInput || (() => {});
  await h.context.addDictionaryWordFromInput();
  const write = h.requests.find(request => request.url === '/api/dictionary/add');
  assert.ok(write);
  assert.deepEqual(JSON.parse(write.options.body), { word: 'HyperKube', heard_as: 'Hyper cube' });
});

test('manually adding a Learned word reaches the API so it can become explicit', async () => {
  const h = harness({ '/api/dictionary/add': { success: true } });
  vm.runInContext(`allDictionaryWords = [{ word: 'LangGraph', category: 'Learned' }];`, h.context);
  h.getElement('dictionary-add-input').value = 'LangGraph';
  h.getElement('dictionary-casing').value = 'keep';
  h.context.loadDictionary = async () => {};

  await h.context.addDictionaryWordFromInput();

  const write = h.requests.find(request => request.url === '/api/dictionary/add');
  assert.ok(write, 'a Learned entry should not be blocked as a duplicate');
  assert.deepEqual(JSON.parse(write.options.body), { word: 'LangGraph', heard_as: '' });
});

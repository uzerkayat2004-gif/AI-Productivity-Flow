const fs = require('fs');
const assert = require('assert');

let code = fs.readFileSync('src/voice_flow/gui/video-flow.js', 'utf8');

let gridContent = '';
const mockGrid = {
  set innerHTML(val) { gridContent = val; },
  get innerHTML() { return gridContent; },
  style: {}
};
const mockEmpty = { style: {} };
const mockCount = { textContent: '' };
const mockStepper = {
  classList: {
    remove: () => {},
    add: () => {},
    contains: () => true
  },
  querySelector: () => null,
  appendChild: () => {}
};

global.document = {
  getElementById: (id) => {
    if (id === 'vf-history-grid') return mockGrid;
    if (id === 'vf-history-empty') return mockEmpty;
    if (id === 'vf-history-count') return mockCount;
    if (id === 'vf-generation-stepper') return mockStepper;
    return null;
  },
  querySelectorAll: () => [],
  querySelector: () => null
};
global.window = {
  setInterval: () => 123,
  clearInterval: () => {}
};

// Evaluate with test code appended
const testRunner = `
vfVideos = [
  {
    id: 'test-1',
    title: 'Completed Test',
    status: 'completed',
    timings: { total: 84, upload: 3, cloud_ai: 78, download: 3 }
  },
  {
    id: 'test-2',
    title: 'Generating Test',
    status: 'processing',
    progress: 45,
    stage: 'Generating cloud video...'
  },
  {
    id: 'test-3',
    title: 'Meta Timings Test',
    status: 'completed',
    meta: { timings: { total: '1m 24s', upload: '3s', cloud_ai: '1m 18s', download: '3s' } }
  }
];

renderVideoHistory();
`;

eval(code + '\n' + testRunner);

console.log('--- Rendered Video History Grid Snippet ---');
console.log(gridContent.substring(0, 700));

assert(gridContent.includes('vf-timing-pill'), 'Should include .vf-timing-pill');
assert(gridContent.includes('⚡'), 'Should include lightning bolt');
assert(gridContent.includes('1m 24s'), 'Should include total timing 1m 24s');
assert(gridContent.includes('Upload: 3s'), 'Should include Upload: 3s');
assert(gridContent.includes('Cloud AI: 1m 18s'), 'Should include Cloud AI: 1m 18s');
assert(gridContent.includes('Download: 3s'), 'Should include Download: 3s');
console.log('\n--- Testing Live Stopwatch Ticking ---');
const testLiveStopwatch = `
vfLiveTimerStartTime = Date.now() - 34000;
let updatedTimerText = '';
const mockLiveTimer = {
  style: {},
  set innerHTML(val) { updatedTimerText = val; },
  get innerHTML() { return updatedTimerText; },
  setAttribute: () => {}
};
document.getElementById = (id) => {
  if (id === 'vf-live-timer') return mockLiveTimer;
  return null;
};
vfUpdateLiveTimer({ stage: 'video_poll' });
assert(updatedTimerText.includes('0:34 elapsed'), 'Should include 0:34 elapsed');
assert(updatedTimerText.includes('Generating in Cloud AI...'), 'Should include Generating in Cloud AI...');
`;

eval(code + '\n' + testLiveStopwatch);
assert(gridContent.includes('vf-card-live-timer'), 'Should include vf-card-live-timer');
assert(gridContent.includes('Generating in Cloud AI...'), 'Should include Generating in Cloud AI...');

console.log('\n--- Testing CSS rules in video-flow.css ---');
const css = fs.readFileSync('src/voice_flow/gui/video-flow.css', 'utf8');
assert(css.includes('.vf-timing-pill'), 'CSS should include .vf-timing-pill');
assert(css.includes('.vf-live-timer'), 'CSS should include .vf-live-timer');
assert(css.includes('backdrop-filter: blur('), 'CSS should include backdrop-filter blur');
assert(css.includes('border: 1px solid rgba('), 'CSS should include subtle border');

console.log('\nAll SPECIALIST 4 assertions verified successfully!');

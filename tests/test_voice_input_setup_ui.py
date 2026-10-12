"""Offline renderer regression loops; only the bounded settings source is evaluated."""
from pathlib import Path
import subprocess

SOURCE = Path(__file__).parents[1] / "src/voice_flow/gui/app.js"


def test_voice_input_settings_renderer():
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('// --- User-Configurable Trigger & Hotkey Settings ---');
const end = source.indexOf('// Home Page Data Aggregator', start);
assert(start >= 0 && end > start);
const nodes = new Map();
function node(id) {
  if (!nodes.has(id)) {
    const classes = new Set(id.endsWith('modal') ? [] : []);
    nodes.set(id, { value: id === 'custom-hotkey-input' ? 'Alt+Space' : '',
      textContent: '', innerHTML: '', title: '', checked: true, disabled: false,
      dataset: {}, style: {}, scrollIntoView() {}, setAttribute() {},
      classList: { add(x) {classes.add(x)}, remove(x) {classes.delete(x)}, contains(x) {return classes.has(x)} } });
  }
  return nodes.get(id);
}
const listeners = new Map();
const calls = [];
let failSettings = true;
let failMic = true;
let catalog = {success:true,devices:[],preferred:null,preferred_available:true,selected_identity:null};
let pendingBegin = null;
let hotkeyGet = null;
let hotkeyPost = null;
let microphoneGet = null;
let microphoneSavedName = "Windows default microphone";
const saved = {success:true,hotkey_trigger:'custom',custom_hotkey:'Alt+Space',custom_trigger_type:'hold',dictation_trigger_mode:'hybrid',middle_click_enabled:true};
const context = {
 document: { getElementById: node, querySelectorAll() {return []} },
 window: {addEventListener(k,f){listeners.set(k,f)},removeEventListener(k,f){if(listeners.get(k)===f)listeners.delete(k)}},
 console: {error(){},warn(){}}, setTimeout(){return 1},clearTimeout(){},setInterval(){return 1},clearInterval(){},
 escapeHtml: x=>String(x), escapeJs: x=>String(x), vfToast(){},
 safeFetchJson: async (url, options) => {
  calls.push({url,options});
  if(url.endsWith('/recorder')) {const body=JSON.parse(options.body);if(body.action==='begin'&&pendingBegin)return pendingBegin;return {success:true,token:'offline-token'};}
  if(url==='/api/microphones') return microphoneGet ? microphoneGet() : catalog;
  if(url==='/api/microphones/select') return failMic ? {success:false,error:'Could not save'} : {success:true,name:microphoneSavedName};
  if(options&&hotkeyPost)return hotkeyPost();
  if(options) return failSettings ? {success:false,error:'Could not save'} : {success:true,settings:saved};
  return hotkeyGet ? hotkeyGet() : saved;
 }
};
vm.createContext(context); vm.runInContext(source.slice(start,end),context);
function key(type,key,ctrlKey=false,metaKey=false){const fn=listeners.get(type);if(fn)fn({key,code:key,ctrlKey,metaKey,altKey:false,shiftKey:false,repeat:false,preventDefault(){},stopPropagation(){}})}
(async()=>{
 const failures=[];
 async function check(name,fn){try{await fn()}catch(e){failures.push(name+': '+e.message)}}
 await check('modifier combination records through release', async()=>{
  await context.toggleRecordHotkey(); key('keydown','Control',true);key('keydown','Meta',true,true);
  key('keyup','Meta',true);key('keyup','Control');
  assert.equal(node('custom-hotkey-input').value,'Ctrl+Win');
  assert(!listeners.has('keydown'),'recorder listener must stop after release');
  if(listeners.has('keydown'))await context.toggleRecordHotkey();
 });
 await check('dialog mode and mouse changes remain drafts', async()=>{
  await context.openShortcutDialog();calls.length=0; context.selectShortcutMode('ptt_only',node('shortcut-mode-ptt'));context.onToggleMiddleClickChange(false);
  await Promise.resolve();assert.equal(calls.filter(c=>c.options&&c.url==='/api/settings/hotkey').length,0);
 });
 await check('failed save keeps dialog open',async()=>{
  node('shortcuts-sub-modal').classList.remove('hidden');
  await context.saveAndApplyHotkeyModal();await Promise.resolve();
  assert(!node('shortcuts-sub-modal').classList.contains('hidden'));
 });
 await check('failed mic save preserves active badge',async()=>{
  node('current-mic-badge').textContent='Existing microphone';
  await context.selectMicrophoneDevice('New microphone',4,node('mic-row'));
  assert.equal(node('current-mic-badge').textContent,'Existing microphone');
 });
 await check('combination waits for complete release and ignores repeats',async()=>{
  node('custom-hotkey-input').value='F8';await context.toggleRecordHotkey();
  key('keydown','Control',true);key('keydown','d',true);
  const repeat=listeners.get('keydown');repeat({key:'d',code:'d',ctrlKey:true,repeat:true,preventDefault(){},stopPropagation(){}});
  assert(listeners.has('keydown'));key('keyup','d',true);assert(listeners.has('keydown'));
  key('keyup','Control');assert.equal(node('custom-hotkey-input').value,'Ctrl+D');assert(!listeners.has('keyup'));
 });
 for(const action of ['escape','blur','close','clear']) await check(action+' cancels and releases recorder',async()=>{
  node('custom-hotkey-input').value='F8';await context.toggleRecordHotkey();key('keydown','Control',true);
  if(action==='escape')key('keydown','Escape');if(action==='blur')listeners.get('blur')();
  if(action==='close')context.closeSubModal('shortcuts-sub-modal');if(action==='clear')context.clearRecordedHotkey();
  await Promise.resolve();assert(!listeners.has('keydown'));assert(!listeners.has('keyup'));
  assert.equal(node('custom-hotkey-input').value,action==='clear'?'Alt+Space':'F8');
  assert(calls.some(c=>c.url.endsWith('/recorder')&&JSON.parse(c.options.body).action==='end'));
 });
 await check('pending recorder begin canceled safely',async()=>{
  let finish;pendingBegin=new Promise(resolve=>finish=resolve);
  const recording=context.toggleRecordHotkey();context.closeSubModal('shortcuts-sub-modal');
  finish({success:true,token:'offline-token'});await recording;pendingBegin=null;
  assert(!listeners.has('keydown'));assert(!node('record-hotkey-btn').disabled);
 });
 await check('default microphone present without invented hardware or signal',async()=>{
  catalog={success:true,devices:[],preferred:null,preferred_available:true,selected_identity:null};
  await context.loadHardwareMicrophones();const html=node('mic-devices-list').innerHTML;
  assert(html.includes('Windows default microphone'));assert(!html.includes('Headset (Max Pro)'));assert(!html.includes('audio-signal-bars'));
 });
 await check('disconnected preference is truthful and retained',async()=>{
  catalog={success:true,devices:[],preferred:'vfmic:missing',preferred_available:false,selected_identity:null};
  calls.length=0;await context.loadHardwareMicrophones();assert(node('current-mic-badge').textContent.includes('disconnected'));
  assert(!calls.some(c=>c.options));assert(node('mic-settings-status').textContent.includes('Reconnect'));
 });
 await check('successful save uses canonical server settings and closes',async()=>{
  failSettings=false;await context.openShortcutDialog();node('custom-hotkey-input').value='control+shift+d';
  saved.custom_hotkey='Ctrl+Shift+D';saved.push_to_talk_shortcut='Ctrl+Shift+D';
  await context.saveAndApplyHotkeyModal();assert(node('shortcuts-sub-modal').classList.contains('hidden'));
  assert.equal(node('ptt-current-kbd').textContent,'Ctrl+Shift+D');failSettings=true;
 });
 await check('microphone default success sends explicit null identity',async()=>{
  failMic=false;catalog={success:true,devices:[],preferred:null,preferred_available:true,selected_identity:null};
  await context.loadHardwareMicrophones();await context.selectMicrophoneDeviceByRow(0,node('mic-row'));
  const call=calls.filter(c=>c.url==='/api/microphones/select').at(-1);assert.deepEqual(JSON.parse(call.options.body),{identity:null});
  assert.equal(node('current-mic-badge').textContent,'Windows default microphone');failMic=true;
 });
 await check('stale closed dialog GET cannot overwrite newly edited draft',async()=>{
  await context.openShortcutDialog();let resolveOld;hotkeyGet=()=>new Promise(resolve=>resolveOld=resolve);
  context.closeSubModal('shortcuts-sub-modal');hotkeyGet=null;await context.openShortcutDialog();
  node('custom-hotkey-input').value='F9';context.onModalHotkeyTriggerChange('custom');
  resolveOld({...saved,custom_hotkey:'F8'});for(let flush=0;flush<8;flush++)await Promise.resolve();
  assert.equal(node('custom-hotkey-input').value,'F9');
 });
 await check('main Custom choice survives initial preset loading',async()=>{
  context.closeSubModal('shortcuts-sub-modal');saved.hotkey_trigger='ctrl_win';
  await context.onHotkeyTriggerSelectChange('custom');await Promise.resolve();await Promise.resolve();
  assert.equal(node('modal-hotkey-trigger-select').value,'custom');saved.hotkey_trigger='custom';
 });
 await check('successful Save renders canonical response when GET fails',async()=>{
  await context.openShortcutDialog();failSettings=false;node('custom-hotkey-input').value='control+shift+d';
  saved.custom_hotkey='Ctrl+Shift+D';saved.push_to_talk_shortcut='Ctrl+Shift+D';
  hotkeyGet=()=>({success:false,error:'Offline GET'});await context.saveAndApplyHotkeyModal();
  assert.equal(node('ptt-current-kbd').textContent,'Ctrl+Shift+D');
  assert.equal(node('custom-hotkey-input').value,'Ctrl+Shift+D');hotkeyGet=null;failSettings=true;
 });
 await check('old dialog Save cannot overwrite or close reopened draft',async()=>{
  await context.openShortcutDialog();failSettings=false;let finishPost;
  hotkeyPost=()=>new Promise(resolve=>finishPost=resolve);
  const saving=context.saveAndApplyHotkeyModal();context.closeSubModal('shortcuts-sub-modal');
  await context.openShortcutDialog();node('custom-hotkey-input').value='F9';
  finishPost({success:true,settings:{...saved,custom_hotkey:'F8',push_to_talk_shortcut:'F8'}});await saving;
  assert.equal(node('custom-hotkey-input').value,'F9');assert(!node('shortcuts-sub-modal').classList.contains('hidden'));
  hotkeyPost=null;failSettings=true;
 });
 await check('saved microphone badge survives catalog failure and reports refresh error',async()=>{
  failMic=false;microphoneSavedName='USB microphone';microphoneGet=()=>({success:false,error:'Could not refresh microphones.'});
  await context.selectMicrophoneDevice('USB microphone',5,node('mic-row'),'vfmic:usb');
  assert.equal(node('current-mic-badge').textContent,'USB microphone');
  assert(node('mic-settings-status').textContent.includes('refresh'));
  microphoneGet=null;microphoneSavedName='Windows default microphone';failMic=true;
 });
 if(failures.length){throw new Error(failures.join('\n'))}
})().catch(e=>{console.error=e=>process.stderr.write(String(e)+'\n');console.error(e);process.exitCode=1});
"""
    completed = subprocess.run(["node", "-e", harness, str(SOURCE)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr

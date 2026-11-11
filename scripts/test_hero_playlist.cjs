const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../dist/assets/hero-playlist.js'), 'utf8');
function fixture(count = 6, previous = '', rng = () => 0.4) {
  const listeners = {}, storage = new Map([['showcase.hero.test', previous]]), selections = [];
  const video = { paused: true, ended: false, seeking: false, readyState: 0, duration: 30, currentTime: 0,
    addEventListener(name, fn) { (listeners[name] ||= []).push(fn); } };
  function fire(name) { for (const fn of listeners[name] || []) fn(); }
  const helper = { visible: true, src: '', userPaused: false };
  const docListeners = {};
  const document = { hidden: false, addEventListener(name, fn) { docListeners[name] = fn; } };
  helper.pause = () => { video.paused = true; fire('pause'); };
  helper.update = () => { if (helper.visible && !helper.userPaused) { video.paused = false; fire('playing'); } };
  function visibility(hidden) { document.hidden = hidden; docListeners.visibilitychange(); }
  const window = { ShowcaseVideo: {
    attach() { video.addEventListener('ended', () => { helper.userPaused = true; }); return helper; },
    setSource(v, src, poster) { helper.src = src; helper.userPaused = false; v.readyState = 0; v.paused = true; v.ended = false; v.poster = poster; }
  } };
  vm.runInNewContext(source, { window, document, sessionStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) }, Math: Object.assign(Object.create(Math), { random: rng }) });
  const items = Array.from({ length: count }, (_, i) => ({ id: `id${i}`, video: `/v${i}.mp4`, poster: `/p${i}`, title: `Title ${i}`, meta: `Meta ${i}`, href: `/detail/${i}` }));
  const controller = window.HeroPlaylist.attach(video, items, { key: 'test', onSelect: item => selections.push(item) });
  function ready(duration = 30) { video.duration = duration; video.readyState = 1; fire('loadedmetadata'); fire('seeking'); fire('seeked'); video.paused = false; fire('playing'); }
  function finish() { ready(); video.currentTime = 30; fire('timeupdate'); }
  return { video, helper, document, visibility, fire, ready, finish, selections, controller, items };
}
for (const count of [6, 35]) {
  const f = fixture(count);
  for (let i = 0; i < count * 3 - 1; i++) f.finish();
  for (let offset = 0; offset < count * 3; offset += count) assert.equal(new Set(f.selections.slice(offset, offset + count).map(x => x.id)).size, count);
  for (let i = 1; i < f.selections.length; i++) assert.notEqual(f.selections[i].id, f.selections[i - 1].id);
  for (const item of f.selections) assert.equal(item, f.items.find(x => x.id === item.id));
  assert.equal(f.controller.current, f.selections.at(-1));
  assert.equal(f.video.loop, false);
}
{
  const first = fixture().controller.current.id;
  assert.notEqual(fixture(6, first).controller.current.id, first);
}
for (const random of [0, 0.99999999]) {
  const f = fixture(6, '', () => random);
  f.ready(30);
  assert.ok(f.video.currentTime >= 0 && f.video.currentTime <= 21.5);
}
{
  const f = fixture(); f.ready(4);
  assert.equal(f.video.currentTime, 0);
  f.video.currentTime = 4; f.fire('timeupdate');
  assert.equal(f.selections.length, 2);
}
for (const condition of ['pause', 'hidden', 'offscreen']) {
  const f = fixture(); f.ready();
  if (condition === 'pause') { f.video.paused = true; f.fire('pause'); }
  if (condition === 'hidden') f.document.hidden = true;
  if (condition === 'offscreen') f.helper.visible = false;
  f.video.currentTime = 30; f.fire('timeupdate'); f.video.ended = true; f.fire('ended');
  assert.equal(f.selections.length, 1, condition);
}
{
  const f = fixture(); f.ready();
  f.video.seeking = true; f.fire('seeking'); f.video.currentTime = 26; f.fire('timeupdate');
  assert.equal(f.selections.length, 1);
  f.video.seeking = false; f.fire('seeked'); f.fire('timeupdate');
  assert.equal(f.selections.length, 1);
  f.video.currentTime = 30; f.video.ended = true; f.video.paused = true; f.fire('ended');
  assert.equal(f.selections.length, 2);
  assert.equal(f.helper.userPaused, false);
  // A queued event from the previous source cannot seek an unready resource.
  f.fire('loadedmetadata'); assert.equal(f.video.currentTime, 30);
}
console.log('hero playlist: shuffle, metadata, captions, visibility, pause, seeking, and ended checks passed');

{
  const f = fixture(); f.ready();
  f.visibility(true); assert.equal(f.video.paused, true);
  assert.equal(f.selections.length, 1);
  f.visibility(false); assert.equal(f.video.paused, false);
  f.helper.userPaused = true; f.video.paused = true; f.fire('pause');
  f.visibility(true); f.visibility(false); assert.equal(f.video.paused, true);
}
{
  const f = fixture(); f.ready();
  f.document.hidden = true; f.video.ended = true; f.video.paused = true; f.fire('ended');
  assert.equal(f.selections.length, 1); assert.equal(f.helper.userPaused, true);
  f.visibility(true); f.visibility(false);
  assert.equal(f.selections.length, 2); assert.equal(f.helper.userPaused, false);
}
{
  const f = fixture(); f.ready();
  f.document.hidden = true; f.video.ended = true; f.fire('ended');
  f.helper.visible = false; f.visibility(false);
  assert.equal(f.selections.length, 1);
  f.helper.visible = true; f.helper.update();
  assert.equal(f.selections.length, 2);
}
// Four independently progressing windows share reservations, including pauses.
for (const count of [6, 35]) {
  const states = new WeakMap();
  const window = { ShowcaseVideo: {
    attach(video) { const state = { visible: true, src: '', pause() {}, update() {} }; states.set(video, state); return state; },
    setSource(video, src) { states.get(video).src = src; video.readyState = 0; }
  } };
  vm.runInNewContext(source, { window, document: { hidden: false, addEventListener() {} }, sessionStorage: { getItem() {}, setItem() {} }, Math });
  const items = Array.from({ length: count }, (_, i) => ({ id: `shared${i}`, task: `task${i % (count === 35 ? 7 : 6)}`, video: `/shared${i}.mp4` }));
  const seen = new Set();
  const slots = Array.from({ length: 4 }, (_, slot) => {
    const events = {};
    const video = { paused: false, seeking: false, duration: 4, currentTime: 0, readyState: 0,
      addEventListener(name, fn) { (events[name] ||= []).push(fn); } };
    const fire = name => (events[name] || []).forEach(fn => fn());
    const controller = window.HeroPlaylist.attach(video, items, { key: `slot${slot}`, group: `platform${count}`, onSelect: item => seen.add(item.id) });
    return { video, fire, controller };
  });
  const unique = () => assert.equal(new Set(slots.map(slot => slot.controller.current.id)).size, 4);
  unique();
  assert.equal(new Set(slots.map(slot => slot.controller.current.task)).size, 4);
  for (let round = 0; round < 30; round++) {
    // Hold slot 0's reservation while the other windows continue independently.
    for (const slot of slots.slice(round < 10 ? 1 : 0)) {
      const previous = slot.controller.current.id;
      slot.video.readyState = 1; slot.video.currentTime = 0;
      slot.fire('loadedmetadata'); slot.fire('playing');
      slot.video.currentTime = 4; slot.fire('timeupdate');
      assert.notEqual(slot.controller.current.id, previous);
      unique();
    }
  }
  assert.equal(seen.size, count, 'shared group covers the whole pool');
}

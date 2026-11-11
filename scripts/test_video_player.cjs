'use strict';
const vm = require('node:vm'), fs = require('node:fs'), assert = require('node:assert/strict');
const code = fs.readFileSync('dist/assets/video-player.js', 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const header = new Uint8Array([0,0,0,12,102,116,121,112,0,0,0,0]);
const mp4 = new Blob([header]);
function harness({reduced = false} = {}) {
  const observers=[], requests=[], pauses=[], videos=[], revoked=[], events={};
  const motion={matches:reduced,addEventListener(){}};
  class TestURL extends URL {}
  TestURL.createObjectURL=blob=>URL.createObjectURL(blob);
  TestURL.revokeObjectURL=url=>{revoked.push(url);URL.revokeObjectURL(url);};
  const document={hidden:false,addEventListener(name,callback){events[name]=callback;}};
  const context={window:{},document,location:{href:'https://example.test/',origin:'https://example.test'},
    URL:TestURL,Blob,AbortController,Uint8Array,matchMedia:()=>motion,
    IntersectionObserver:class{constructor(cb){this.cb=cb;observers.push(this);}observe(video){this.video=video;}},
    fetch:(url,options)=>new Promise((resolve,reject)=>{
      const request={url,options,resolve,reject};requests.push(request);
      options.signal.addEventListener('abort',()=>{request.aborted=true;reject(Error('aborted'));});
    })};
  vm.runInNewContext(code,context);
  function video(src='first.mp4') {
    const events={};
    const v={dataset:{},paused:true,ended:false,plays:0,loads:0,currentTime:0,duration:35,readyState:0,events,
      getAttribute:()=>src,removeAttribute(){delete this.src;},load(){this.loads++;this.currentTime=0;this.readyState=0;},
      addEventListener(name,callback){events[name]=callback;},
      play(){this.plays++;this.paused=false;events.play();return Promise.resolve();},
      pause(){if(!this.paused){this.paused=true;pauses.push(()=>events.pause());}}};videos.push(v);return v;
  }
  function visibility(v,visible){for(const o of observers.filter(o=>o.video===v))o.cb([{isIntersecting:visible,intersectionRatio:visible?1:0}]);}
  function metadata(){while(pauses.length)pauses.shift()();for(const v of videos)if(v.src&&v.readyState===0){v.readyState=4;v.events.loadedmetadata();}}
  async function complete(index,{range=false,html=false,blob=mp4}={}) {
    const r=requests[index];r.done=true;
    r.resolve({ok:true,status:range?206:200,headers:{get:key=>key==='content-type'?(html?'text/html':'video/mp4'):(range?'bytes 0-11/4000000':null)},
      arrayBuffer:async()=>header.buffer,blob:async()=>{assert(!html,'HTML must not be cached as video');return blob;}});
    await tick();await tick();metadata();await tick();
  }
  return {api:context.window.ShowcaseVideo,video,visibility,requests,complete,metadata,document,events,revoked};
}
(async()=>{
  // Hosts supporting Range start without downloading an entire movie.
  const n=harness(),nv=n.video();n.api.attach(nv);assert.equal(n.requests.length,0);
  n.visibility(nv,true);assert.equal(n.requests[0].options.headers.Range,'bytes=0-11');
  await n.complete(0,{range:true});assert.equal(nv.dataset.playbackMode,'stream');assert.equal(nv.src,'https://example.test/first.mp4');assert.equal(nv.paused,false);
  const loads=nv.loads;for(const target of [3,20,7]){nv.currentTime=target;nv.events.seeking?.();nv.events.seeked?.();assert.equal(nv.currentTime,target);}assert.equal(nv.loads,loads);assert.equal(n.requests.length,1);
  // Hosts that ignore Range share one complete file between hero/task players.
  const h=harness(),a=h.video(),b=h.video();h.api.attach(a);h.api.attach(b);h.visibility(a,true);h.visibility(b,true);
  assert.equal(h.requests.length,1,'same source is fetched once');assert.equal(a.plays,0);
  await h.complete(0);assert(a.src.startsWith('blob:'));assert.equal(a.src,b.src);assert.equal(a.dataset.playbackMode,'cached');
  const source=a.src; a.currentTime=20;h.visibility(a,false);h.metadata();assert.equal(a.src,undefined);assert.equal(b.src,source,'another visible player retains shared data');
  h.visibility(a,true);h.metadata();assert.equal(a.currentTime,20,'scrolling restores the last position');assert.equal(h.requests.length,1);
  a.paused=true;a.events.pause();const plays=a.plays;h.visibility(a,false);h.metadata();h.visibility(a,true);h.metadata();assert.equal(a.plays,plays,'manual pause survives scrolling');
  h.api.setSource(a,'second.mp4');await h.complete(1);assert(a.plays>plays);assert.notEqual(a.src,b.src);
  // Fast scrolling cannot leave a growing queue of stale downloads.
  const q=harness(),qs=['a.mp4','b.mp4','c.mp4','d.mp4'].map(s=>q.video(s));
  qs.forEach(v=>{q.api.attach(v);q.visibility(v,true);});assert.equal(q.requests.length,2,'bounded parallel requests');
  q.visibility(qs[0],false);await tick();assert(q.requests[0].options.signal.aborted);assert.equal(q.requests.length,3,'visible queued movie takes freed slot');
  q.visibility(qs[3],false);await q.complete(1);assert.equal(q.requests.length,3,'offscreen queued movie never starts');await q.complete(2);
  q.document.hidden=true;q.events.visibilitychange();q.metadata();assert(qs.every(v=>v.paused&&!v.src),'background tab releases decoders');
  q.document.hidden=false;q.events.visibilitychange();q.metadata();assert.equal(q.requests.length,3,'cached movies resume without duplicate downloads');
  // Source replacement cannot install a late response from the previous scene.
  const s=harness(),sv=s.video();s.api.attach(sv);s.visibility(sv,true);s.api.setSource(sv,'new.mp4');await tick();assert(s.requests[0].options.signal.aborted);
  await s.complete(0);assert.equal(sv.src,undefined);await s.complete(1,{html:true});assert.equal(sv.src,'https://example.test/new.mp4');assert(sv.controls);
  // Reduced motion and blocked autoplay keep native controls available.
  // A retired fingerprint URL recovers to the current redacted original.
  const f=harness(),fv=f.video('media/web/episode-demo-870d416625.mp4');
  f.api.attach(fv);f.visibility(fv,true);
  f.requests[0].resolve({ok:false,status:404});await tick();await tick();f.metadata();
  assert.equal(fv.src,'https://example.test/media/episode-demo.mp4');
  assert.equal(fv.paused,false);assert.equal(f.requests.length,1,'missing fingerprints do not retry indefinitely');
  const r=harness({reduced:true}),rv=r.video();r.api.attach(rv);r.visibility(rv,true);await r.complete(0);assert.equal(rv.plays,0);
  const k=harness(),kv=k.video();kv.play=()=>Promise.reject(Error('blocked'));k.api.attach(kv);k.visibility(kv,true);await k.complete(0);assert(kv.controls);
  // Idle caches are bounded; evicted videos can be loaded again on demand.
  const c=harness(),cv=c.video('large-a.mp4'),dv=c.video('large-b.mp4');const large=new Blob([header,new Uint8Array(13*1024*1024)]);
  c.api.attach(cv);c.api.attach(dv);c.visibility(cv,true);await c.complete(0,{blob:large});const old=cv.src;c.visibility(cv,false);c.metadata();c.visibility(dv,true);await c.complete(1,{blob:large});c.visibility(dv,false);c.metadata();assert(c.revoked.includes(old));c.visibility(cv,true);assert.equal(c.requests.length,3);
  console.log('PASS range streaming, shared fallback, seeking, two-request limit, stale cancellation, pause/position preservation, hidden tabs, authentication responses, autoplay and cache eviction');
})().catch(error=>{console.error(error);process.exitCode=1;});

(() => {
  'use strict';
  const states = new WeakMap(), players = new Set(), assets = new Map();
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const MAX_DOWNLOADS = 2, MAX_IDLE_BYTES = 24 * 1024 * 1024;
  let downloads = 0, clock = 0;
  const mediaType = response => {
    const type = (response.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
    return type.startsWith('video/') || type === 'application/octet-stream';
  };
  const validHeader = bytes => bytes.length >= 12 && String.fromCharCode(...bytes.slice(4, 8)) === 'ftyp';
  function originalSource(src) {
    const url = new URL(src, location.href);
    if (url.origin !== location.origin) return '';
    const match = url.pathname.match(/^(.*\/media)\/web\/([\w-]+)-[a-f0-9]{10}\.mp4$/);
    if (!match) return '';
    url.pathname = `${match[1]}/${match[2]}.mp4`;
    url.search = ''; url.hash = '';
    return url.href;
  }

  function trimCache() {
    const idle = [...assets.values()].filter(a => !a.users.size && a.status === 'ready').sort((a, b) => a.used - b.used);
    let bytes = idle.reduce((sum, a) => sum + a.bytes, 0);
    for (const a of idle) {
      if (bytes <= MAX_IDLE_BYTES) break;
      bytes -= a.bytes;
      if (a.blob) URL.revokeObjectURL(a.blob);
      assets.delete(a.src);
    }
  }
  function release(s) {
    const a = s.asset;
    s.asset = null;
    if (!a) return;
    a.users.delete(s); a.used = ++clock;
    if (!a.users.size && a.status !== 'ready') {
      a.controller?.abort();
      assets.delete(a.src);
    }
    trimCache();
  }
  async function download(a) {
    downloads++;
    a.status = 'loading';
    const controller = a.controller = new AbortController();
    try {
      const response = await fetch(a.src, { credentials: 'same-origin', headers: {Range: 'bytes=0-11'}, signal: controller.signal });
      if (!response.ok || !mediaType(response)) throw Error('Invalid video response');
      const range = response.headers.get('content-range') || '';
      if (response.status === 206 && /^bytes 0-11\/\d+$/.test(range)) {
        const header = new Uint8Array(await response.arrayBuffer());
        if (header.length !== 12 || !validHeader(header)) throw Error('Invalid video header');
        // Only use streaming when the host actually serves byte ranges. This
        // preserves native seeking; hosts ignoring Range use a cached MP4 below.
        a.mode = 'stream'; a.url = a.src;
      } else {
        if (response.status !== 200) throw Error('Invalid video range');
        const blob = await response.blob();
        if (!validHeader(new Uint8Array(await blob.slice(0, 12).arrayBuffer()))) throw Error('Invalid video header');
        if (controller.signal.aborted || assets.get(a.src) !== a) return;
        a.blob = URL.createObjectURL(new Blob([blob], {type:'video/mp4'}));
        a.url = a.blob; a.bytes = blob.size; a.mode = 'cached';
      }
      if (controller.signal.aborted || assets.get(a.src) !== a) return;
      a.status = 'ready';
      for (const s of a.users) s.install(a);
    } catch (_) {
      if (!controller.signal.aborted && assets.get(a.src) === a) {
        // Keep native controls usable if fetching is unavailable. Do not loop
        // requests or swap sources in the middle of a seek.
        a.status = 'ready'; a.mode = 'native'; a.url = originalSource(a.src) || a.src;
        for (const s of a.users) s.install(a);
      }
    } finally {
      downloads--;
      trimCache(); pump();
    }
  }
  function pump() {
    for (const a of assets.values()) {
      if (downloads >= MAX_DOWNLOADS) break;
      if (a.status === 'queued' && a.users.size) download(a);
    }
  }
  function acquire(s) {
    if (!s.src || s.asset) return;
    let url;
    try { url = new URL(s.src, location.href); if (url.origin !== location.origin) return; } catch (_) { return; }
    let a = assets.get(url.href);
    if (!a) {
      a = {src:url.href, status:'queued', users:new Set(), used:++clock, bytes:0, blob:null};
      assets.set(url.href, a);
    }
    s.asset = a; a.users.add(s); a.used = ++clock;
    if (a.status === 'ready') s.install(a);
    else pump();
  }
  function attach(video) {
    if (states.has(video)) return states.get(video);
    const initial = video.getAttribute('src') || '';
    const s = {video, version:0, src:'', asset:null, installed:null, visible:false,
      userPaused:false, intent:false, resumeTime:0, internalPauses:0};
    states.set(video, s); players.add(s);
    video.controls = true; video.muted = true; video.defaultMuted = true;
    video.playsInline = true; video.autoplay = false; video.preload = 'none';
    function pause() {
      s.intent = false;
      if (!video.paused) s.internalPauses++;
      video.pause();
    }
    async function play(version) {
      if (version !== s.version || !s.intent || !s.visible || document.hidden || s.userPaused || reduced.matches) return;
      try { await video.play(); } catch (_) { if (version === s.version) s.intent = false; }
    }
    function unload() {
      pause();
      if (s.installed) {
        s.resumeTime = Number.isFinite(video.currentTime) ? video.currentTime : 0;
        video.removeAttribute('src'); video.load(); s.installed = null;
      }
      release(s);
    }
    s.install = a => {
      if (s.asset !== a || !s.visible || document.hidden || s.installed === a) return;
      s.installed = a;
      video.dataset.playbackMode = a.mode;
      video.src = a.url; video.load();
      // loadedmetadata restores a saved position before resuming playback.
    };
    s.update = () => {
      if (!s.visible || document.hidden) { unload(); return; }
      s.intent = !s.userPaused && !reduced.matches;
      acquire(s);
      if (s.installed && video.readyState >= 1) play(s.version);
    };
    s.pause = pause; s.unload = unload;
    video.addEventListener('loadedmetadata', () => {
      if (s.resumeTime > 0) {
        video.currentTime = Math.min(s.resumeTime, Number.isFinite(video.duration) ? video.duration : s.resumeTime);
        s.resumeTime = 0;
      }
      play(s.version);
    });
    video.addEventListener('play', () => { s.userPaused = false; });
    video.addEventListener('pause', () => {
      if (s.internalPauses) { s.internalPauses--; return; }
      if (!video.ended) { s.userPaused = true; s.intent = false; }
    });
    video.addEventListener('ended', () => { s.userPaused = true; s.intent = false; });
    const observer = new IntersectionObserver(entries => {
      s.visible = entries[0].isIntersecting && entries[0].intersectionRatio >= 0.2;
      s.update();
    }, {threshold:[0,0.2]});
    observer.observe(video);
    setSource(video, initial);
    return s;
  }
  function setSource(video, src, poster) {
    const s = states.get(video) || attach(video);
    s.version++; s.unload();
    video.removeAttribute('src'); video.load();
    s.resumeTime = 0; s.userPaused = false; s.src = src || '';
    if (poster !== undefined) video.poster = poster || '';
    s.update();
  }
  document.addEventListener('visibilitychange', () => { for (const s of players) s.update(); });
  reduced.addEventListener?.('change', () => { for (const s of players) s.update(); });
  window.ShowcaseVideo = {attach, setSource};
})();

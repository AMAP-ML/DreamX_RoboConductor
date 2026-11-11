(() => {
  'use strict';
  const attached = new WeakMap();
  const groups = new Map();
  function attach(video, items, options = {}) {
    if (attached.has(video)) return attached.get(video);
    items = items.filter(item => item && item.video);
    if (!items.length) return null;
    const storageKey = `showcase.hero.${options.key || 'default'}`;
    let last = '';
    try { last = sessionStorage.getItem(storageKey) || ''; } catch (_) {}
    const groupKey = options.group || video;
    if (!groups.has(groupKey)) groups.set(groupKey, { bag: [], active: new Map(), tasks: new Map() });
    const group = groups.get(groupKey);
    let selected = null, end = Infinity, prepared = false;
    let active = false, userSeeking = false, internalSeek = false, helper;
    const random = () => Math.max(0, Math.min(0.999999999, Math.random()));
    function pick() {
      const reserved = new Set([...group.active.entries()].filter(([slot]) => slot !== video).map(([, id]) => id));
      const reservedTasks = new Set([...group.tasks.entries()].filter(([slot]) => slot !== video).map(([, task]) => task));
      function refill() {
        group.bag = items.slice();
        for (let i = group.bag.length - 1; i > 0; i--) {
          const j = Math.floor(random() * (i + 1));
          [group.bag[i], group.bag[j]] = [group.bag[j], group.bag[i]];
        }
      }
      const eligible = item => !reserved.has(item.id) && item.id !== last;
      const diverse = item => eligible(item) && (!item.task || !reservedTasks.has(item.task));
      let index = group.bag.findIndex(diverse);
      if (index < 0) index = group.bag.findIndex(eligible);
      if (index < 0) { refill(); index = group.bag.findIndex(diverse); }
      if (index < 0) index = group.bag.findIndex(eligible);
      // Tiny pools may have no alternative; never take another window's ID.
      if (index < 0) index = group.bag.findIndex(item => !reserved.has(item.id));
      if (index < 0) return null;
      const item = group.bag.splice(index, 1)[0];
      group.active.set(video, item.id);
      if (item.task) group.tasks.set(video, item.task);
      return item;
    }
    function select() {
      const next = pick();
      if (!next) return;
      selected = next;
      last = selected.id;
      try { sessionStorage.setItem(storageKey, last); } catch (_) {}
      prepared = active = userSeeking = internalSeek = false;
      end = Infinity;
      video.loop = false;
      options.onSelect?.(selected);
      window.ShowcaseVideo.setSource(video, selected.video, selected.poster);
    }
    function metadata() {
      // setSource removes the old resource before loading the next one. Ignore
      // queued metadata events until the selected resource has usable metadata.
      if (prepared || !selected || helper?.src !== selected.video || video.readyState < 1) return;
      const duration = video.duration;
      if (!Number.isFinite(duration) || duration <= 0) return;
      prepared = true;
      const maxStart = Math.max(0, duration - 8 - 0.5);
      const start = random() * maxStart;
      end = Math.min(duration, start + 8);
      if (start > 0) {
        internalSeek = true;
        video.currentTime = start;
      }
    }
    // Seek before the shared helper's metadata listener starts playback.
    video.addEventListener('loadedmetadata', metadata);
    helper = window.ShowcaseVideo.attach(video);
    video.loop = false;
    function visible() {
      return !document.hidden && helper.visible;
    }
    let hiddenEnded = false;
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        // A natural ending can race the browser's visibility notification.
        hiddenEnded = hiddenEnded || (active && video.ended);
        helper.pause();
      } else if (hiddenEnded && helper.visible) {
        hiddenEnded = false;
        select();
      } else {
        if (hiddenEnded) helper.userPaused = false;
        helper.update();
      }
    });
    video.addEventListener('playing', () => {
      active = true;
      if (hiddenEnded && visible()) { hiddenEnded = false; select(); }
    });
    video.addEventListener('pause', () => { if (!video.ended) active = false; });
    video.addEventListener('seeking', () => {
      if (!internalSeek) userSeeking = true;
    });
    video.addEventListener('seeked', () => {
      if (internalSeek) { internalSeek = false; return; }
      if (userSeeking) {
        userSeeking = false;
        end = Math.min(video.duration, video.currentTime + 8);
      }
    });
    video.addEventListener('timeupdate', () => {
      if (prepared && active && !video.paused && visible() && !video.seeking && !userSeeking && !internalSeek && video.currentTime >= end) select();
    });
    // Registered after the helper: setSource clears its natural-ended pause.
    video.addEventListener('ended', () => {
      if (prepared && active && document.hidden && !userSeeking && !video.seeking) hiddenEnded = true;
      if (prepared && active && visible() && !userSeeking && !video.seeking) select();
    });
    const controller = { get current() { return selected; } };
    attached.set(video, controller);
    select();
    return controller;
  }
  window.HeroPlaylist = { attach };
})();

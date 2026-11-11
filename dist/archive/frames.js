/* Keep the displayed frame until the next complete camera set is decoded. */
(() => {
  function createFrameLoader(ImageType = Image, schedule = requestAnimationFrame) {
    const cache = new Map();
    let revision = 0;

    function load(url) {
      if (!url) return Promise.resolve(null);
      if (!cache.has(url)) {
        cache.set(url, new Promise(resolve => {
          const image = new ImageType();
          image.decoding = 'async';
          image.onload = async () => {
            try {
              if (image.decode) await image.decode();
              resolve(image);
            } catch (_) { resolve(null); }
          };
          image.onerror = () => resolve(null);
          image.src = url;
        }));
      }
      return cache.get(url);
    }

    return {
      clear() { revision++; cache.clear(); },
      preload(sources) { sources.forEach(load); },
      async show(sources, commit) {
        const requested = ++revision;
        const images = await Promise.all(sources.map(load));
        return new Promise(resolve => schedule(() => {
          if (requested !== revision) { resolve(false); return; }
          commit(images);
          resolve(true);
        }));
      },
    };
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { createFrameLoader };
  else window.createFrameLoader = createFrameLoader;
})();

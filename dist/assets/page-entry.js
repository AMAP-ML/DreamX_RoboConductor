// A refresh starts at the cover. Fresh shared section links still deep-link.
(() => {
  const navigation = performance.getEntriesByType('navigation')[0];
  if (navigation?.type !== 'reload') return;
  document.documentElement.dataset.refreshAtTop = 'true';
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  history.replaceState(history.state, '', location.pathname + location.search);
  const top = () => window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  top();
  window.addEventListener('pageshow', () => requestAnimationFrame(top), { once: true });
})();

(() => {
  'use strict';
  const resources = window.ShowcaseTranslations || [];
  const normalize = value => value.replace(/\s+/g, ' ').trim();
  const strings = new Map();
  resources.forEach(resource => Object.entries(resource.strings || {}).forEach(([en, zh]) => strings.set(normalize(en), zh)));
  const foldedStrings = new Map([...strings].map(([key, value]) => [key.toLowerCase(), value]));
  const lookup = key => strings.get(key) ?? foldedStrings.get(key.toLowerCase());
  // Page-specific templates run before broad shared labels and number phrases.
  const patterns = resources.slice().reverse().flatMap(resource => (resource.patterns || []).map(rule => ({
    expression: new RegExp(rule.source, rule.flags || ''), replacement: rule.replacement
  })));
  const storageKey = 'roboconductor.language';
  const canonical = value => /^zh(?:-|$)/i.test(value || '') ? 'zh' : value === 'en' ? 'en' : null;
  // The bare site URL always opens in English; explicit language links keep their choice.
  let language = canonical(new URL(location.href).searchParams.get('lang')) || 'en';
  const rawSelectors = 'script,style,pre,code,textarea,[data-i18n-skip],[data-lang-only],#instruction,#manual-text,.trace-text,.trace-summary';
  const textRecords = new WeakMap(), attributeRecords = new WeakMap(), linkRecords = new WeakMap();
  const attributes = ['title', 'aria-label', 'placeholder', 'alt'];
  let controls;

  function translate(value, target = language) {
    if (target !== 'zh' || !value || !value.trim()) return value;
    const key = normalize(value);
    let result = lookup(key);
    if (result === undefined) {
      result = key;
      patterns.forEach(rule => { result = result.replace(rule.expression, rule.replacement); });
      result = result.split(/(\s*·\s*)/).map(part => lookup(normalize(part)) || part).join('');
    }
    return value.match(/^\s*/)[0] + result + value.match(/\s*$/)[0];
  }
  function skipped(element) { return !!element?.closest(rawSelectors); }
  function applyText(node) {
    if (!node.parentElement || skipped(node.parentElement)) return;
    const previous = textRecords.get(node), current = node.nodeValue;
    const source = previous && current === previous.rendered ? previous.source : current;
    const rendered = translate(source);
    textRecords.set(node, { source, rendered });
    if (current !== rendered) node.nodeValue = rendered;
  }
  function applyAttributes(element) {
    if (skipped(element)) return;
    const records = attributeRecords.get(element) || {};
    for (const name of attributes) {
      const current = element.getAttribute(name);
      if (current === null) continue;
      const previous = records[name];
      const source = previous && current === previous.rendered ? previous.source : current;
      const rendered = translate(source);
      records[name] = { source, rendered };
      if (current !== rendered) element.setAttribute(name, rendered);
    }
    attributeRecords.set(element, records);
    if (element.tagName === 'A') {
      const current = element.getAttribute('href');
      if (!current) return;
      const previous = linkRecords.get(element);
      const source = previous && current === previous.rendered ? previous.source : current;
      if (source.startsWith('#')) return;
      const url = new URL(source, location.href);
      if (url.origin !== location.origin || !/\/$|\.html$/.test(url.pathname)) return;
      url.searchParams.set('lang', language);
      const rendered = url.pathname + url.search + url.hash;
      linkRecords.set(element, { source, rendered });
      if (current !== rendered) element.setAttribute('href', rendered);
    }
  }
  function apply(root) {
    if (root.nodeType === 3) { applyText(root); return; }
    if (root.nodeType !== 1 || skipped(root)) return;
    applyAttributes(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        return skipped(node.nodeType === 1 ? node : node.parentElement) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
      }
    });
    let node;
    while ((node = walker.nextNode())) {
      if (node.nodeType === 3) applyText(node); else applyAttributes(node);
    }
  }
  function languagePanels() {
    document.querySelectorAll('[data-lang-only]').forEach(element => { element.hidden = element.dataset.langOnly !== language; });
  }
  function setLanguage(next, persist = true) {
    language = canonical(next) || 'en';
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
    if (persist) { try { localStorage.setItem(storageKey, language); } catch (_) {} }
    const url = new URL(location.href);
    url.searchParams.set('lang', language);
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    controls?.querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.language === language)));
    languagePanels();
    apply(document.body);
    const title = document.querySelector('title');
    if (title) apply(title);
    window.dispatchEvent(new CustomEvent('showcase:languagechange', { detail: { language } }));
  }
  function init() {
    const host = document.querySelector('.nav-inner');
    if (host) {
      controls = document.createElement('div');
      controls.className = 'language-switch';
      controls.setAttribute('data-i18n-skip', '');
      controls.setAttribute('role', 'group');
      controls.setAttribute('aria-label', 'Language / 语言');
      for (const [value, label, title] of [['en', 'EN', 'English'], ['zh', '中文', '简体中文']]) {
        const button = document.createElement('button');
        button.type = 'button'; button.dataset.language = value; button.textContent = label;
        button.setAttribute('aria-label', title); button.title = title;
        button.addEventListener('click', () => setLanguage(value)); controls.append(button);
      }
      host.append(controls);
    }
    setLanguage(language);
    const observer = new MutationObserver(changes => {
      const targets = new Set();
      changes.forEach(change => {
        if (change.type === 'childList') change.addedNodes.forEach(node => targets.add(node));
        else targets.add(change.target);
      });
      targets.forEach(target => { if (target.isConnected) apply(target); });
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: [...attributes, 'href'] });
    const title = document.querySelector('title');
    if (title) observer.observe(title, { childList: true, characterData: true, subtree: true });
  }
  window.ShowcaseI18n = { translate, setLanguage, get language() { return language; } };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();

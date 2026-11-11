/* SPDX-License-Identifier: LicenseRef-DreamX-RoboConductor-NonCommercial */
(() => {
  'use strict';
  const list = document.querySelector('#episode-list');
  const detail = document.querySelector('#episode-detail');
  const search = document.querySelector('#search');
  const category = document.querySelector('#category');
  let episodes = [];
  let selected = null;

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function showDetail(episode) {
    detail.replaceChildren();
    if (!episode) {
      detail.append(element('p', 'Try another search to explore an example.'));
      return;
    }
    detail.append(element('p', 'EXAMPLE / ' + episode.id, 'eyebrow'));
    detail.append(element('h3', episode.title));
    detail.append(element('p', episode.summary));
    const meta = element('div', undefined, 'detail-meta');
    meta.append(element('span', episode.category, 'badge'));
    meta.append(element('span', 'Outcome: ' + episode.outcome, 'badge'));
    detail.append(meta);
    const steps = element('ol', undefined, 'steps');
    for (const step of episode.steps) {
      const row = element('li');
      row.append(element('strong', step.title), element('p', step.detail));
      steps.append(row);
    }
    detail.append(steps);
  }

  function render() {
    const query = search.value.trim().toLowerCase();
    const visible = episodes.filter(episode =>
      (category.value === 'all' || episode.category === category.value) &&
      (episode.title + ' ' + episode.summary).toLowerCase().includes(query));
    if (!visible.some(episode => episode.id === selected)) selected = visible[0]?.id ?? null;
    document.querySelector('#episode-count').textContent = `${visible.length} of ${episodes.length} examples`;
    list.replaceChildren();
    for (const episode of visible) {
      const card = element('button', undefined, 'episode-card');
      card.type = 'button';
      card.setAttribute('aria-pressed', String(episode.id === selected));
      card.setAttribute('aria-controls', 'episode-detail');
      const top = element('span', undefined, 'card-top');
      top.append(element('span', episode.id, 'fixture-id'), element('span', episode.category, 'badge'));
      card.append(top, element('span', episode.title, 'card-title'), element('span', episode.summary, 'card-summary'));
      card.addEventListener('click', () => {
        selected = episode.id;
        for (const button of list.querySelectorAll('button')) button.setAttribute('aria-pressed', 'false');
        card.setAttribute('aria-pressed', 'true');
        showDetail(episode);
      });
      list.append(card);
    }
    if (!visible.length) list.append(element('p', 'No examples match your filters.', 'empty'));
    showDetail(visible.find(episode => episode.id === selected));
  }

  async function start() {
    try {
      const response = await fetch('data/demo.json', { credentials: 'omit' });
      if (!response.ok) throw new Error('Fixture request failed');
      const data = await response.json();
      if (data.synthetic !== true || !Array.isArray(data.episodes) || !data.episodes.length) throw new Error('Invalid fixture');
      const ids = new Set();
      for (const episode of data.episodes) {
        if (episode.synthetic !== true || typeof episode.id !== 'string' || ids.has(episode.id) ||
            !['arrangement', 'inspection'].includes(episode.category) ||
            !['title', 'summary', 'outcome'].every(key => typeof episode[key] === 'string') ||
            !Array.isArray(episode.steps) || episode.steps.some(step => typeof step.title !== 'string' || typeof step.detail !== 'string')) {
          throw new Error('Invalid example');
        }
        ids.add(episode.id);
      }
      episodes = data.episodes;
      search.addEventListener('input', render);
      category.addEventListener('change', render);
      render();
    } catch (_) {
      document.querySelector('#load-error').hidden = false;
      document.querySelector('#episode-count').textContent = 'Examples unavailable';
    }
  }
  start();
})();

/* SPDX-License-Identifier: LicenseRef-DreamX-RoboConductor-NonCommercial */
(() => {
  'use strict';
  function safeLocalPath(value) {
    if (typeof value !== 'string' || !value || value.trim() !== value) return '';
    let decoded;
    try { decoded = decodeURIComponent(value); } catch (_) { return ''; }
    if (/^[a-z][a-z\d+.-]*:/i.test(decoded) || decoded.startsWith('/') || /[\\?#%\u0000-\u001f\u007f]/.test(decoded)) return '';
    if (decoded.split('/').some(part => !part || part === '.' || part === '..')) return '';
    return value;
  }
  function episodeScriptPath(value) {
    const path = safeLocalPath(value);
    return path.startsWith('episodes/') && path.endsWith('/data.js') ? path : '';
  }
  function trialInfo(episode, outcome, documentType = document) {
    const info = documentType.createElement('span'); info.className = 'trial-info';
    const title = documentType.createElement('b'); title.textContent = `Scene ${String(episode.scene).padStart(2, '0')}`;
    const result = documentType.createElement('span');
    const kind = ['success', 'failure', 'pending'].includes(outcome) ? outcome : 'pending';
    result.className = `trial-outcome ${kind}`; result.textContent = kind;
    const details = documentType.createElement('span');
    details.textContent = [Number.isFinite(episode.turns) ? `${episode.turns} turns` : '', Number.isFinite(episode.observations) ? `${episode.observations} observations` : 'Observation replay'].filter(Boolean).join(' · ');
    info.append(title, result, details);
    return info;
  }
  const api = {safeLocalPath, episodeScriptPath, trialInfo};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.ShowcaseContent = api;
})();

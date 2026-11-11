/* SPDX-License-Identifier: LicenseRef-DreamX-RoboConductor-NonCommercial */
(() => {
  'use strict';
  const pending = new Map();
  function applyEnglish(original, translated, language) {
    if (language !== 'en' || !translated) return original;
    if (translated.id !== original.id || (original.manual?.sha256 && translated.manualSourceSha256 !== original.manual.sha256)) throw Error('English text does not match this episode.');
    if (!Array.isArray(translated.steps) || translated.steps.length !== (original.steps || []).length) throw Error('English text has an incomplete turn list.');
    return {
      ...original,
      instruction: translated.instruction ?? original.instruction,
      public_summary: translated.public_summary ?? original.public_summary,
      done_reason: translated.done_reason ?? original.done_reason,
      warnings: translated.warnings ?? original.warnings,
      manual: {...original.manual, text: translated.manual?.text ?? original.manual?.text,
        media: (original.manual?.media || []).map((item, index) => ({...item, label: translated.manual?.media?.[index]?.label ?? item.label}))},
      steps: (original.steps || []).map((step, index) => ({...step,
        narration: translated.steps[index].narration ?? step.narration,
        done_reason: translated.steps[index].done_reason ?? step.done_reason})),
    };
  }
  function loadEnglish(id, base = 'translations/en/', fetcher = fetch) {
    if (!/^[a-zA-Z\d_-]+$/.test(id)) return Promise.reject(Error('Invalid episode ID.'));
    const path = `${base}${id}.json?v=1`;
    if (!pending.has(path)) {
      const request = fetcher(path, {credentials:'same-origin'}).then(response => {
        if (!response.ok) throw Error('English text is unavailable. Reload the page or select Chinese.');
        return response.json();
      }).then(value => {
        if (value.id !== id) throw Error('English text does not match this episode.');
        return value;
      }).catch(error => {pending.delete(path); throw error;});
      pending.set(path, request);
    }
    return pending.get(path);
  }
  const api = {applyEnglish, loadEnglish};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.EpisodeLanguage = api;
})();

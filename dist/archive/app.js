(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const safePath = window.ShowcaseContent.safeLocalPath;
  const imagePath = value => {
    const path = safePath(value);
    if (!path.startsWith('episodes/real-world/')) return path;
    const faceRevision = ["c0a8263451cd9b62e805", "9f74c1bac3c2f338d12f", "97e94ffd19ceb5ba012b", "a19de066ff5ffd71f42a", "ff4e4e8e57e218d00589"].includes(path.split('/')[3]);
    return `${path}?v=${faceRevision ? 'faces-20261109-1' : 'redaction-20261027-2'}`;
  };
  const catalog = window.EVALUATION_CATALOG;
  const platforms = catalog?.platforms || (catalog?.tasks?.length ? [{
    id: 'robotwin', name: 'RoboTwin 2.0', kind: 'simulation',
    summary: catalog.summary, tasks: catalog.tasks,
  }] : []);
  const cache = new Map(), pending = new Map();
  const frames = window.createFrameLoader();
  const cameras = ['head_camera', 'left_camera', 'right_camera'];
  let platform = null, task = null, episode = null, detail = null, stepIndex = 0, timer = null;
  let requestedStep = 0, playing = false, playbackRevision = 0, navigationRevision = 0;
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  };
  const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
  const percent = (successes, counted) => counted ? `${(successes / counted * 100).toFixed(1).replace(/\.0$/, '')}%` : '—';
  const physicalTaskTitles = {
  "discard_blackboard_eraser": "Discard eraser",
  "empty_cup": "Empty cup",
  "lift_bottle": "Lift bottle",
  "place_gum_bottle": "Place gum bottle",
  "place_orange": "Place orange",
  "put_pen": "Place pen in holder",
  "stack_three_bowls": "Stack three bowls",
  "pour_water": "Pour water",
  "hang_cup": "Hang cup",
  "put_phone": "Place phone on stand"
};
  const taskTitle = value => (platform?.id === 'piper' && physicalTaskTitles[value]) || value.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase());
  function formatDuration(seconds) {
    if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return null;
    const rounded = Math.round(seconds);
    const hours = Math.floor(rounded / 3600), minutes = Math.floor(rounded % 3600 / 60);
    return [hours ? `${hours} h` : '', hours || minutes ? `${minutes} min` : '', `${rounded % 60} s`].filter(Boolean).join(' ');
  }
  function result(item) {
    if (item.result_source === 'operator') return item.success === true ? ['success', 'Success'] : item.success === false ? ['failure', 'Failure'] : ['unknown', 'Awaiting operator confirmation'];
    if (item.success_available === false) return ['unknown', 'No native score'];
    return item.success !== true && item.success !== false ? ['unknown', 'Unknown result'] : item.counted === false ? ['unknown', 'Unscored'] : item.success ? ['success', 'Success'] : ['failure', 'Failure'];
  }
  function scoreSummary(item) {
    const s = item.summary, physical = item.kind === 'physical' || item.backend === 'piper';
    return physical ? { wins: number(s.operator_successes), count: number(s.operator_confirmed), label: 'Success rate' }
      : { wins: number(s.successes), count: number(s.counted), label: 'Success rate' };
  }
  const episodeLabel = item => `EP ${String(item.episode_index ?? Math.max(0, task?.episodes.findIndex(value => value.id === item.id) ?? 0)).padStart(2, '0')}`;
  const route = item => `#/platforms/${encodeURIComponent(item.backend || platform?.id || 'robotwin')}/tasks/${encodeURIComponent(item.task)}/episodes/${encodeURIComponent(item.id)}`;
  function selection(hash) {
    const modern = hash.match(/^#\/platforms\/([^/]+)(?:\/tasks\/([^/]+)\/episodes\/([^/]+))?$/);
    const legacy = hash.match(/^#\/tasks\/([^/]+)\/episodes\/([^/]+)$/);
    let selectedPlatform, selectedTask, selectedEpisode;
    try {
      if (modern) {
        selectedPlatform = platforms.find(value => value.id === decodeURIComponent(modern[1]));
        if (modern[2]) {
          selectedTask = selectedPlatform?.tasks.find(value => value.name === decodeURIComponent(modern[2]) || value.id === decodeURIComponent(modern[2]));
          selectedEpisode = selectedTask?.episodes.find(value => value.id === decodeURIComponent(modern[3]));
        }
      } else if (legacy) {
        // Resolve by episode identity first: the same task name can occur on two platforms.
        for (const candidate of platforms) {
          const found = candidate.tasks.find(value => value.episodes.some(item => item.id === decodeURIComponent(legacy[2])));
          if (found) {
            selectedPlatform = candidate; selectedTask = found;
            selectedEpisode = found.episodes.find(value => value.id === decodeURIComponent(legacy[2]));
            break;
          }
        }
      }
    } catch (_) { /* Malformed bookmarks fall back to an available episode. */ }
    selectedPlatform ||= platforms.find(value => value.tasks.some(item => item.episodes.length));
    selectedTask ||= selectedPlatform?.tasks.find(value => value.episodes.length);
    selectedEpisode ||= selectedTask?.episodes[0];
    return { platform: selectedPlatform, task: selectedTask, episode: selectedEpisode };
  }
  const pretty = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  function renderUsage(value) {
    const target = $('token-usage'); target.replaceChildren();
    const valid = count => Number.isSafeInteger(count) && count >= 0;
    const format = count => valid(count) ? count.toLocaleString('en-US') : 'Not recorded';
    const total = usage => valid(usage?.total_tokens) ? usage.total_tokens : valid(usage?.input_tokens) && valid(usage?.output_tokens) ? usage.input_tokens + usage.output_tokens : null;
    const usage = value.usage || {}, tokenUsage = value.token_usage || {};
    const calls = Array.isArray(tokenUsage.calls) ? tokenUsage.calls : [];
    target.append(make('h2', '', 'Token usage · control session'));
    const summary = make('div', 'usage-summary');
    [['Input', usage.input_tokens, `Cached input ${format(usage.cached_input_tokens)}`], ['Output', usage.output_tokens, `Reasoning output ${format(usage.reasoning_output_tokens)}`], ['Total', total(usage), 'Input + output']].forEach(([label, count, note]) => {
      const item = make('div', 'usage-stat');
      item.append(make('span', 'muted', label), make('strong', '', format(count)), make('small', 'muted', note)); summary.append(item);
    });
    target.append(summary);
    const panel = make('details', 'usage-calls');
    panel.append(make('summary', '', `Model calls · ${calls.length || 'Not recorded'}${tokenUsage.complete === false ? ' · Partial records' : ''}`));
    if (calls.length) {
      const wrap = make('div', 'usage-table-wrap'), table = make('table', 'usage-table');
      const head = make('thead'), heading = make('tr');
      ['Call', 'Time (UTC+8)', 'Input', 'Cached', 'Output', 'Reasoning', 'Total'].forEach(label => { const cell = make('th', '', label); cell.scope = 'col'; heading.append(cell); });
      head.append(heading); table.append(head);
      const body = make('tbody');
      calls.forEach((call, index) => {
        const row = make('tr'), entry = call.usage || {};
        const date = call.time ? new Date(call.time) : null;
        const time = date && !Number.isNaN(date.getTime()) ? new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(date) : 'Not recorded';
        [valid(call.index) ? call.index : index + 1, time, ...[entry.input_tokens, entry.cached_input_tokens, entry.output_tokens, entry.reasoning_output_tokens, total(entry)].map(format)].forEach((text, column) => {
          const cell = make('td', '', text); if (column === 1 && call.time) cell.title = call.time; row.append(cell);
        });
        body.append(row);
      });
      table.append(body); wrap.append(table); panel.append(wrap);
    } else panel.append(make('p', 'usage-note muted', 'Per-call token usage was not recorded.'));
    target.append(panel);
  }
  function alertBox(id, message, error = false) {
    const box = $(id);
    box.textContent = message || '';
    box.classList.toggle('hidden', !message);
    box.classList.toggle('error', error);
  }
  function fillBar(node, summary) {
    node.replaceChildren();
    const total = number(summary.episodes);
    [['success', summary.successes], ['failure', summary.failures], ['unscored', summary.unscored], ['unknown', summary.unknown]].forEach(([kind, count]) => {
      const bar = make('span', kind);
      bar.style.width = `${total ? Math.max(0, number(count)) / total * 100 : 0}%`;
      bar.title = `${({success:'Success', failure:'Failure', unscored:'Unscored', unknown:'Unknown result'})[kind]}: ${number(count)}`;
      node.append(bar);
    });
  }
  function renderPlatforms() {
    $('platform-list').replaceChildren(...platforms.map(item => {
      const link = make('a', `platform-item${platform?.id === item.id ? ' active' : ''}`);
      link.href = `#/platforms/${encodeURIComponent(item.id)}`;
      const copy = make('span', 'platform-copy');
      copy.append(make('strong', 'platform-item-label', item.name), make('small', 'platform-item-kind', item.kind === 'physical' ? 'PHYSICAL' : 'SIMULATION'));
      link.append(make('span', 'platform-icon', item.kind === 'physical' ? 'P' : 'R'), copy, make('span', 'platform-count', number(item.summary.episodes)));
      if (platform?.id === item.id) link.setAttribute('aria-current', 'page');
      return link;
    }));
    const physical = platform.kind === 'physical', summary = platform.summary, score = scoreSummary(platform);
    $('platform-name').textContent = platform.name;
    $('platform-kind').textContent = physical ? 'Experiments · Real world' : 'Experiments · Simulation';
    $('platform-tasks').textContent = platform.tasks.length;
    $('platform-episodes').textContent = number(summary.episodes);
    $('overall-rate').replaceChildren(document.createTextNode(percent(score.wins, score.count)), make('span', '', score.label));
    $('overall-count').textContent = physical ? `${summary.episodes} episodes · ${score.wins} / ${score.count} successes`
      : `${platform.tasks.length} tasks · ${summary.episodes} episodes · ${score.wins} / ${score.count} Success`;
    if (!physical && (summary.unscored || summary.unknown)) $('overall-count').textContent += ` · ${number(summary.unscored)} Unscored · ${number(summary.unknown)} Unknown result`;
    fillBar($('overall-bar'), physical ? { episodes: summary.episodes, successes: score.wins, failures: score.count - score.wins, unknown: summary.episodes - score.count } : summary);
    document.documentElement.dataset.platform = platform.id;
  }
  function renderTasks() {
    const normalize = text => text.trim().toLowerCase().replace(/[\s_]+/g, ' ');
    const query = normalize($('task-search').value);
    const tasks = platform.tasks.filter(item => normalize(`${item.name} ${taskTitle(item.name)} ${window.ShowcaseI18n?.translate(taskTitle(item.name), 'zh') || ''}`).includes(query));
    $('task-count').textContent = `${tasks.length} / ${platform.tasks.length}`;
    $('task-list').replaceChildren(...tasks.map(item => {
      const link = make('a', `task-item${task?.id === item.id ? ' active' : ''}`);
      link.href = item.episodes.length ? route(item.episodes[0]) : '#';
      const score = scoreSummary(item);
      link.append(make('span', 'task-name', taskTitle(item.name)), make('span', 'task-score', score.count ? `${score.wins} / ${score.count}` : '—'));
      link.title = `${item.name} · ${item.summary.episodes} episodes · ${score.label} ${percent(score.wins, score.count)}`;
      if (task?.id === item.id) link.setAttribute('aria-current', 'page');
      return link;
    }));
    if (!tasks.length) $('task-list').append(make('p', 'empty-nav', 'No matching tasks'));
  }
  function renderEpisodes() {
    const score = scoreSummary(task);
    $('task-rate').textContent = score.count ? `${score.wins} / ${score.count} successes · ${percent(score.wins, score.count)}` : 'Unscored';
    $('episode-list').replaceChildren(...task.episodes.map(item => {
      const link = make('a', `episode-button${item.id === episode.id ? ' active' : ''}`);
      const [kind, label] = result(item);
      link.href = route(item);
      const thumbnail = make('div', 'episode-thumbnail');
      if (safePath(item.thumbnail)) {
        const image = make('img'); image.src = imagePath(item.thumbnail); image.alt = ''; image.loading = 'lazy';
        image.onerror = () => { thumbnail.replaceChildren(make('span', '', 'No preview')); };
        thumbnail.append(image);
      } else thumbnail.append(make('span', '', 'No preview'));
      link.append(thumbnail);
      link.append(make('span', '', episodeLabel(item)), make('span', `episode-result ${kind}`, `${kind === 'success' ? '●' : kind === 'failure' ? '×' : '○'} ${label}`), make('small', '', item.backend === 'piper' ? `Scene ${item.scene_id ?? '—'}` : `Seed ${item.seed ?? '—'}`));
      if (item.id === episode.id) link.setAttribute('aria-current', 'page');
      link.title = item.run_id || item.id;
      return link;
    }));
  }
  window.registerEpisode = value => {
    if (value && value.id) cache.set(value.id, value);
  };
  function loadEpisode(item) {
    const source = window.ShowcaseContent.episodeScriptPath(item.data_file);
    if (!source) return Promise.reject(new Error('Invalid episode data path.'));
    if (cache.has(item.id)) return Promise.resolve(cache.get(item.id));
    if (pending.has(item.id)) return pending.get(item.id);
    const promise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = source;
      script.onload = () => {
        script.remove();
        cache.has(item.id) ? resolve(cache.get(item.id)) : reject(new Error('Episode data did not register correctly. Please re-export this archive.'));
      };
      script.onerror = () => { script.remove(); reject(new Error(`Unable to load episode file: ${item.data_file}`)); };
      document.head.append(script);
    }).finally(() => pending.delete(item.id));
    pending.set(item.id, promise);
    return promise;
  }
  async function navigate(options = {}) {
    const previousId = episode?.id, previousStep = options.keepStep ? requestedStep : 0;
    const summaryOpen = options.keepStep && $('trace-summary-panel').open;
    const revision = ++navigationRevision;
    const { platform: nextPlatform, task: nextTask, episode: nextEpisode } = selection(location.hash);
    if (!nextEpisode) {
      alertBox('global-alert', 'No displayable episode records were found. Check the source directory and export messages.');
      return;
    }
    if (previousId !== nextEpisode.id || !options.keepStep) requestedStep = 0;
    if (location.hash !== route(nextEpisode)) history.replaceState(null, '', route(nextEpisode));
    stopPlayback();
    frames.clear();
    if (platform?.id !== nextPlatform.id) $('task-search').value = '';
    platform = nextPlatform; task = nextTask; episode = nextEpisode; detail = null;
    $('episode-content').classList.add('hidden');
    $('loading').classList.remove('hidden');
    alertBox('global-alert', (catalog.warnings || []).join('\n'));
    renderPlatforms(); renderTasks(); renderEpisodes();
    try {
      const loaded = await loadEpisode(episode);
      if (revision !== navigationRevision) return;
      const language = window.ShowcaseI18n?.language || 'en';
      const translated = language === 'en' ? await window.EpisodeLanguage.loadEnglish(loaded.id) : null;
      if (revision !== navigationRevision) return;
      detail = window.EpisodeLanguage.applyEnglish(loaded, translated, language);
      await renderEpisode(previousId === loaded.id ? previousStep : 0);
      if (summaryOpen) $('trace-summary-panel').open = true;
      if (revision !== navigationRevision) return;
      $('loading').classList.add('hidden');
      $('episode-content').classList.remove('hidden');
    } catch (error) {
      if (revision !== navigationRevision) return;
      $('loading').classList.add('hidden');
      alertBox('global-alert', `${error.message}\nSelect another episode to continue browsing.`, true);
    }
  }
  async function renderEpisode(initialStep = 0) {
    document.title = `${taskTitle(episode.task)} · ${platform.name} · DreamX-RoboConductor`;
    $('episode-label').textContent = `${episodeLabel(episode)} · ${task.episodes.length} trials`;
    $('episode-title').textContent = taskTitle(episode.task);
    const [kind, label] = result(episode);
    $('episode-status').className = `badge ${kind}`;
    $('episode-status').textContent = label;
    $('instruction').textContent = detail.instruction || '';
    const facts = [platform.kind === 'physical' ? ['Scene', detail.scene_id] : ['Seed', detail.seed],
      ['Turns', detail.turns], ['Control time', formatDuration(detail.execution_duration_seconds)],
      ['Scoring', detail.result_source === 'operator' ? 'Operator' : detail.result_source === 'official' ? 'Official evaluator' : 'Unscored']];
    $('episode-facts').replaceChildren(...facts.filter(([, value]) => value !== null && value !== undefined).map(([name, value]) => {
      const span = make('span'); span.append(document.createTextNode(name), make('b', '', value)); return span;
    }));
    const metadata = [...(platform.kind === 'physical' ? [['Scene', detail.scene_id], ['Mode', detail.execution_mode], ['Outcome source', detail.result_source === 'operator' ? 'Operator confirmation' : 'No native score']] : [['Seed', detail.seed], ['Config', detail.task_config]]), ['Turns', detail.turns], ['Commands', detail.command_steps], ['Model', detail.model], ['Reasoning', detail.reasoning_effort], ['Run', detail.run_id], ['End reason', detail.done_reason],
      ['Total duration', formatDuration(detail.duration_seconds), 'Elapsed evaluation time, including manual preparation, authorization, and outcome-confirmation waits; excludes archive copying.'],
      ['Execution duration', formatDuration(detail.execution_duration_seconds), 'From initial observation to episode closure, including model reasoning and robot execution; this is not motion-only time.']];
    $('metadata').replaceChildren(...metadata.filter(([, value]) => value !== null && value !== undefined && value !== '').map(([key, value, title]) => {
      const span = make('span'); if (title) span.title = title;
      span.append(document.createTextNode(`${key} `), make('b', '', value)); return span;
    }));
    renderUsage(detail);
    $('trace-summary').textContent = detail.public_summary || '';
    $('trace-summary-panel').classList.toggle('hidden', !detail.public_summary);
    $('trace-summary-panel').open = false;
    $('timeline').max = Math.max(0, (detail.steps || []).length - 1);
    $('timeline').disabled = !detail.steps?.length;
    $('play').disabled = (detail.steps || []).length < 2;
    const present = new Set((detail.steps || []).flatMap(step => Object.keys(step.images || {})));
    if (!present.size) present.add('head_camera');
    cameras.forEach(camera => { $(`${camera.replace('_', '-')}-panel`).hidden = !present.has(camera); });
    $('camera-grid').classList.toggle('two-cameras', cameras.filter(camera => present.has(camera)).length === 2);
    const wrists = document.querySelector('.wrist-cameras');
    wrists.hidden = !present.has('left_camera') && !present.has('right_camera');
    wrists.classList.toggle('single-camera', present.has('left_camera') !== present.has('right_camera'));
    $('step-list').replaceChildren(...(detail.steps || []).map((step, index) => {
      const button = make('button', 'step-item');
      button.append(document.createTextNode(step.turn != null ? `Turn ${step.turn}` : `Snapshot ${index + 1}`), make('small', '', eventLabel(step.event)));
      button.onclick = () => { stopPlayback(); showStep(index); };
      return button;
    }));
    renderManual(detail.manual || {});
    alertBox('episode-warnings', (detail.warnings || []).join('\n'));
    await showStep(initialStep);
  }
  function eventLabel(event) {
    return ({ start_episode: 'Initial observation', execute_turn: 'Post-action observation', finish_episode: 'Episode ended', get_observation: 'Observation snapshot' })[event] || event || 'Observation snapshot';
  }
  function imageFor(id, loaded, url) {
    const image = $(id);
    const placeholder = image.nextElementSibling;
    if (loaded) {
      loaded.id = id;
      loaded.alt = image.alt;
      loaded.hidden = false;
      if (loaded !== image) image.replaceWith(loaded);
    } else {
      const empty = make('img');
      empty.id = id; empty.alt = image.alt; empty.hidden = true;
      image.replaceWith(empty);
      placeholder.textContent = url ? 'Image failed to load for this turn' : 'No camera image for this turn';
    }
  }
  function addCode(parent, title, data, folded = false) {
    const block = make(folded ? 'details' : 'section', folded ? 'data-details' : 'trace-block');
    block.append(make(folded ? 'summary' : 'h3', '', title), make('pre', 'code-block', pretty(data)));
    parent.append(block);
  }
  async function showStep(index) {
    if (!detail) return false;
    const current = detail;
    const steps = current.steps || [];
    const nextIndex = Math.max(0, Math.min(index, steps.length - 1));
    requestedStep = nextIndex;
    const step = steps[nextIndex];
    const sources = item => cameras.map(camera => imagePath(item?.images?.[camera]));
    const committed = await frames.show(sources(step), images => {
      stepIndex = nextIndex;
      renderStep(step, images);
    });
    if (committed && current === detail) frames.preload(sources(steps[nextIndex + 1]));
    return committed;
  }
  function renderStep(step, images) {
    const steps = detail.steps || [];
    $('timeline').value = String(stepIndex);
    $('previous-step').disabled = !step || stepIndex === 0;
    $('next-step').disabled = !step || stepIndex === steps.length - 1;
    [...$('step-list').children].forEach((node, i) => {
      node.classList.toggle('active', i === stepIndex);
      if (i === stepIndex) node.setAttribute('aria-current', 'step');
      else node.removeAttribute('aria-current');
    });
    cameras.forEach((camera, index) => imageFor(camera.replace('_', '-'), images[index], step?.images?.[camera]));
    $('step-detail').replaceChildren();
    if (!step) {
      $('step-label').textContent = 'No snapshots available for replay'; $('step-event').textContent = '';
      $('step-detail').append(make('p', 'step-empty', 'No per-turn observation events were archived.')); return;
    }
    $('step-label').textContent = `${step.turn != null ? `Turn ${step.turn}` : 'Initial snapshot'} · ${stepIndex + 1} / ${steps.length}`;
    $('step-event').textContent = eventLabel(step.event);
    const heading = make('div', 'step-detail-heading');
    heading.append(make('strong', '', `${step.turn != null ? `Turn ${step.turn}` : 'Snapshot'} · ${eventLabel(step.event)}`));
    if (step.done) {
      const [kind, label] = platform.kind === 'physical' ? ['unknown', 'Episode ended'] : result({ counted: episode.counted, success: step.success ?? episode.success });
      heading.append(make('span', `badge ${kind}`, label));
    }
    const target = $('step-detail'); target.append(heading);
    const narration = (step.narration || []).filter(Boolean);
    if (narration.length) {
      const block = make('section', 'trace-block'); block.append(make('h3', '', 'Agent'));
      narration.forEach(text => block.append(make('p', 'trace-text', text))); target.append(block);
    }
    if (step.commands?.length) addCode(target, 'Commands', step.commands);
    if (step.command_results?.length) addCode(target, 'Command results', step.command_results);
    if (!narration.length && !step.commands?.length && !step.command_results?.length) target.append(make('p', 'step-empty', 'No public narration or execution commands were archived for this snapshot.'));
    if (step.done_reason) { const block = make('section', 'trace-block'); block.append(make('h3', '', 'End reason'), make('p', 'trace-text', step.done_reason)); target.append(block); }
    if (step.robot_state && Object.keys(step.robot_state).length) addCode(target, 'Robot state', step.robot_state, true);
    if (step.time) heading.title = step.time;
  }
  function inlineText(parent, text) {
    text.split(/(`[^`\n]+`)/g).forEach(part => parent.append(part.startsWith('`') && part.endsWith('`') ? make('code', '', part.slice(1, -1)) : document.createTextNode(part)));
  }
  function renderManual(manual) {
    const target = $('manual-text'); target.replaceChildren();
    const lines = (manual.text || 'No task manual was archived for this episode.').replace(/\r\n/g, '\n').split('\n');
    let code = null, paragraph = [], list = null;
    const flush = () => { if (paragraph.length) { const p = make('p'); inlineText(p, paragraph.join('\n')); target.append(p); paragraph = []; } list = null; };
    lines.forEach(line => {
      if (/^\s*```/.test(line)) { flush(); if (code !== null) { target.append(make('pre', 'code-block', code.join('\n'))); code = null; } else code = []; return; }
      if (code !== null) { code.push(line); return; }
      const heading = line.match(/^(#{1,6})\s+(.+)$/), bullet = line.match(/^\s*(?:[-*+] |\d+\. )(.+)$/);
      if (heading) { flush(); const node = make(`h${Math.min(4, heading[1].length + 1)}`); inlineText(node, heading[2]); target.append(node); }
      else if (bullet) { if (paragraph.length) flush(); if (!list) { list = make('ul'); target.append(list); } const node = make('li'); inlineText(node, bullet[1]); list.append(node); }
      else if (!line.trim()) flush();
      else { list = null; paragraph.push(line); }
    });
    flush(); if (code !== null) target.append(make('pre', 'code-block', code.join('\n')));
    $('manual-media').replaceChildren(...(manual.media || []).filter(item => safePath(item.url)).map(item => {
      const figure = make('figure'), media = make(item.kind === 'video' ? 'video' : 'img');
      media.src = imagePath(item.url);
      if (item.kind === 'video') { media.controls = true; media.preload = 'metadata'; }
      else { media.alt = item.label || 'Task manual attachment'; media.loading = 'lazy'; }
      figure.append(media, make('figcaption', '', item.label || 'Manual attachment')); return figure;
    }));
  }
  function stopPlayback() {
    clearTimeout(timer); timer = null;
    playing = false; playbackRevision++;
    $('play').replaceChildren(document.createTextNode('▶'), make('span', '', 'Play'));
    $('play').setAttribute('aria-label', 'Play snapshots');
  }
  function startPlayback() {
    if (!detail || detail.steps.length < 2) return;
    playing = true;
    const revision = ++playbackRevision;
    $('play').replaceChildren(document.createTextNode('Ⅱ'), make('span', '', 'Pause'));
    $('play').setAttribute('aria-label', 'Pause snapshots');
    const queue = () => {
      if (revision !== playbackRevision) return;
      timer = setTimeout(async () => {
        await showStep(stepIndex + 1);
        if (revision !== playbackRevision) return;
        if (stepIndex >= detail.steps.length - 1) stopPlayback();
        else queue();
      }, 1000 / Number($('speed').value));
    };
    if (stepIndex >= detail.steps.length - 1) showStep(0).then(queue);
    else queue();
  }
  $('task-search').addEventListener('input', renderTasks);
  document.querySelector('.skip-link').addEventListener('click', event => {
    event.preventDefault(); $('main').focus(); $('main').scrollIntoView();
  });
  $('timeline').addEventListener('input', event => { stopPlayback(); showStep(Number(event.target.value)); });
  $('previous-step').onclick = () => { stopPlayback(); showStep(requestedStep - 1); };
  $('next-step').onclick = () => { stopPlayback(); showStep(requestedStep + 1); };
  $('play').onclick = () => playing ? stopPlayback() : startPlayback();
  $('speed').onchange = () => { if (playing) { stopPlayback(); startPlayback(); } };
  window.addEventListener('hashchange', navigate);
  window.addEventListener('showcase:languagechange', () => navigate({keepStep:true}));
  document.addEventListener('visibilitychange', () => { if (document.hidden) stopPlayback(); });
  document.addEventListener('keydown', event => {
    if (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'SUMMARY', 'VIDEO'].includes(event.target.tagName) || event.target.isContentEditable || event.altKey || event.ctrlKey || event.metaKey || !detail) return;
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End', ' '].includes(event.key)) event.preventDefault();
    if (event.key === ' ') playing ? stopPlayback() : startPlayback();
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { stopPlayback(); showStep(requestedStep + (event.key === 'ArrowLeft' ? -1 : 1)); }
    else if (event.key === 'Home' || event.key === 'End') { stopPlayback(); showStep(event.key === 'Home' ? 0 : detail.steps.length - 1); }
  });
  if (!catalog || !Array.isArray(catalog.tasks)) {
    alertBox('global-alert', 'Unable to load catalog.js. Regenerate the viewer and keep its assets beside index.html.', true); return;
  }
  navigate();
})();

'use strict';
(() => {
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const safePath = window.ShowcaseContent.safeLocalPath;
  const archiveEpisode = (backend, task, id) => `archive/#/platforms/${encodeURIComponent(backend)}/tasks/${encodeURIComponent(task)}/episodes/${encodeURIComponent(id)}`;
  const percent = (n, total) => total ? `${Math.round(n / total * 1000) / 10}%` : '—';
  const number = value => Number(value).toLocaleString('en-US');
  const outcomeOf = episode => ['success', 'failure'].includes(episode.outcome) ? episode.outcome : 'pending';
  const outcomeLabel = episode => ({success: 'Success', failure: 'Failure', pending: 'Pending'})[outcomeOf(episode)];
  const players = [];
  let data;
  const mediaPath = value => safePath(data?.media?.[value]?.src || value);
  const thumbnailPath = value => safePath(data?.media?.[value]?.thumbnail || data?.media?.[value]?.src || value);

  function registerPlayer(video) {
    if (players.includes(video)) return;
    players.push(video);
    window.ShowcaseVideo?.attach(video);
  }

  function setVideoSource(video, source, poster) {
    const path = mediaPath(source), image = mediaPath(poster);
    if (window.ShowcaseVideo) window.ShowcaseVideo.setSource(video, path, image);
    else {
      video.pause(); video.src = path; video.poster = image; video.load();
    }
  }

  function setText(selector, value) {
    $$(`[data-bind="${selector}"]`).forEach(node => { node.textContent = value; });
  }

  async function loadData() {
    const response = await fetch('data/page-data.json?v=paper-names-20261110');
    if (!response.ok) throw Error(`HTTP ${response.status}`);
    const value = await response.json();
    if (!value?.simulation?.tasks?.length || !value?.real?.tasks?.length || !value?.walkthrough?.steps?.length) throw Error('Invalid page data');
    return value;
  }

  function fillSummary() {
    const sim = data.simulation, real = data.real;
    const confirmedTrials = real.confirmedTrials ?? real.tasks.reduce((sum, task) => sum + task.episodes.filter(e => outcomeOf(e) !== 'pending').length, 0);
    const taskCount = real.taskCount ?? real.tasks.length;
    setText('real.taskCount', taskCount); setText('real.confirmedTrials', confirmedTrials);
    setText('provenance.archiveEpisodes', data.provenance?.archiveEpisodes ?? sim.trials + real.trials);
    setText('sim.rate', percent(sim.successes, sim.trials));
    setText('sim.detail', `${sim.successes} / ${sim.trials} trials · ${sim.taskCount} RoboTwin 2.0 tasks`);
    setText('sim.perfect', `${sim.perfectTasks} / ${sim.taskCount}`);
    setText('real.rate', percent(real.successes, confirmedTrials));
    setText('real.rateFixed', confirmedTrials ? `${(real.successes / confirmedTrials * 100).toFixed(1)}%` : '—');
    $('.simulation-fill').style.width = percent(sim.successes, sim.trials);
    $('.real-fill').style.width = confirmedTrials ? percent(real.successes, confirmedTrials) : '0%';
    setText('real.trials', real.trials); setText('real.successes', real.successes);
    setText('real.detail', `${real.successes} / ${confirmedTrials} operator-confirmed trials · ${taskCount} tasks`);
    setText('sim.sentence', `${sim.successes} of ${sim.trials}`);
    setText('real.sentence', `${real.successes} of ${confirmedTrials}`);
    setText('sim.tasks', sim.taskCount); setText('sim.trials', sim.trials); setText('sim.successes', sim.successes);
    setText('sim.turnsSuccess', sim.turns.successMedian);
    setText('updatedAt', data.updatedAt);
  }

  function commandLabel(command) {
    if (command.op === 'move_tcp') {
      const move = command.translation_cm || [], rotation = command.rotation_deg || [];
      const parts = [`Move ${command.arm} TCP`, `Δxyz [${move.map(v => `${v > 0 ? '+' : ''}${v}`).join(', ')}] cm`];
      if (rotation.length) parts.push(`Δrpy [${rotation.map(v => `${v > 0 ? '+' : ''}${v}`).join(', ')}]°`);
      if (command.frame) parts.push(`${command.frame} frame`);
      return parts.join(' · ');
    }
    if (command.op === 'set_gripper') return `${command.arm[0].toUpperCase() + command.arm.slice(1)} gripper · ${command.opening === 0 ? 'close' : `opening ${command.opening}`}`;
    return command.op || 'Command';
  }

  function setupWalkthrough() {
    const walkthrough = data.walkthrough, steps = walkthrough.steps;
    const tips = $('#manual-tips');
    tips.replaceChildren(...walkthrough.manual.tips.map(value => { const li = document.createElement('li'); li.textContent = value; return li; }));
    $('#manual-task').replaceChildren(...walkthrough.manual.task.flatMap(([name, value]) => {
      const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = name; dd.textContent = value; return [dt, dd];
    }));
    let selected = 0, camera = 'head', timer, english = null;
    let languageRevision = 0;
    async function updateRecordedLanguage() {
      const revision = ++languageRevision;
      if ((window.ShowcaseI18n?.language || 'en') === 'en') {
        try {
          const value = await window.EpisodeLanguage.loadEnglish(walkthrough.id, 'archive/translations/en/');
          if (revision !== languageRevision) return;
          english = value;
        } catch (_) { english = null; }
      }
      show(selected);
    }
    const image = $('#wt-image'), range = $('#wt-range'), count = $('#wt-count'), turn = $('#wt-turn'), log = $('#wt-log'), play = $('#wt-play');
    const output = $('#wt-output'), speed = $('#wt-speed'), stepNav = $('#wt-steps');
    $('#wt-full-session').href = archiveEpisode('robotwin', walkthrough.task, walkthrough.id);
    const node = (tag, className, text) => { const el = document.createElement(tag); el.className = className; if (text !== undefined) el.textContent = text; return el; };
    const python = value => value === null ? 'None' : typeof value === 'boolean' ? (value ? 'True' : 'False') : Array.isArray(value) ? `[${value.map(python).join(', ')}]` : typeof value === 'object' ? `{${Object.entries(value).map(([k, v]) => `${JSON.stringify(k)}: ${python(v)}`).join(', ')}}` : JSON.stringify(value);
    const call = command => `${command.op}(\n${Object.entries(command).filter(([key]) => key !== 'op').map(([key, value]) => `    ${key}=${python(value)}`).join(',\n')}\n)`;
    function label(step) {
      if (!step.commands.length) return 'Initialize episode';
      if (step.commands.every(command => command.op === 'set_gripper')) return 'Set left gripper';
      const move = step.commands.find(command => command.op === 'move_tcp');
      if (move && step.turn === 6 && move.translation_cm?.join(',') === '0,0,4') return 'Test lift · +4 cm';
      return move ? `Move ${move.arm} TCP` : step.commands[0].op;
    }
    const chips = steps.map((step, index) => {
      const button = node('button', 'wt-step-chip'); button.type = 'button';
      button.append(node('b', '', String(step.turn)), node('span', '', label(step)));
      button.addEventListener('click', () => { stop(); show(index); }); return button;
    });
    stepNav.replaceChildren(...chips);
    const header = node('div', 'wt-output-head'), outputTitle = node('b', 'wt-output-title'), meta = node('span', 'wt-event-meta');
    header.append(outputTitle, meta);
    const code = node('pre', 'wt-code'), codeContent = node('code', ''); code.append(codeContent);
    const details = node('details', 'wt-details'), summary = node('summary', '', 'Inspect recorded model text, commands & state');
    const detailBody = node('div', 'wt-detail-body'); details.append(summary, detailBody);
    output.replaceChildren(header, code, details);
    range.max = String(steps.length - 1);
    function stop() { clearInterval(timer); timer = null; play.setAttribute('aria-label', 'Play episode'); play.innerHTML = '<span class="icon-play" aria-hidden="true"></span>'; }
    function show(index) {
      selected = Math.max(0, Math.min(steps.length - 1, index));
      const step = steps[selected];
      image.src = safePath(step.frames[camera]); image.alt = `${camera === 'head' ? 'Head' : 'Left-wrist'}-camera observation at turn ${step.turn}`;
      range.value = String(selected); count.textContent = `${selected} / ${steps.length - 1}`;
      turn.textContent = `Turn ${step.turn}${step.done ? ` · Task ${step.success ? 'SUCCESS' : 'FAILURE'}` : ''}`;
      chips.forEach((chip, i) => { chip.setAttribute('aria-pressed', String(i === selected)); if (i === selected) chip.setAttribute('aria-current', 'step'); else chip.removeAttribute('aria-current'); });
      [...tips.children].forEach((tip, i) => tip.classList.toggle('wt-tip-active', i === 2 && step.turn === 6));
      outputTitle.textContent = `Turn ${step.turn} · ${label(step)}`;
      meta.textContent = `${step.event} · ${(step.rawCommands || step.commands).length} recorded action calls`;
      const commands = step.rawCommands || step.commands;
      codeContent.textContent = commands.length ? commands.map(call).join('\n\n') : `# Recorded event: ${step.event}\n# Task: ${walkthrough.task} · seed ${walkthrough.seed}\n# First observation received; no movement commands.`;
      const sections = [];
      function section(title, value, rawText = false) {
        const item = node('section', 'wt-raw-section'); item.append(node('h4', '', title), node('pre', 'wt-raw', rawText ? value : JSON.stringify(value, null, 2))); sections.push(item);
      }
      const englishMode = (window.ShowcaseI18n?.language || 'en') === 'en';
      const narration = englishMode ? english?.steps?.[selected]?.narration : step.narration;
      if (narration?.length) section('Recorded model text', narration.join('\n'), true);
      section('Exact commands · translation_cm in cm; rotation_deg in degrees', commands);
      section('Execution results · position_error_cm in cm; rotation_error_deg in degrees', step.rawResults || step.results);
      section('Robot state · TCP xyz in cm; quaternion and direction vectors unitless; gripper opening normalized 0–1', step.robotState || {});
      section('Event metadata', { event: step.event, eventIndex: step.eventIndex, timestamp: step.timestamp, done: step.done, success: step.success, doneReason: step.doneReason });
      detailBody.replaceChildren(...sections);
      const rows = [];
      if (!step.commands.length) rows.push(node('li', 'empty', 'Episode initialized · first observation received'));
      step.commands.forEach((command, i) => {
        const li = node('li', '');
        const feedback = step.results[i] || {}, error = Number.isFinite(feedback.position_error_cm) ? ` · ${feedback.position_error_cm.toFixed(3)} cm position error` : '';
        const status = feedback.target_reached === false ? `target_reached = false${error}` : feedback.target_reached === true ? `target_reached = true${error}` : feedback.status || 'executed';
        li.append(node('span', 'op', command.op === 'move_tcp' ? 'MOVE' : command.op === 'set_gripper' ? 'GRIP' : command.op.toUpperCase()), node('span', '', commandLabel(command)), node('span', `result${feedback.target_reached === false ? ' wt-target-missed' : ''}`, status)); rows.push(li);
      });
      if (step.done) {
        const score = node('li', 'done');
        score.append(node('span', 'op', 'SCORE'), node('span', '', `Official task evaluator${step.doneReason ? ` · ${step.doneReason}` : ''}`), node('span', 'result', step.success ? 'SUCCESS' : 'FAILURE')); rows.push(score);
      }
      log.replaceChildren(...rows);
    }
    function start() {
      if (selected === steps.length - 1) show(0);
      play.setAttribute('aria-label', 'Pause episode'); play.innerHTML = '<span class="icon-pause" aria-hidden="true"></span>';
      timer = setInterval(() => { if (selected === steps.length - 1) stop(); else { show(selected + 1); if (selected === steps.length - 1) stop(); } }, Number(speed.value) || 3000);
    }
    $('#wt-prev').addEventListener('click', () => { stop(); show(selected - 1); });
    $('#wt-next').addEventListener('click', () => { stop(); show(selected + 1); });
    range.addEventListener('input', () => { stop(); show(Number(range.value)); });
    play.addEventListener('click', () => { if (timer) stop(); else start(); });
    speed.addEventListener('change', () => { if (timer) { stop(); start(); } });
    $$('.wt-cams button').forEach(button => button.addEventListener('click', () => {
      stop(); camera = button.dataset.cam; $$('.wt-cams button').forEach(other => other.setAttribute('aria-pressed', String(other === button))); show(selected);
    }));
    show(0);
    window.addEventListener('showcase:languagechange', updateRecordedLanguage);
    updateRecordedLanguage();
  }

  function setupMatrix() {
    const root = $('#trial-matrix'), tip = $('#matrix-tip'), panel = $('#results-matrix');
    const cards = $$('[data-results-kind]');
    const sets = {
      'real-world': { backend: 'piper', label: 'real-world', tasks: data.real.tasks.map(task => ({
        id: task.id, name: task.title,
        trials: task.episodes.map(item => ({ id: item.archiveId, outcome: outcomeOf(item), scene: item.scene, turns: item.turns }))
      })) },
      simulation: { backend: 'robotwin', label: 'simulation', tasks: data.simulation.tasks.map(task => ({
        id: task.id, name: task.name,
        trials: task.outcomes.map(item => ({ id: item.id, outcome: item.success ? 'success' : 'failure', seed: item.seed, turns: item.turns }))
      })) }
    };
    let selected = 'real-world', sort = 'rate';
    function updateCards() {
      cards.forEach(card => {
        const active = card.dataset.resultsKind === selected;
        card.setAttribute('aria-pressed', String(active));
        card.setAttribute('aria-expanded', String(active && panel.open));
        card.classList.toggle('primary-result', active);
      });
    }
    function render() {
      const set = sets[selected], tasks = set.tasks.map(task => ({
        ...task, successes: task.trials.filter(trial => trial.outcome === 'success').length
      }));
      const trials = tasks.flatMap(task => task.trials);
      const sizes = new Set(tasks.map(task => task.trials.length));
      const successes = trials.filter(trial => trial.outcome === 'success').length;
      $('#matrix-title').textContent = `All ${trials.length} ${set.label} trials`;
      $('#matrix-description').textContent = sizes.size === 1
        ? `${tasks.length} tasks × ${tasks[0].trials.length} trials · ${successes} successes`
        : `${tasks.length} tasks · ${trials.length} trials · ${successes} successes`;
      $('#matrix-pending-legend').hidden = !trials.some(trial => trial.outcome === 'pending');
      root.setAttribute('aria-label', selected === 'real-world' ? 'Real-world trials by task' : 'Simulation trials by task');
      root.dataset.kind = selected;
      root.style.setProperty('--matrix-cells-width', `${Math.max(...tasks.map(task => task.trials.length)) * 26 - 6}px`);
      tip.hidden = true;
      tasks.sort((a, b) => sort === 'name' ? a.name.localeCompare(b.name)
        : b.successes / b.trials.length - a.successes / a.trials.length || a.name.localeCompare(b.name));
      const rows = tasks.map(task => {
        const row = document.createElement('div'); row.className = 'matrix-row'; row.setAttribute('role', 'listitem');
        row.hidden = $('#matrix-imperfect').checked && task.successes === task.trials.length;
        const label = document.createElement('a'); label.className = 'matrix-name'; label.textContent = task.name; label.title = task.name;
        label.href = archiveEpisode(set.backend, task.id, task.trials[0].id);
        const cells = document.createElement('span'); cells.className = 'matrix-cells';
        task.trials.forEach((trial, index) => {
          const link = document.createElement('a');
          link.className = `cell ${trial.outcome === 'success' ? 'ok' : trial.outcome === 'failure' ? 'fail' : 'pending'}`;
          link.href = archiveEpisode(set.backend, task.id, trial.id);
          const identity = trial.scene !== undefined ? `scene ${trial.scene}` : `trial ${index + 1}, seed ${trial.seed}`;
          const turns = Number.isFinite(trial.turns) ? ` in ${trial.turns} turns` : '';
          link.setAttribute('aria-label', `${task.name}, ${identity}: ${trial.outcome}${turns}. Open full episode.`);
          const show = event => {
            tip.hidden = false;
            tip.textContent = `${task.name} · ${identity} · ${trial.outcome}${turns} · select for full episode`;
            const x = event.clientX || link.getBoundingClientRect().right, y = event.clientY || link.getBoundingClientRect().bottom;
            tip.style.left = `${Math.max(8, Math.min(innerWidth - 250, x + 12))}px`;
            tip.style.top = `${Math.max(8, Math.min(innerHeight - 45, y + 12))}px`;
          };
          link.addEventListener('pointerenter', show); link.addEventListener('pointermove', show); link.addEventListener('focus', show);
          link.addEventListener('pointerleave', () => { tip.hidden = true; }); link.addEventListener('blur', () => { tip.hidden = true; });
          cells.append(link);
        });
        const score = document.createElement('b'); score.className = 'matrix-score'; score.textContent = `${task.successes} / ${task.trials.length}`;
        row.append(label, cells, score); return row;
      });
      root.replaceChildren(...rows);
      updateCards();
    }
    function selectResults(kind) {
      selected = kind;
      $('#matrix-imperfect').checked = false;
      panel.open = true;
      render();
      panel.scrollIntoView({ block: 'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    }
    cards.forEach(card => card.addEventListener('click', () => selectResults(card.dataset.resultsKind)));
    $('.simulation-group a[href="#results"]')?.addEventListener('click', event => {
      event.preventDefault();
      selectResults('simulation');
    });
    panel.addEventListener('toggle', updateCards);
    $$('.matrix-toolbar [data-sort]').forEach(button => button.addEventListener('click', () => {
      sort = button.dataset.sort;
      $$('.matrix-toolbar [data-sort]').forEach(other => other.setAttribute('aria-pressed', String(other === button)));
      render();
    }));
    $('#matrix-imperfect').addEventListener('change', render);
    render();
  }

  function setupSimulationGallery() {
    const gallery = $('#sim-gallery');
    if (!gallery) return;
    gallery.replaceChildren(...data.simulation.featured.map(item => {
      const figure = document.createElement('figure'); figure.className = 'film-card';
      const video = document.createElement('video'); video.controls = true; video.playsInline = true; video.preload = 'none'; video.poster = mediaPath(item.poster); video.src = mediaPath(item.video); video.setAttribute('aria-label', item.title); registerPlayer(video);
      const caption = document.createElement('figcaption'); const name = document.createElement('a'), meta = document.createElement('span');
      name.className = 'episode-link'; name.href = archiveEpisode('robotwin', item.task, item.id); name.textContent = `${item.title} · full session →`;
      meta.textContent = `seed ${item.seed} · ${item.turns} turns · task ${item.taskSuccesses}/${item.taskTrials}`; caption.append(name, meta); figure.append(video, caption); return figure;
    }));
  }

  function setupRealTasks() {
    const root = $('#real-tasks');
    root.replaceChildren(...data.real.tasks.map((task, taskIndex) => {
      const section = document.createElement('section'); section.className = 'real-task'; section.id = task.id;
      const head = document.createElement('div'); head.className = 'real-task-head';
      const title = document.createElement('div'), description = document.createElement('p'), num = document.createElement('span'), h3 = document.createElement('h3');
      const confirmed = task.episodes.filter(episode => outcomeOf(episode) !== 'pending');
      const successes = confirmed.filter(episode => outcomeOf(episode) === 'success').length;
      const pending = task.episodes.length - confirmed.length;
      num.className = 'num'; num.textContent = `TASK ${String(taskIndex + 1).padStart(2, '0')} · ${successes} / ${confirmed.length} SUCCESS${pending ? ` · ${pending} pending` : ''}`;
      h3.textContent = task.title; title.append(num, h3); description.textContent = task.instructionEn; head.append(title, description);
      const viewer = document.createElement('div'); viewer.className = 'real-viewer';
      const stage = document.createElement('div'); stage.className = 'real-stage'; const video = document.createElement('video'); video.controls = true; video.playsInline = true; video.preload = 'none'; registerPlayer(video);
      const caption = document.createElement('div'); caption.className = 'real-caption'; const capText = document.createElement('div'), capTitle = document.createElement('b'), capMeta = document.createElement('p'), session = document.createElement('a'), outcome = document.createElement('span'); session.className = 'episode-link'; session.textContent = 'Full session →'; capText.append(capTitle, capMeta, session); caption.append(capText, outcome); stage.append(video, caption);
      const list = document.createElement('div'); list.className = 'real-list'; const buttons = [];
      function select(episode, selected) {
        setVideoSource(video, episode.video, episode.poster); video.setAttribute('aria-label', `${task.title}, scene ${episode.scene}, ${outcomeOf(episode)}`);
        capTitle.textContent = `Scene ${String(episode.scene).padStart(2, '0')} · ${outcomeLabel(episode)}`;
        capMeta.textContent = [Number.isFinite(episode.turns) ? `${episode.turns} turns` : '', Number.isFinite(episode.wallClockSeconds) ? `${Math.round(episode.wallClockSeconds / 60)} min wall-clock` : '', Number.isFinite(episode.videoSeconds) ? `${episode.videoSeconds} s observation replay` : 'Observation replay'].filter(Boolean).join(' · ');
        session.href = archiveEpisode('piper', task.id, episode.archiveId);
        outcome.className = `outcome ${outcomeOf(episode)}`; outcome.textContent = outcomeOf(episode);
        buttons.forEach((button, index) => button.setAttribute('aria-pressed', String(index === selected)));
      }
      task.episodes.forEach((episode, index) => {
        const button = document.createElement('button'); button.type = 'button'; button.className = 'trial-button'; button.setAttribute('aria-label', `Scene ${episode.scene}, ${outcomeOf(episode)}`);
        const image = document.createElement('img'); image.src = thumbnailPath(episode.poster); image.decoding = 'async'; image.alt = ''; image.loading = 'lazy'; image.width = 160; image.height = 60;
        const info = window.ShowcaseContent.trialInfo(episode, outcomeOf(episode));
        button.append(image, info); button.addEventListener('click', () => select(episode, index)); list.append(button); buttons.push(button);
      });
      viewer.append(stage, list); section.append(head, viewer); select(task.episodes[0], 0); return section;
    }));
  }

  function setupHero() {
    const simulation = data.simulation.featured.map(item => ({
      id: item.id, video: mediaPath(item.video), poster: mediaPath(item.poster),
      title: item.title, meta: 'Head and wrist observations',
      href: archiveEpisode('robotwin', item.task, item.id)
    }));
    const real = data.real.tasks.flatMap(task => task.episodes.map(item => ({
      id: item.id, video: mediaPath(item.video), poster: mediaPath(item.poster),
      title: task.title,
      meta: `Scene ${String(item.scene).padStart(2, '0')} · ${outcomeLabel(item)}`,
      href: archiveEpisode('piper', task.id, item.archiveId)
    })));
    $$('video[data-hero-kind]').forEach(video => {
      const pool = video.dataset.heroKind === 'real-world' ? real : simulation;
      const item = pool.find(entry => entry.id === video.dataset.heroEpisode);
      if (!item) return;
      const caption = video.closest('figure').querySelector('figcaption');
      const link = document.createElement('a');
      link.textContent = item.title;
      link.href = item.href;
      link.setAttribute('aria-label', `${item.title}: open full episode`);
      caption.querySelector('b').replaceChildren(link);
      video.setAttribute('aria-label', `${item.title} · ${item.meta}`);
      video.src = item.video;
      video.poster = item.poster;
      video.loop = true;
      registerPlayer(video);
    });
  }

  function setupNavigation() {
    const links = $$('.nav-inner nav a').filter(link => link.hash && link.pathname === location.pathname);
    const sections = links.map(link => document.querySelector(link.hash)).filter(Boolean);
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) links.forEach(link => link.setAttribute('aria-current', String(link.hash === `#${entry.target.id}`)));
    }), {rootMargin: '-20% 0px -70%'});
    sections.forEach(section => observer.observe(section));
  }

  function scrollToSection(behavior) {
    if (/^#[A-Za-z][\w-]*$/.test(location.hash)) document.querySelector(location.hash)?.scrollIntoView({block: 'start', behavior});
  }

  window.addEventListener('hashchange', () => requestAnimationFrame(() => scrollToSection('instant')));

  function setupCopy() {
    $$('.copy').forEach(button => button.addEventListener('click', async () => {
      const text = document.getElementById(button.dataset.copy)?.textContent || '';
      try { await navigator.clipboard.writeText(text); button.textContent = 'Copied'; setTimeout(() => button.textContent = 'Copy', 1500); } catch (_) { button.textContent = 'Select text'; }
    }));
  }

  loadData().then(value => {
    data = value; fillSummary(); setupWalkthrough(); setupMatrix(); setupSimulationGallery(); setupRealTasks(); setupHero(); setupNavigation(); setupCopy();
    requestAnimationFrame(() => {
      if (document.documentElement.dataset.refreshAtTop === 'true') {
        window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
      } else scrollToSection('instant');
    });
  }).catch(error => {
    console.error(error);
    const matrix = $('#trial-matrix'); if (matrix) matrix.innerHTML = '<p class="placeholder">Results data could not be loaded. Serve this directory over HTTP and refresh.</p>';
    const real = $('#real-tasks'); if (real) real.innerHTML = '<p class="placeholder">Real-world trial data could not be loaded.</p>';
  });
})();

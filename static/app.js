const cardsEl = document.getElementById('cards');
const finishEl = document.getElementById('finish');
const outputCheapestEl = document.getElementById('outputCheapest');
const outputAllEl = document.getElementById('outputAll');
const outputBothEl = document.getElementById('outputBoth');
const checkEl = document.getElementById('check');
const statusEl = document.getElementById('status');
const progressEl = document.getElementById('progress');
const resultsEl = document.getElementById('results');

let pollTimer = null;
let runStartedAt = 0;
let timerInterval = null;

function parseCards(text) {
  return text.split(/\r?\n|\s*,\s*(?=\d+\s+)/)
    .map(x => x.trim().replace(/^\d+\s+/, '').replace(/^['"]|['"]$/g, ''))
    .filter(Boolean);
}

function money(value) { return `¥${Number(value).toLocaleString('en-US')}`; }
function escapeHtml(s) {
  return String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}
function finishText(row) { return row.foil ? 'Foil' : 'Non-foil'; }

function sortRows(rows, key, direction) {
  const sign = direction === 'desc' ? -1 : 1;
  return [...rows].sort((a, b) => {
    const av = key === 'finish' ? finishText(a) : a[key];
    const bv = key === 'finish' ? finishText(b) : b[key];
    if (key === 'price') return (Number(av) - Number(bv)) * sign;
    return String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: 'base' }) * sign;
  });
}

function uniqueValues(rows, key) {
  const values = rows.map(r => key === 'finish' ? finishText(r) : r[key]);
  return [...new Set(values)].sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' }));
}

function filterRows(rows, filters) {
  const maxPrice = filters.maxPrice === '' ? Infinity : Number(filters.maxPrice);
  return rows.filter(row =>
    row.price <= maxPrice &&
    (!filters.language || row.language === filters.language) &&
    (!filters.expansion || row.expansion === filters.expansion) &&
    (!filters.finish || finishText(row) === filters.finish) &&
    (!filters.title || row.title.toLowerCase().includes(filters.title.toLowerCase()))
  );
}

function selectHtml(id, label, values) {
  return `<label class="filter-control">${label}<select id="${id}"><option value="">All</option>${values.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join('')}</select></label>`;
}

function listingButton(row) {
  if (!row.url) return '<span class="listing-unavailable">Unavailable</span>';
  return `<a class="listing-button" href="${escapeHtml(row.url)}" target="_blank" rel="noopener noreferrer">View listing ↗</a>`;
}

function previewButton(row) {
  const image = row.image_url ? escapeHtml(row.image_url) : '';
  const title = escapeHtml(row.title || 'Card image');
  return `<span class="preview-button" tabindex="0" data-image-url="${image}" data-image-title="${title}" aria-label="Preview card image">Preview</span>`;
}

function renderTable(container, rows, keyPrefix, options = {}) {
  const state = {
    sort: 'price',
    direction: 'asc',
    maxPrice: '',
    language: '',
    expansion: '',
    finish: '',
    title: ''
  };

  function draw() {
    const filtered = sortRows(filterRows(rows, state), state.sort, state.direction);
    const arrow = key => state.sort === key ? (state.direction === 'asc' ? ' ↑' : ' ↓') : '';
    const body = filtered.length ? filtered.map(row => `<tr>
      <td class="price" data-label="Price">${money(row.price)}</td>
      <td data-label="Language">${escapeHtml(row.language)}</td>
      <td data-label="Expansion">${escapeHtml(row.expansion)}</td>
      <td data-label="Finish">${finishText(row)}</td>
      <td data-label="Full title">${escapeHtml(row.title)}</td>
      <td data-label="Listing">${listingButton(row)}</td>
      <td data-label="Preview">${previewButton(row)}</td>
    </tr>`).join('') : `<tr><td colspan="7" class="no-results">No listings match the current filters.</td></tr>`;

    container.querySelector('.table-count').textContent = `${filtered.length} / ${rows.length}`;
    container.querySelector('tbody').innerHTML = body;
    for (const th of container.querySelectorAll('th[data-sort]')) {
      th.textContent = th.dataset.label + arrow(th.dataset.sort);
      th.setAttribute('aria-sort', state.sort === th.dataset.sort ? (state.direction === 'asc' ? 'ascending' : 'descending') : 'none');
    }
  }

  container.innerHTML = `
    <div class="table-tools">
      <details class="filter-details">
        <summary>Filters</summary>
        <div class="filters">
        <label class="filter-control">Max price (¥)<input id="${keyPrefix}-max" type="number" min="0" step="1" placeholder="No limit"></label>
        ${selectHtml(`${keyPrefix}-language`, 'Language', uniqueValues(rows, 'language'))}
        ${selectHtml(`${keyPrefix}-expansion`, 'Expansion', uniqueValues(rows, 'expansion'))}
        ${selectHtml(`${keyPrefix}-finish`, 'Finish', uniqueValues(rows, 'finish'))}
        <label class="filter-control title-filter">Title contains<input id="${keyPrefix}-title" type="text" placeholder="Search title"></label>
        <button class="clear-filters" type="button">Clear</button>
        </div>
      </details>
      <div class="mobile-sort-control">
        <label>Sort by<select class="mobile-sort-select">
          <option value="price">Price</option>
          <option value="language">Language</option>
          <option value="expansion">Expansion</option>
          <option value="finish">Finish</option>
          <option value="title">Full title</option>
        </select></label>
        <button class="mobile-sort-direction" type="button" aria-label="Reverse sort order">↑</button>
      </div>
      <span class="table-count"></span>
    </div>
    <div class="table-wrap"><table>
      <thead><tr>
        <th data-sort="price" data-label="Price" aria-sort="ascending">Price ↑</th>
        <th data-sort="language" data-label="Language">Language</th>
        <th data-sort="expansion" data-label="Expansion">Expansion</th>
        <th data-sort="finish" data-label="Finish">Finish</th>
        <th data-sort="title" data-label="Full title">Full title</th>
        <th class="listing-heading">Listing</th>
        <th class="preview-heading">Preview</th>
      </tr></thead>
      <tbody></tbody>
    </table></div>`;

  container.querySelector(`#${keyPrefix}-max`).addEventListener('input', e => { state.maxPrice = e.target.value; draw(); });
  container.querySelector(`#${keyPrefix}-language`).addEventListener('change', e => { state.language = e.target.value; draw(); });
  container.querySelector(`#${keyPrefix}-expansion`).addEventListener('change', e => { state.expansion = e.target.value; draw(); });
  container.querySelector(`#${keyPrefix}-finish`).addEventListener('change', e => { state.finish = e.target.value; draw(); });
  container.querySelector(`#${keyPrefix}-title`).addEventListener('input', e => { state.title = e.target.value; draw(); });
  container.querySelector('.clear-filters').addEventListener('click', () => {
    Object.assign(state, { maxPrice: '', language: '', expansion: '', finish: '', title: '' });
    container.querySelector(`#${keyPrefix}-max`).value = '';
    container.querySelector(`#${keyPrefix}-language`).value = '';
    container.querySelector(`#${keyPrefix}-expansion`).value = '';
    container.querySelector(`#${keyPrefix}-finish`).value = '';
    container.querySelector(`#${keyPrefix}-title`).value = '';
    draw();
  });
  container.querySelectorAll('th[data-sort]').forEach(th => th.addEventListener('click', () => {
    if (state.sort === th.dataset.sort) state.direction = state.direction === 'asc' ? 'desc' : 'asc';
    else { state.sort = th.dataset.sort; state.direction = 'asc'; }
    const mobileSort = container.querySelector('.mobile-sort-select');
    if (mobileSort) mobileSort.value = state.sort;
    const mobileDirection = container.querySelector('.mobile-sort-direction');
    if (mobileDirection) mobileDirection.textContent = state.direction === 'asc' ? '↑' : '↓';
    draw();
  }));
  const mobileSort = container.querySelector('.mobile-sort-select');
  const mobileDirection = container.querySelector('.mobile-sort-direction');
  if (mobileSort) mobileSort.addEventListener('change', e => {
    state.sort = e.target.value;
    state.direction = 'asc';
    if (mobileDirection) mobileDirection.textContent = '↑';
    draw();
  });
  if (mobileDirection) mobileDirection.addEventListener('click', () => {
    state.direction = state.direction === 'asc' ? 'desc' : 'asc';
    mobileDirection.textContent = state.direction === 'asc' ? '↑' : '↓';
    draw();
  });
  draw();
}

function renderCheapest(results) {
  const rows = results.map(r => r.rows[0] ? {
    card: r.card_name,
    price: r.rows[0].price,
    language: r.rows[0].language,
    expansion: r.rows[0].expansion,
    finish: finishText(r.rows[0]),
    title: r.rows[0].title,
    url: r.rows[0].url,
    image_url: r.rows[0].image_url,
    error: r.error
  } : {
    card: r.card_name, price: null, language: '-', expansion: '-', finish: '-', title: r.card_name, url: '', image_url: '', error: r.error
  });

  const section = document.createElement('section');
  section.className = 'card-result cheapest-section';
  section.innerHTML = `<h2>Cheapest listing for each card</h2>
    <div class="table-tools">
      <details class="filter-details">
        <summary>Filters</summary>
        <div class="filters">
        <label class="filter-control">Max price (¥)<input class="cheap-max" type="number" min="0" step="1" placeholder="No limit"></label>
        <label class="filter-control">Language<select class="cheap-language"><option value="">All</option></select></label>
        <label class="filter-control">Expansion<select class="cheap-expansion"><option value="">All</option></select></label>
        <label class="filter-control">Finish<select class="cheap-finish"><option value="">All</option></select></label>
        <label class="filter-control title-filter">Title contains<input class="cheap-title" type="text" placeholder="Search card/title"></label>
        <button class="clear-filters cheap-clear" type="button">Clear</button>
        </div>
      </details>
      <div class="mobile-sort-control">
        <label>Sort by<select class="mobile-sort-select">
          <option value="card">Card</option>
          <option value="price">Price</option>
          <option value="language">Language</option>
          <option value="expansion">Expansion</option>
          <option value="finish">Finish</option>
          <option value="title">Full title</option>
        </select></label>
        <button class="mobile-sort-direction" type="button" aria-label="Reverse sort order">↑</button>
      </div>
      <span class="table-count"></span>
    </div>
    <div class="table-wrap"><table class="cheapest-table"><thead><tr>
      <th data-sort="card" data-label="Card">Card ↑</th>
      <th data-sort="price" data-label="Price">Price</th>
      <th data-sort="language" data-label="Language">Language</th>
      <th data-sort="expansion" data-label="Expansion">Expansion</th>
      <th data-sort="finish" data-label="Finish">Finish</th>
      <th data-sort="title" data-label="Full title">Full title</th>
      <th class="listing-heading">Listing</th>
      <th class="preview-heading">Preview</th>
    </tr></thead><tbody></tbody></table></div>`;
  resultsEl.appendChild(section);

  const state = { sort: null, direction: 'asc', maxPrice: '', language: '', expansion: '', finish: '', title: '' };
  const values = key => [...new Set(rows.map(r => r[key]).filter(v => v && v !== '-'))].sort((a,b) => String(a).localeCompare(String(b), undefined, {numeric:true, sensitivity:'base'}));
  for (const [cls, key] of [['cheap-language','language'], ['cheap-expansion','expansion'], ['cheap-finish','finish']]) {
    section.querySelector(`.${cls}`).innerHTML += values(key).map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join('');
  }

  const filtered = () => rows.filter(r =>
    (r.price === null || r.price <= (state.maxPrice === '' ? Infinity : Number(state.maxPrice))) &&
    (!state.language || r.language === state.language) &&
    (!state.expansion || r.expansion === state.expansion) &&
    (!state.finish || r.finish === state.finish) &&
    (!state.title || r.title.toLowerCase().includes(state.title.toLowerCase()) || r.card.toLowerCase().includes(state.title.toLowerCase()))
  );
  const sort = arr => {
    if (!state.sort) return [...arr];
    const sign = state.direction === 'desc' ? -1 : 1;
    return [...arr].sort((a, b) => {
      if (state.sort === 'price') {
        if (a.price === null) return 1;
        if (b.price === null) return -1;
        return (a.price - b.price) * sign;
      }
      return String(a[state.sort]).localeCompare(String(b[state.sort]), undefined, {numeric:true, sensitivity:'base'}) * sign;
    });
  };

  function draw() {
    const visible = sort(filtered());
    section.querySelector('.table-count').textContent = `${visible.length} / ${rows.length}`;
    section.querySelector('tbody').innerHTML = visible.map(r => r.price === null ?
      `<tr><td>${escapeHtml(r.card)}</td><td colspan="7">No matching in-stock listing${r.error ? `: ${escapeHtml(r.error)}` : ''}</td></tr>` :
      `<tr><td>${escapeHtml(r.card)}</td><td class="price">${money(r.price)}</td><td>${escapeHtml(r.language)}</td><td>${escapeHtml(r.expansion)}</td><td>${escapeHtml(r.finish)}</td><td>${escapeHtml(r.title)}</td><td>${listingButton(r)}</td><td>${previewButton(r)}</td></tr>`
    ).join('');
    for (const th of section.querySelectorAll('th[data-sort]')) {
      const active = state.sort === th.dataset.sort;
      th.textContent = th.dataset.label + (active ? (state.direction === 'asc' ? ' ↑' : ' ↓') : '');
    }
  }

  section.querySelector('.cheap-max').addEventListener('input', e => { state.maxPrice = e.target.value; draw(); });
  section.querySelector('.cheap-language').addEventListener('change', e => { state.language = e.target.value; draw(); });
  section.querySelector('.cheap-expansion').addEventListener('change', e => { state.expansion = e.target.value; draw(); });
  section.querySelector('.cheap-finish').addEventListener('change', e => { state.finish = e.target.value; draw(); });
  section.querySelector('.cheap-title').addEventListener('input', e => { state.title = e.target.value; draw(); });
  section.querySelector('.cheap-clear').addEventListener('click', () => {
    Object.assign(state, {maxPrice:'', language:'', expansion:'', finish:'', title:''});
    section.querySelector('.cheap-max').value = '';
    section.querySelector('.cheap-language').value = '';
    section.querySelector('.cheap-expansion').value = '';
    section.querySelector('.cheap-finish').value = '';
    section.querySelector('.cheap-title').value = '';
    draw();
  });
  section.querySelectorAll('th[data-sort]').forEach(th => th.addEventListener('click', () => {
    if (state.sort === th.dataset.sort) state.direction = state.direction === 'asc' ? 'desc' : 'asc';
    else { state.sort = th.dataset.sort; state.direction = 'asc'; }
    const mobileSort = section.querySelector('.mobile-sort-select');
    if (mobileSort) mobileSort.value = state.sort;
    const mobileDirection = section.querySelector('.mobile-sort-direction');
    if (mobileDirection) mobileDirection.textContent = state.direction === 'asc' ? '↑' : '↓';
    draw();
  }));
  const mobileSort = section.querySelector('.mobile-sort-select');
  const mobileDirection = section.querySelector('.mobile-sort-direction');
  if (mobileSort) mobileSort.addEventListener('change', e => {
    state.sort = e.target.value;
    state.direction = 'asc';
    if (mobileDirection) mobileDirection.textContent = '↑';
    draw();
  });
  if (mobileDirection) mobileDirection.addEventListener('click', () => {
    state.direction = state.direction === 'asc' ? 'desc' : 'asc';
    mobileDirection.textContent = state.direction === 'asc' ? '↑' : '↓';
    draw();
  });
  draw();
}

function renderIndividuals(results) {
  const section = document.createElement('section');
  section.className = 'card-result individual-section';
  section.innerHTML = `<h2>All results</h2><div class="tabbar" role="tablist"></div><div class="tab-panels"></div>`;
  const tabbar = section.querySelector('.tabbar');
  const panels = section.querySelector('.tab-panels');

  results.forEach((r, index) => {
    const tab = document.createElement('button');
    tab.className = 'tab';
    tab.type = 'button';
    tab.textContent = r.card_name;
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-selected', index === 0 ? 'true' : 'false');
    tab.id = `tab-${index}`;

    const panel = document.createElement('div');
    panel.className = 'tab-panel';
    panel.hidden = index !== 0;
    panel.setAttribute('role', 'tabpanel');
    panel.setAttribute('aria-labelledby', tab.id);
    if (r.error) panel.innerHTML = `<div class="error">${escapeHtml(r.error)}</div>`;
    else renderTable(panel, r.rows, `card-${index}`);

    tab.addEventListener('click', () => {
      section.querySelectorAll('.tab').forEach(t => {
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
      });
      section.querySelectorAll('.tab-panel').forEach(p => { p.hidden = true; });
      tab.classList.add('active');
      tab.setAttribute('aria-selected', 'true');
      panel.hidden = false;
      requestAnimationFrame(fitResultSections);
    });

    if (index === 0) tab.classList.add('active');
    tabbar.appendChild(tab);
    panels.appendChild(panel);
  });
  resultsEl.appendChild(section);
}

function render(results, output) {
  resultsEl.classList.remove('hidden');
  resultsEl.innerHTML = '';
  if (output === 'cheapest' || output === 'both') renderCheapest(results);
  if (output === 'individual' || output === 'both') renderIndividuals(results);
  requestAnimationFrame(() => { syncMobileFilters(); fitResultSections(); });
}

function fitResultSections() {
  const sections = [...resultsEl.querySelectorAll('.card-result')];
  if (!sections.length) return;
  if (window.matchMedia('(max-width: 700px)').matches) {
    const width = Math.max(280, window.innerWidth - 20);
    for (const section of sections) section.style.width = `${width}px`;
    return;
  }
  const maxViewportWidth = Math.max(320, window.innerWidth - 32);
  let requiredWidth = 0;
  for (const section of sections) {
    const wasHidden = section.hidden;
    if (wasHidden) section.hidden = false;
    const previousWidth = section.style.width;
    section.style.width = 'max-content';
    const tableWidths = [...section.querySelectorAll('table')].map(t => t.scrollWidth);
    requiredWidth = Math.max(requiredWidth, ...tableWidths, section.scrollWidth);
    section.style.width = previousWidth;
    if (wasHidden) section.hidden = true;
  }
  const width = Math.min(Math.ceil(requiredWidth), maxViewportWidth);
  for (const section of sections) section.style.width = `${width}px`;
}


function outputMode() {
  if (outputBothEl.checked) return 'both';
  if (outputAllEl.checked) return 'individual';
  return 'cheapest';
}

function formatDuration(seconds) {
  const whole = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const secs = whole % 60;
  return hours > 0
    ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function updateTiming(completed, total, finished = false) {
  const elapsed = runStartedAt ? (Date.now() - runStartedAt) / 1000 : 0;
  const elapsedText = `Elapsed ${formatDuration(elapsed)}`;
  if (finished) {
    statusEl.textContent = `Finished: ${completed}/${total} • ${elapsedText}`;
    return;
  }
  if (total >= 10 && completed > 0 && completed < total) {
    const remaining = Math.max(0, elapsed * (total - completed) / completed);
    statusEl.textContent = `Checking cards • ${completed}/${total} • ${elapsedText} • Estimated time left ${formatDuration(remaining)}`;
  } else {
    statusEl.textContent = `Checking cards • ${completed}/${total} • ${elapsedText}`;
  }
}

function startTimer() {
  if (timerInterval) clearInterval(timerInterval);
  runStartedAt = Date.now();
  updateTiming(0, 0);
  timerInterval = setInterval(() => {
    const elapsed = (Date.now() - runStartedAt) / 1000;
    const current = statusEl.textContent;
    if (!current.startsWith('Finished')) {
      const match = current.match(/Checking cards • (\d+)\/(\d+)/);
      if (match) updateTiming(Number(match[1]), Number(match[2]));
      else statusEl.textContent = `Checking cards • ${formatDuration(elapsed)}`;
    }
  }, 250);
}

function stopTimer() {
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
}

async function start() {
  if (pollTimer) clearTimeout(pollTimer);
  const cards = parseCards(cardsEl.value);
  if (!cards.length) { statusEl.textContent = 'Enter at least one card.'; return; }
  if (cards.length > 100) { statusEl.textContent = 'Maximum 100 cards per job.'; return; }

  checkEl.disabled = true;
  resultsEl.classList.add('hidden');
  resultsEl.innerHTML = '';
  progressEl.style.width = '0%';
  statusEl.textContent = `Submitting ${cards.length} card${cards.length === 1 ? '' : 's'}...`;
  startTimer();

  try {
    const response = await fetch('/api/jobs', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({cards, finish:finishEl.value, output:outputMode()})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not create job.');
    poll(data.job_id);
  } catch (e) {
    stopTimer();
    statusEl.textContent = `Error: ${e.message}`;
    checkEl.disabled = false;
  }
}

async function poll(jobId) {
  try {
    const response = await fetch(`/api/jobs/${jobId}`);
    const job = await response.json();
    if (!response.ok) throw new Error(job.detail || 'Could not read job.');
    const pct = job.total ? Math.round(job.completed / job.total * 100) : 100;
    progressEl.style.width = `${pct}%`;
    if (job.status === 'complete') updateTiming(job.completed, job.total, true);
    else updateTiming(job.completed, job.total);
    if (job.status === 'complete') {
      render(job.results, job.output);
      stopTimer();
      checkEl.disabled = false;
      return;
    }
    if (job.status === 'error') throw new Error(job.error || 'Job failed.');
    pollTimer = setTimeout(() => poll(jobId), 800);
  } catch (e) {
    stopTimer();
    statusEl.textContent = `Error: ${e.message}`;
    checkEl.disabled = false;
  }
}

checkEl.addEventListener('click', start);


let previewOverlay = null;
let previewHideTimer = null;

function ensurePreviewOverlay() {
  if (previewOverlay) return previewOverlay;
  previewOverlay = document.createElement('div');
  previewOverlay.className = 'image-preview-overlay';
  previewOverlay.setAttribute('role', 'tooltip');
  previewOverlay.hidden = true;
  document.body.appendChild(previewOverlay);
  return previewOverlay;
}

function hidePreview() {
  if (previewHideTimer) clearTimeout(previewHideTimer);
  const overlay = ensurePreviewOverlay();
  overlay.hidden = true;
}

function positionPreview(button) {
  const overlay = ensurePreviewOverlay();
  if (overlay.hidden) return;
  const rect = button.getBoundingClientRect();
  const gap = 10;
  const margin = 10;
  const overlayWidth = Math.min(overlay.scrollWidth, window.innerWidth - margin * 2);
  const overlayHeight = Math.min(overlay.scrollHeight, window.innerHeight - margin * 2);

  let left = rect.left + rect.width / 2 - overlayWidth / 2;
  left = Math.max(margin, Math.min(left, window.innerWidth - overlayWidth - margin));

  const spaceAbove = rect.top - gap - margin;
  const spaceBelow = window.innerHeight - rect.bottom - gap - margin;
  let top;
  if (overlayHeight <= spaceAbove || spaceAbove >= spaceBelow) {
    top = rect.top - overlayHeight - gap;
  } else {
    top = rect.bottom + gap;
  }
  top = Math.max(margin, Math.min(top, window.innerHeight - overlayHeight - margin));

  overlay.style.left = `${Math.round(left)}px`;
  overlay.style.top = `${Math.round(top)}px`;
}


function showPreview(button) {
  if (previewHideTimer) clearTimeout(previewHideTimer);
  const overlay = ensurePreviewOverlay();
  const url = button.dataset.imageUrl || '';
  const title = button.dataset.imageTitle || 'Card image';
  overlay.hidden = false;

  if (!url) {
    overlay.innerHTML = '<div class="preview-message">Unable to load image.</div>';
    positionPreview(button);
    return;
  }

  overlay.innerHTML = `<img src="${escapeHtml(url)}" alt="${title}">`;
  const img = overlay.querySelector('img');
  img.addEventListener('load', () => positionPreview(button), {once:true});
  img.addEventListener('error', () => {
    overlay.innerHTML = '<div class="preview-message">Unable to load image.</div>';
    positionPreview(button);
  }, {once:true});
  positionPreview(button);
}

function isMobileViewport() {
  return window.matchMedia('(max-width: 700px)').matches;
}

function syncMobileFilters() {
  const mobile = isMobileViewport();
  document.querySelectorAll('.filter-details').forEach(details => {
    if (mobile) details.removeAttribute('open');
    else details.setAttribute('open', '');
  });
}

function toggleMobilePreview(button) {
  const overlay = ensurePreviewOverlay();
  const isSame = overlay.dataset.previewButtonId === button.dataset.previewId;
  if (isSame && !overlay.hidden) {
    hidePreview();
    return;
  }
  const previewId = button.dataset.previewId || `preview-${Math.random().toString(36).slice(2)}`;
  button.dataset.previewId = previewId;
  overlay.dataset.previewButtonId = previewId;
  showPreview(button);
}

document.addEventListener('mouseover', event => {
  if (isMobileViewport()) return;
  const button = event.target.closest('.preview-button');
  if (button) showPreview(button);
});
document.addEventListener('mouseout', event => {
  const button = event.target.closest('.preview-button');
  if (!button || button.contains(event.relatedTarget)) return;
  previewHideTimer = setTimeout(hidePreview, 80);
});
document.addEventListener('focusin', event => {
  const button = event.target.closest('.preview-button');
  if (button && !isMobileViewport()) showPreview(button);
});
document.addEventListener('focusout', event => {
  if (event.target.closest('.preview-button') && !isMobileViewport()) previewHideTimer = setTimeout(hidePreview, 80);
});
document.addEventListener('click', event => {
  const button = event.target.closest('.preview-button');
  if (button && isMobileViewport()) {
    toggleMobilePreview(button);
    return;
  }
  if (isMobileViewport() && previewOverlay && !previewOverlay.hidden) hidePreview();
});

window.addEventListener('scroll', hidePreview, true);
window.addEventListener('resize', hidePreview);

window.addEventListener('resize', () => {
  syncMobileFilters();
  if (!resultsEl.classList.contains('hidden')) fitResultSections();
});

syncMobileFilters();

const cardsEl = document.getElementById('cards');
const finishEl = document.getElementById('finish');
const outputCheapestEl = document.getElementById('outputCheapest');
const outputAllEl = document.getElementById('outputAll');
const outputBothEl = document.getElementById('outputBoth');
const checkEl = document.getElementById('check');
const statusEl = document.getElementById('status');
const progressEl = document.getElementById('progress');
const resultsEl = document.getElementById('results');
const viewToggleEl = document.getElementById('viewToggle');

let pollTimer = null;
let runStartedAt = 0;
let timerInterval = null;
let viewMode = 'desktop';

function isMobileDevice() {
  return window.matchMedia('(max-width: 700px)').matches ||
    (window.matchMedia('(pointer: coarse)').matches && window.matchMedia('(hover: none)').matches);
}

function setViewMode(mode) {
  viewMode = mode === 'mobile' ? 'mobile' : 'desktop';
  document.body.classList.toggle('mobile-ui', viewMode === 'mobile');
  document.body.classList.toggle('desktop-ui', viewMode === 'desktop');
  viewToggleEl.setAttribute('aria-pressed', String(viewMode === 'mobile'));
  viewToggleEl.textContent = viewMode === 'mobile' ? 'Switch to Desktop view' : 'Switch to Mobile view';
  hidePreview();
  if (viewMode === 'mobile') {
    document.querySelectorAll('.card-result').forEach(section => section.style.removeProperty('width'));
  } else if (!resultsEl.classList.contains('hidden')) {
    requestAnimationFrame(fitResultSections);
  }
}

function parseCards(text) {
  return text.split(/\r?\n|\s*,\s*(?=\d+\s+)/)
    .map(x => x.trim().replace(/^\d+\s+/, '').replace(/^['"]|['"]$/g, ''))
    .filter(Boolean);
}

function money(value, eurJpyRate = null) {
  const yen = `¥${Number(value).toLocaleString('en-US')}`;
  return Number.isFinite(eurJpyRate) && eurJpyRate > 0
    ? `${yen} <span class="euro-price">(€ ${(Number(value) / eurJpyRate).toFixed(2)})</span>`
    : yen;
}
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

function mobileListingCard(row, eurJpyRate, heading = '') {
  const title = escapeHtml(row.title || heading);
  return `<article class="mobile-listing-card">
    ${heading ? `<div class="mobile-card-heading">${escapeHtml(heading)}</div>` : ''}
    <div class="mobile-card-price">${money(row.price, eurJpyRate)}</div>
    <div class="mobile-card-meta"><span>${escapeHtml(row.language)}</span><span>${escapeHtml(row.expansion)}</span><span>${finishText(row)}</span></div>
    <div class="mobile-card-title">${title}</div>
    <div class="mobile-card-actions">${listingButton(row)}${previewButton(row)}</div>
  </article>`;
}

function mobileFilterPanel(prefix, values) {
  return `<div class="mobile-filter-panel" id="${prefix}-mobile-filters" hidden>
    <label class="filter-control">Max price (¥)<input id="${prefix}-mobile-max" type="number" min="0" step="1" placeholder="No limit"></label>
    ${selectHtml(`${prefix}-mobile-language`, 'Language', values.language)}
    ${selectHtml(`${prefix}-mobile-expansion`, 'Expansion', values.expansion)}
    ${selectHtml(`${prefix}-mobile-finish`, 'Finish', values.finish)}
    <label class="filter-control title-filter">Title contains<input id="${prefix}-mobile-title" type="text" placeholder="Search title"></label>
    <button class="clear-filters mobile-clear" type="button">Clear filters</button>
  </div>`;
}

function mobileSortHtml(prefix, options) {
  return `<label class="mobile-sort">Sort by<select id="${prefix}-mobile-sort">${options.map(([value,label]) => `<option value="${value}">${label}</option>`).join('')}</select></label>`;
}

function renderTable(container, rows, keyPrefix, eurJpyRate = null, options = {}) {
  const state = {
    sort: 'price',
    direction: 'asc',
    maxPrice: '',
    language: '',
    expansion: '',
    finish: '',
    title: ''
  };
  const values = {
    language: uniqueValues(rows, 'language'),
    expansion: uniqueValues(rows, 'expansion'),
    finish: uniqueValues(rows, 'finish')
  };

  container.innerHTML = `
    <div class="desktop-results">
      <div class="table-tools">
        <div class="filters">
          <label class="filter-control">Max price (¥)<input id="${keyPrefix}-max" type="number" min="0" step="1" placeholder="No limit"></label>
          ${selectHtml(`${keyPrefix}-language`, 'Language', values.language)}
          ${selectHtml(`${keyPrefix}-expansion`, 'Expansion', values.expansion)}
          ${selectHtml(`${keyPrefix}-finish`, 'Finish', values.finish)}
          <label class="filter-control title-filter">Title contains<input id="${keyPrefix}-title" type="text" placeholder="Search title"></label>
          <button class="clear-filters" type="button">Clear</button>
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
      </table></div>
    </div>
    <div class="mobile-results">
      <div class="mobile-toolbar">
        ${mobileSortHtml(`${keyPrefix}`, [['price-asc','Price ↑'],['price-desc','Price ↓'],['language-asc','Language A–Z'],['language-desc','Language Z–A'],['expansion-asc','Expansion A–Z'],['expansion-desc','Expansion Z–A'],['finish-asc','Finish A–Z'],['finish-desc','Finish Z–A'],['title-asc','Title A–Z'],['title-desc','Title Z–A']])}
        <button class="mobile-filter-toggle" type="button" aria-expanded="false">Filters</button>
        <span class="table-count"></span>
      </div>
      ${mobileFilterPanel(keyPrefix, values)}
      <div class="mobile-list"></div>
    </div>`;

  const mobileSort = container.querySelector(`#${keyPrefix}-mobile-sort`);
  const mobileFilters = container.querySelector(`#${keyPrefix}-mobile-filters`);
  const mobileFilterButton = container.querySelector('.mobile-filter-toggle');

  function setSort(value) {
    const [column, direction] = value.split('-');
    state.sort = column;
    state.direction = direction;
  }

  function currentMobileSort() {
    return `${state.sort}-${state.direction}`;
  }

  function draw() {
    const filtered = sortRows(filterRows(rows, state), state.sort, state.direction);
    const count = `${filtered.length} / ${rows.length}`;
    container.querySelectorAll('.table-count').forEach(el => { el.textContent = count; });
    const body = filtered.length ? filtered.map(row => `<tr>
      <td class="price">${money(row.price, eurJpyRate)}</td>
      <td>${escapeHtml(row.language)}</td>
      <td>${escapeHtml(row.expansion)}</td>
      <td>${finishText(row)}</td>
      <td>${escapeHtml(row.title)}</td>
      <td>${listingButton(row)}</td>
      <td>${previewButton(row)}</td>
    </tr>`).join('') : `<tr><td colspan="7" class="no-results">No listings match the current filters.</td></tr>`;
    container.querySelector('.desktop-results tbody').innerHTML = body;

    const mobileBody = filtered.length
      ? filtered.map(row => mobileListingCard(row, eurJpyRate)).join('')
      : '<div class="no-results">No listings match the current filters.</div>';
    container.querySelector('.mobile-list').innerHTML = mobileBody;

    const arrow = key => state.sort === key ? (state.direction === 'asc' ? ' ↑' : ' ↓') : '';
    for (const th of container.querySelectorAll('th[data-sort]')) {
      th.textContent = th.dataset.label + arrow(th.dataset.sort);
      th.setAttribute('aria-sort', state.sort === th.dataset.sort ? (state.direction === 'asc' ? 'ascending' : 'descending') : 'none');
    }
    mobileSort.value = currentMobileSort();
  }

  const bind = (selector, key, event = 'change') => {
    container.querySelector(selector)?.addEventListener(event, e => { state[key] = e.target.value; draw(); });
  };
  bind(`#${keyPrefix}-max`, 'maxPrice', 'input');
  bind(`#${keyPrefix}-language`, 'language');
  bind(`#${keyPrefix}-expansion`, 'expansion');
  bind(`#${keyPrefix}-finish`, 'finish');
  bind(`#${keyPrefix}-title`, 'title', 'input');
  bind(`#${keyPrefix}-mobile-max`, 'maxPrice', 'input');
  bind(`#${keyPrefix}-mobile-language`, 'language');
  bind(`#${keyPrefix}-mobile-expansion`, 'expansion');
  bind(`#${keyPrefix}-mobile-finish`, 'finish');
  bind(`#${keyPrefix}-mobile-title`, 'title', 'input');

  const clear = () => {
    Object.assign(state, { maxPrice: '', language: '', expansion: '', finish: '', title: '' });
    for (const selector of [`#${keyPrefix}-max`, `#${keyPrefix}-mobile-max`]) { const el = container.querySelector(selector); if (el) el.value = ''; }
    for (const selector of [`#${keyPrefix}-language`, `#${keyPrefix}-mobile-language`, `#${keyPrefix}-expansion`, `#${keyPrefix}-mobile-expansion`, `#${keyPrefix}-finish`, `#${keyPrefix}-mobile-finish`]) {
      const el = container.querySelector(selector); if (el) el.value = '';
    }
    for (const selector of [`#${keyPrefix}-title`, `#${keyPrefix}-mobile-title`]) { const el = container.querySelector(selector); if (el) el.value = ''; }
    draw();
  };
  container.querySelector('.clear-filters').addEventListener('click', clear);
  container.querySelector('.mobile-clear').addEventListener('click', clear);
  mobileFilterButton.addEventListener('click', () => {
    const open = mobileFilters.hidden;
    mobileFilters.hidden = !open;
    mobileFilterButton.setAttribute('aria-expanded', String(open));
  });
  mobileSort.addEventListener('change', e => { setSort(e.target.value); draw(); });

  container.querySelectorAll('.desktop-results th[data-sort]').forEach(th => th.addEventListener('click', () => {
    if (state.sort === th.dataset.sort) state.direction = state.direction === 'asc' ? 'desc' : 'asc';
    else { state.sort = th.dataset.sort; state.direction = 'asc'; }
    draw();
  }));
  draw();
}

function renderCheapest(results, eurJpyRate) {
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
    <div class="desktop-results">
      <div class="table-tools">
        <div class="filters">
          <label class="filter-control">Max price (¥)<input class="cheap-max" type="number" min="0" step="1" placeholder="No limit"></label>
          <label class="filter-control">Language<select class="cheap-language"><option value="">All</option></select></label>
          <label class="filter-control">Expansion<select class="cheap-expansion"><option value="">All</option></select></label>
          <label class="filter-control">Finish<select class="cheap-finish"><option value="">All</option></select></label>
          <label class="filter-control title-filter">Title contains<input class="cheap-title" type="text" placeholder="Search card/title"></label>
          <button class="clear-filters cheap-clear" type="button">Clear</button>
        </div>
        <span class="table-count"></span>
      </div>
      <div class="table-wrap"><table class="cheapest-table"><thead><tr>
        <th data-sort="card" data-label="Card">Card</th>
        <th data-sort="price" data-label="Price">Price</th>
        <th data-sort="language" data-label="Language">Language</th>
        <th data-sort="expansion" data-label="Expansion">Expansion</th>
        <th data-sort="finish" data-label="Finish">Finish</th>
        <th data-sort="title" data-label="Full title">Full title</th>
        <th class="listing-heading">Listing</th>
        <th class="preview-heading">Preview</th>
      </tr></thead><tbody></tbody></table></div>
    </div>
    <div class="mobile-results">
      <div class="mobile-toolbar">
        ${mobileSortHtml('cheap', [['input','Input order'],['price-asc','Price ↑'],['price-desc','Price ↓'],['card-asc','Card A–Z'],['card-desc','Card Z–A'],['language-asc','Language A–Z'],['expansion-asc','Expansion A–Z'],['finish-asc','Finish A–Z'],['title-asc','Title A–Z']])}
        <button class="mobile-filter-toggle" type="button" aria-expanded="false">Filters</button>
        <span class="table-count"></span>
      </div>
      <div class="mobile-filter-panel" hidden>
        <label class="filter-control">Max price (¥)<input class="cheap-mobile-max" type="number" min="0" step="1" placeholder="No limit"></label>
        <label class="filter-control">Language<select class="cheap-mobile-language"><option value="">All</option></select></label>
        <label class="filter-control">Expansion<select class="cheap-mobile-expansion"><option value="">All</option></select></label>
        <label class="filter-control">Finish<select class="cheap-mobile-finish"><option value="">All</option></select></label>
        <label class="filter-control title-filter">Title contains<input class="cheap-mobile-title" type="text" placeholder="Search card/title"></label>
        <button class="clear-filters mobile-clear" type="button">Clear filters</button>
      </div>
      <div class="mobile-list"></div>
    </div>`;
  resultsEl.appendChild(section);

  const state = { sort: null, direction: 'asc', maxPrice: '', language: '', expansion: '', finish: '', title: '' };
  const values = key => [...new Set(rows.map(r => r[key]).filter(v => v && v !== '-'))].sort((a,b) => String(a).localeCompare(String(b), undefined, {numeric:true, sensitivity:'base'}));
  for (const [cls, key] of [['cheap-language','language'], ['cheap-expansion','expansion'], ['cheap-finish','finish'], ['cheap-mobile-language','language'], ['cheap-mobile-expansion','expansion'], ['cheap-mobile-finish','finish']]) {
    section.querySelector(`.${cls}`).innerHTML += values(key).map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join('');
  }

  const filtered = () => rows.filter(r =>
    (r.price === null || r.price <= (state.maxPrice === '' ? Infinity : Number(state.maxPrice))) &&
    (!state.language || r.language === state.language) &&
    (!state.expansion || r.expansion === state.expansion) &&
    (!state.finish || r.finish === state.finish) &&
    (!state.title || r.title.toLowerCase().includes(state.title.toLowerCase()) || r.card.toLowerCase().includes(state.title.toLowerCase()))
  );
  const sorted = arr => {
    if (!state.sort || state.sort === 'input') return [...arr];
    const [key, direction] = state.sort.split('-');
    const sign = direction === 'desc' ? -1 : 1;
    return [...arr].sort((a,b) => {
      if (key === 'price') {
        if (a.price === null) return 1;
        if (b.price === null) return -1;
        return (a.price - b.price) * sign;
      }
      return String(a[key]).localeCompare(String(b[key]), undefined, {numeric:true, sensitivity:'base'}) * sign;
    });
  };
  const setFilter = (key, selector, event='change') => section.querySelector(selector)?.addEventListener(event, e => { state[key] = e.target.value; draw(); });

  function draw() {
    const visible = sorted(filtered());
    section.querySelectorAll('.table-count').forEach(el => { el.textContent = `${visible.length} / ${rows.length}`; });
    section.querySelector('.cheapest-table tbody').innerHTML = visible.map(r => r.price === null ?
      `<tr><td>${escapeHtml(r.card)}</td><td colspan="7">No matching in-stock listing${r.error ? `: ${escapeHtml(r.error)}` : ''}</td></tr>` :
      `<tr><td>${escapeHtml(r.card)}</td><td class="price">${money(r.price, eurJpyRate)}</td><td>${escapeHtml(r.language)}</td><td>${escapeHtml(r.expansion)}</td><td>${escapeHtml(r.finish)}</td><td>${escapeHtml(r.title)}</td><td>${listingButton(r)}</td><td>${previewButton(r)}</td></tr>`
    ).join('');
    section.querySelector('.mobile-list').innerHTML = visible.map(r => r.price === null
      ? `<article class="mobile-listing-card"><div class="mobile-card-heading">${escapeHtml(r.card)}</div><div class="mobile-card-title">No matching in-stock listing${r.error ? `: ${escapeHtml(r.error)}` : ''}</div></article>`
      : mobileListingCard(r, eurJpyRate, r.card)
    ).join('') || '<div class="no-results">No listings match the current filters.</div>';
    const mobileSort = section.querySelector('.mobile-toolbar select');
    mobileSort.value = state.sort ? state.sort : 'input';
    for (const th of section.querySelectorAll('th[data-sort]')) {
      const key = th.dataset.sort;
      const active = state.sort && state.sort.startsWith(key);
      const direction = active ? (state.sort.endsWith('-desc') ? ' ↓' : ' ↑') : '';
      th.textContent = th.dataset.label + direction;
    }
  }

  setFilter('maxPrice', '.cheap-max', 'input'); setFilter('language', '.cheap-language'); setFilter('expansion', '.cheap-expansion'); setFilter('finish', '.cheap-finish'); setFilter('title', '.cheap-title', 'input');
  setFilter('maxPrice', '.cheap-mobile-max', 'input'); setFilter('language', '.cheap-mobile-language'); setFilter('expansion', '.cheap-mobile-expansion'); setFilter('finish', '.cheap-mobile-finish'); setFilter('title', '.cheap-mobile-title', 'input');
  section.querySelector('.clear-filters').addEventListener('click', () => { Object.assign(state,{maxPrice:'',language:'',expansion:'',finish:'',title:''}); section.querySelector('.cheap-max').value=''; section.querySelector('.cheap-language').value=''; section.querySelector('.cheap-expansion').value=''; section.querySelector('.cheap-finish').value=''; section.querySelector('.cheap-title').value=''; section.querySelector('.cheap-mobile-max').value=''; section.querySelector('.cheap-mobile-language').value=''; section.querySelector('.cheap-mobile-expansion').value=''; section.querySelector('.cheap-mobile-finish').value=''; section.querySelector('.cheap-mobile-title').value=''; draw(); });
  section.querySelector('.mobile-clear').addEventListener('click', () => section.querySelector('.clear-filters').click());
  section.querySelector('.mobile-filter-toggle').addEventListener('click', e => { const panel=section.querySelector('.mobile-filter-panel'); const open=panel.hidden; panel.hidden=!open; e.currentTarget.setAttribute('aria-expanded', String(open)); });
  section.querySelector('.mobile-toolbar select').addEventListener('change', e => { state.sort = e.target.value === 'input' ? null : e.target.value; state.direction = state.sort?.endsWith('-desc') ? 'desc' : 'asc'; draw(); });
  section.querySelectorAll('.cheapest-table th[data-sort]').forEach(th => th.addEventListener('click', () => { const key=th.dataset.sort; if (state.sort?.startsWith(key)) state.sort = `${key}-${state.sort.endsWith('-asc') ? 'desc' : 'asc'}`; else state.sort=`${key}-asc`; draw(); }));
  draw();
}

function renderIndividuals(results, eurJpyRate) {
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
    else renderTable(panel, r.rows, `card-${index}`, eurJpyRate);

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

function render(results, output, eurJpyRate) {
  resultsEl.classList.remove('hidden');
  resultsEl.innerHTML = '';
  if (output === 'cheapest' || output === 'both') renderCheapest(results, eurJpyRate);
  if (output === 'individual' || output === 'both') renderIndividuals(results, eurJpyRate);
  requestAnimationFrame(() => viewMode === 'desktop' ? fitResultSections() : setViewMode('mobile'));
}

function fitResultSections() {
  if (viewMode === 'mobile') return;
  const sections = [...resultsEl.querySelectorAll('.card-result')];
  if (!sections.length) return;
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
  if (cards.length > 110) { statusEl.textContent = 'Maximum 110 cards per job.'; return; }

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
      render(job.results, job.output, job.eur_jpy_rate);
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
viewToggleEl.addEventListener('click', () => setViewMode(viewMode === 'mobile' ? 'desktop' : 'mobile'));
setViewMode(isMobileDevice() ? 'mobile' : 'desktop');


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

document.addEventListener('mouseover', event => {
  if (viewMode !== 'desktop') return;
  const button = event.target.closest('.preview-button');
  if (button) showPreview(button);
});
document.addEventListener('mouseout', event => {
  if (viewMode !== 'desktop') return;
  const button = event.target.closest('.preview-button');
  if (!button || button.contains(event.relatedTarget)) return;
  previewHideTimer = setTimeout(hidePreview, 80);
});

document.addEventListener('click', event => {
  const button = event.target.closest('.preview-button');
  if (button && viewMode === 'mobile') {
    event.preventDefault();
    if (previewOverlay && !previewOverlay.hidden) {
      hidePreview();
    } else {
      showPreview(button);
    }
    return;
  }
  if (viewMode === 'mobile' && previewOverlay && !previewOverlay.hidden) {
    hidePreview();
  }
});

document.addEventListener('focusin', event => {
  const button = event.target.closest('.preview-button');
  if (button) showPreview(button);
});
document.addEventListener('focusout', event => {
  if (viewMode === 'desktop' && event.target.closest('.preview-button')) {
    previewHideTimer = setTimeout(hidePreview, 80);
  }
});
window.addEventListener('scroll', hidePreview, true);
window.addEventListener('resize', hidePreview);

window.addEventListener('resize', () => { if (!resultsEl.classList.contains('hidden')) fitResultSections(); });

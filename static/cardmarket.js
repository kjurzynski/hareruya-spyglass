const queryEl = document.getElementById('cardmarketQuery');
const expansionEl = document.getElementById('cardmarketExpansion');
const exactEl = document.getElementById('cardmarketExact');
const searchEl = document.getElementById('cardmarketSearch');
const bodyEl = document.getElementById('cardmarketTableBody');
const statusEl = document.getElementById('cardmarketTableStatus');
const pageStatusEl = document.getElementById('cardmarketPageStatus');
const freshnessEl = document.getElementById('cardmarketFreshness');
const prevEl = document.getElementById('cardmarketPrev');
const nextEl = document.getElementById('cardmarketNext');

let page = 1;
const pageSize = 100;
let total = 0;
let lastUpdatedAt = null;
let lastState = null;
let freshnessTimer = null;
let hasSearched = false;

const CARDMARKET_SESSION_KEY = 'hareruyaSpyglass.cardmarket.v1';

function saveCardmarketSession(rows) {
  try {
    const payload = {
      query: queryEl.value,
      expansion: expansionEl.value,
      exact: exactEl.checked,
      page,
      total,
      rows,
      lastUpdatedAt,
      hasSearched,
    };
    sessionStorage.setItem(CARDMARKET_SESSION_KEY, JSON.stringify(payload));
  } catch (_) {
    // Ignore storage quota/privacy errors.
  }
}

function restoreCardmarketSession() {
  try {
    const raw = sessionStorage.getItem(CARDMARKET_SESSION_KEY);
    if (!raw) return false;
    const saved = JSON.parse(raw);
    if (!saved || !saved.hasSearched || !Array.isArray(saved.rows)) return false;

    queryEl.value = typeof saved.query === 'string' ? saved.query : '';
    expansionEl.value = typeof saved.expansion === 'string' ? saved.expansion : '';
    exactEl.checked = Boolean(saved.exact);
    page = Number.isInteger(saved.page) && saved.page > 0 ? saved.page : 1;
    total = Number.isFinite(Number(saved.total)) ? Number(saved.total) : saved.rows.length;
    lastUpdatedAt = saved.lastUpdatedAt || null;
    hasSearched = true;

    renderCardmarketRows(saved.rows);
    const pageCount = Math.max(1, Math.ceil(total / pageSize));
    statusEl.textContent = `Local dataset • ${total.toLocaleString()} matching rows`;
    pageStatusEl.textContent = `Page ${page} of ${pageCount}`;
    prevEl.disabled = page <= 1;
    nextEl.disabled = page >= pageCount;
    return true;
  } catch (_) {
    return false;
  }
}

function renderCardmarketRows(rows) {
  bodyEl.innerHTML = rows.length
    ? rows.map(row => `<tr><td>${escapeHtml(row.card_name)}</td><td>${escapeHtml(row.expansion)}</td><td>${escapeHtml(row.expansion_name || 'Not found')}</td><td>${variantHtml(row.nonfoil)}</td><td>${variantHtml(row.foil)}</td><td>${cardmarketLinkHtml(row)}</td>${cardmarketMobileMarkup(row)}</tr>`).join('')
    : '<tr><td colspan="6" class="empty">No local rows matched the current search.</td></tr>';
}

function escapeHtml(s) {
  return String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

function eur(value) {
  return value === null || value === undefined ? '—' : `€ ${Number(value).toFixed(2)}`;
}

function variantHtml(data) {
  if (!data) return '<span class="cm-muted">No foil data</span>';
  return `<div class="cm-variant-line"><strong>Low</strong> ${eur(data.low)}</div><div class="cm-variant-line"><strong>Trend</strong> ${eur(data.trend)}</div><div class="cm-variant-line"><strong>7d</strong> ${eur(data.avg7)}</div>`;
}

function cardmarketUrl(row) {
  if (row.cardmarket_url) return String(row.cardmarket_url);
  const productId = Number(row.product_id);
  return Number.isInteger(productId) && productId > 0
    ? `https://www.cardmarket.com/en/Magic/Products?idProduct=${encodeURIComponent(productId)}`
    : '';
}

function cardmarketLinkHtml(row) {
  const url = cardmarketUrl(row);
  if (!url) return '<span class="cm-link-button cm-link-button-disabled" aria-disabled="true">View ↗</span>';
  return `<a class="cm-link-button" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">View ↗</a>`;
}

function mobileVariantHtml(label, data) {
  if (!data) {
    return `<div class="cm-mobile-price-row cm-mobile-price-row-missing"><span class="cm-mobile-variant-label">${label}</span><span class="cm-mobile-not-found">Not found</span></div>`;
  }
  return `<div class="cm-mobile-price-row"><span class="cm-mobile-variant-label">${label}</span><span class="cm-mobile-metric">${eur(data.low)}</span><span class="cm-mobile-metric">${eur(data.trend)}</span><span class="cm-mobile-metric">${eur(data.avg7)}</span></div>`;
}

function cardmarketMobileMarkup(row) {
  const url = cardmarketUrl(row);
  const name = escapeHtml(row.card_name || 'Card');
  const expansion = escapeHtml(row.expansion || 'Unknown');
  const prices = `${mobileVariantHtml('Non-foil', row.nonfoil)}${mobileVariantHtml('Foil', row.foil)}`;
  const content = `<div class="cm-mobile-card${url ? '' : ' cm-mobile-card-unavailable'}">
      <div class="cm-mobile-info">
        <div class="cm-mobile-name">${name}</div>
        <div class="cm-mobile-expansion">${expansion}</div>
      </div>
      <div class="cm-mobile-prices">
        <div class="cm-mobile-price-head"><span></span><span>Low</span><span>Trend</span><span>7d</span></div>
        ${prices}
      </div>
      ${url ? '<span class="cm-mobile-chevron" aria-hidden="true">›</span>' : ''}
    </div>`;
  if (!url) return `<td class="cm-mobile-result" colspan="6"><div class="cm-mobile-link cm-mobile-link-unavailable">${content}</div></td>`;
  return `<td class="cm-mobile-result" colspan="6"><a class="cm-mobile-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" aria-label="View ${name} on Cardmarket">${content}</a></td>`;
}

async function loadFreshness() {
  if (!freshnessEl) return null;
  try {
    const response = await fetch('/api/cardmarket/status');
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not read local data status.');
    if (data.state === 'updating') {
      freshnessEl.textContent = data.progress > 0
        ? `Updating local data… ${Math.round(data.progress)}%`
        : 'Updating local data…';
    } else if (data.state === 'error') {
      freshnessEl.textContent = data.message || 'The latest Cardmarket update failed.';
    } else if (data.updated_at) {
      const updated = new Date(data.updated_at);
      const timestamp = Number.isNaN(updated.getTime()) ? data.updated_at : updated.toLocaleString();
      freshnessEl.textContent = `Last updated ${timestamp}`;
    } else {
      freshnessEl.textContent = data.message || 'Waiting for the first local dataset…';
    }
    return data;
  } catch (_) {
    freshnessEl.textContent = '';
    return null;
  }
}


async function load() {
  if (!hasSearched) return;
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (queryEl.value.trim()) params.set('q', queryEl.value.trim());
  if (expansionEl.value.trim()) params.set('expansion', expansionEl.value.trim());
  if (exactEl.checked) params.set('exact', 'true');
  statusEl.textContent = 'Reading local Cardmarket data…';
  searchEl.disabled = true;
  try {
    const response = await fetch(`/api/cardmarket/table?${params}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not load local Cardmarket data.');
    total = Number(data.total || 0);
    renderCardmarketRows(data.rows);
    saveCardmarketSession(data.rows);
    statusEl.textContent = `Local dataset • ${total.toLocaleString()} matching rows`;
    const pageCount = Math.max(1, Math.ceil(total / pageSize));
    pageStatusEl.textContent = `Page ${page} of ${pageCount}`;
    prevEl.disabled = page <= 1;
    nextEl.disabled = page >= pageCount;
  } catch (error) {
    bodyEl.innerHTML = `<tr><td colspan="6" class="error">${escapeHtml(error.message)}</td></tr>`;
    statusEl.textContent = 'Unable to read local Cardmarket data.';
    pageStatusEl.textContent = '';
    prevEl.disabled = true;
    nextEl.disabled = true;
  } finally {
    searchEl.disabled = false;
  }
}

searchEl.addEventListener('click', () => { page = 1; hasSearched = true; load(); });
queryEl.addEventListener('keydown', event => { if (event.key === 'Enter') { page = 1; load(); } });
exactEl.addEventListener('change', () => { page = 1; if (hasSearched) load(); });
expansionEl.addEventListener('keydown', event => { if (event.key === 'Enter') { page = 1; load(); } });
prevEl.addEventListener('click', () => { if (page > 1) { page -= 1; load(); } });
nextEl.addEventListener('click', () => { page += 1; load(); });

async function watchFreshness() {
  const data = await loadFreshness();
  if (data?.state === 'ready' && data.updated_at) {
    const readyTransition = lastState !== null && lastState !== 'ready';
    const snapshotChanged = lastUpdatedAt !== null && data.updated_at !== lastUpdatedAt;
    if (hasSearched && (readyTransition || snapshotChanged)) await load();
    lastUpdatedAt = data.updated_at;
  }
  if (data?.state) lastState = data.state;
  freshnessTimer = setTimeout(watchFreshness, 5000);
}

restoreCardmarketSession();
watchFreshness();

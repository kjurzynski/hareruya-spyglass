const queryEl = document.getElementById('cardmarketQuery');
const suggestionsEl = document.getElementById('cardmarketSuggestions');
const expansionEl = document.getElementById('cardmarketExpansion');
const exactEl = document.getElementById('cardmarketExact');
const searchEl = document.getElementById('cardmarketSearch');
const bodyEl = document.getElementById('cardmarketTableBody');
const statusEl = document.getElementById('cardmarketTableStatus');
const pageStatusEl = document.getElementById('cardmarketPageStatus');
const freshnessEl = document.getElementById('cardmarketFreshness');
const prevEl = document.getElementById('cardmarketPrev');
const nextEl = document.getElementById('cardmarketNext');
const mobileLoadMoreEl = document.getElementById('cardmarketMobileLoadMore');
const tableWrapEl = document.querySelector('.cardmarket-page .table-wrap');
const gridEl = document.getElementById('cardmarketGrid');
const tableViewEl = document.getElementById('cardmarketTableView');
const gridViewEl = document.getElementById('cardmarketGridView');

let page = 1;
const desktopPageSize = 100;
const mobilePageSize = 20;
let total = 0;
let loadedRows = [];
let lastUpdatedAt = null;
let lastState = null;
let freshnessTimer = null;
let hasSearched = false;
let mobileLoading = false;
let mobileLoadObserver = null;
let desktopView = 'grid';
let suggestionTimer = null;
let suggestionRequestId = 0;
let scryfallInfoObserver = null;
let scryfallInfoCache = new Map();
let scryfallInfoPromises = new Map();

const CARDMARKET_SESSION_KEY = 'hareruyaSpyglass.cardmarket.v1';

function isRenderableCardmarketRow(row) {
  return !/art series:/i.test(String(row?.card_name || ''));
}

function hideCardmarketSuggestions() {
  if (!suggestionsEl) return;
  suggestionsEl.hidden = true;
  suggestionsEl.innerHTML = '';
  queryEl?.setAttribute('aria-expanded', 'false');
}

function renderCardmarketSuggestions(suggestions) {
  if (!suggestionsEl) return;
  suggestionsEl.innerHTML = '';
  if (!suggestions.length) {
    hideCardmarketSuggestions();
    return;
  }
  suggestions.forEach((name, index) => {
    const option = document.createElement('button');
    option.type = 'button';
    option.className = 'cardmarket-suggestion';
    option.role = 'option';
    option.dataset.value = name;
    option.id = `cardmarket-suggestion-${index}`;
    option.textContent = name;
    option.addEventListener('mousedown', event => event.preventDefault());
    option.addEventListener('click', () => {
      queryEl.value = name;
      hideCardmarketSuggestions();
      resetMobileSearch();
      hasSearched = true;
      load();
    });
    suggestionsEl.appendChild(option);
  });
  suggestionsEl.hidden = false;
  queryEl?.setAttribute('aria-expanded', 'true');
}

function scheduleCardmarketSuggestions() {
  if (!suggestionsEl || !queryEl) return;
  if (suggestionTimer) clearTimeout(suggestionTimer);
  const query = queryEl.value.trim();
  const requestId = ++suggestionRequestId;
  if (query.length < 4) {
    hideCardmarketSuggestions();
    return;
  }
  suggestionTimer = setTimeout(async () => {
    if (requestId !== suggestionRequestId || query !== queryEl.value.trim()) return;
    suggestionsEl.innerHTML = '<div class="cardmarket-suggestion-status">Searching…</div>';
    suggestionsEl.hidden = false;
    queryEl.setAttribute('aria-expanded', 'true');
    try {
      const params = new URLSearchParams({ q: query, limit: '8' });
      const response = await fetch(`/api/cardmarket/suggestions?${params}`, { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not load suggestions.');
      if (requestId !== suggestionRequestId || query !== queryEl.value.trim()) return;
      renderCardmarketSuggestions(Array.isArray(data.suggestions) ? data.suggestions : []);
    } catch (_) {
      if (requestId === suggestionRequestId) hideCardmarketSuggestions();
    }
  }, 180);
}

function saveCardmarketSession(rows) {
  try {
    const payload = {
      query: queryEl.value,
      expansion: expansionEl.value,
      exact: exactEl.checked,
      page,
      total,
      rows,
      loadedRows,
      lastUpdatedAt,
      hasSearched,
      desktopView,
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

    const savedRows = saved.rows.filter(isRenderableCardmarketRow);

    queryEl.value = typeof saved.query === 'string' ? saved.query : '';
    expansionEl.value = typeof saved.expansion === 'string' ? saved.expansion : '';
    exactEl.checked = Boolean(saved.exact);
    page = Number.isInteger(saved.page) && saved.page > 0 ? saved.page : 1;
    total = Number.isFinite(Number(saved.total)) ? Number(saved.total) : saved.rows.length;
    loadedRows = Array.isArray(saved.loadedRows) && saved.loadedRows.length
      ? saved.loadedRows.filter(isRenderableCardmarketRow)
      : savedRows;
    lastUpdatedAt = saved.lastUpdatedAt || null;
    hasSearched = true;
    desktopView = saved.desktopView === 'grid' ? 'grid' : 'table';

    renderCardmarketRows(isMobileViewport() ? loadedRows : savedRows);
    applyDesktopView();
    if (!isMobileViewport()) {
      const pageCount = Math.max(1, Math.ceil(total / desktopPageSize));
      pageStatusEl.textContent = `Page ${page} of ${pageCount}`;
      prevEl.disabled = page <= 1;
      nextEl.disabled = page >= pageCount;
    }
    statusEl.textContent = `Local dataset • ${total.toLocaleString()} matching rows`;
    if (isMobileViewport()) setupMobileInfiniteScroll();
    return true;
  } catch (_) {
    return false;
  }
}

function cardmarketProductId(row) {
  const productId = Number(row?.product_id);
  return Number.isInteger(productId) && productId > 0 ? productId : null;
}

function promoMarkup(row, className = 'cm-promo-types') {
  const productId = cardmarketProductId(row);
  if (productId === null) return '';
  return `<div class="${className}" data-scryfall-promo-product-id="${productId}" hidden></div>`;
}

async function getCardmarketScryfallInfo(productId) {
  const normalizedId = Number(productId);
  if (!Number.isInteger(normalizedId) || normalizedId <= 0) return null;
  if (scryfallInfoCache.has(normalizedId)) return scryfallInfoCache.get(normalizedId);
  if (scryfallInfoPromises.has(normalizedId)) return scryfallInfoPromises.get(normalizedId);

  const promise = fetch(`/api/cardmarket/scryfall/${encodeURIComponent(normalizedId)}`, { cache: 'force-cache' })
    .then(async response => {
      if (response.status === 404) {
        const empty = { image_url: null, promo_types: [], promo_type_labels: [] };
        scryfallInfoCache.set(normalizedId, empty);
        return empty;
      }
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not load Scryfall data.');
      const info = {
        image_url: typeof data.image_url === 'string' ? data.image_url : null,
        promo_types: Array.isArray(data.promo_types) ? data.promo_types : [],
        promo_type_labels: Array.isArray(data.promo_type_labels) ? data.promo_type_labels : [],
      };
      scryfallInfoCache.set(normalizedId, info);
      return info;
    })
    .finally(() => scryfallInfoPromises.delete(normalizedId));
  scryfallInfoPromises.set(normalizedId, promise);
  return promise;
}

function applyScryfallPromoTypes(productId, labels) {
  const selector = `[data-scryfall-promo-product-id="${productId}"]`;
  document.querySelectorAll(selector).forEach(target => {
    if (labels.length) {
      target.textContent = labels.join(', ');
      target.hidden = false;
    } else {
      target.hidden = true;
      target.textContent = '';
    }
  });
}

function markCardmarketImageMissing(image) {
  image.hidden = true;
  image.removeAttribute('src');
  image.classList.add('cm-mobile-image-missing');
  const placeholder = image.parentElement?.querySelector('.cm-image-placeholder');
  if (placeholder) {
    placeholder.hidden = false;
    placeholder.setAttribute('aria-hidden', 'false');
  }
}

function applyScryfallImage(productId, imageUrl) {
  const selector = `img[data-scryfall-product-id="${productId}"]`;
  document.querySelectorAll(selector).forEach(image => {
    if (!imageUrl) {
      markCardmarketImageMissing(image);
      return;
    }
    image.addEventListener('error', () => markCardmarketImageMissing(image), { once: true });
    image.src = imageUrl;
    image.removeAttribute('data-scryfall-product-id');
  });
}

function prepareCardmarketScryfall() {
  const targets = document.querySelectorAll('.cardmarket-page [data-scryfall-product-id], .cardmarket-page [data-scryfall-promo-product-id]');
  if (!targets.length) return;
  if (scryfallInfoObserver) scryfallInfoObserver.disconnect();

  const loadForTarget = target => {
    const productId = target.dataset.scryfallProductId || target.dataset.scryfallPromoProductId;
    if (!productId || target.dataset.scryfallLoading === 'true') return;
    target.dataset.scryfallLoading = 'true';
    getCardmarketScryfallInfo(productId)
      .then(info => {
        const labels = info?.promo_type_labels || [];
        applyScryfallPromoTypes(Number(productId), labels);
        applyScryfallImage(Number(productId), info?.image_url || null);
      })
      .catch(() => {
        applyScryfallPromoTypes(Number(productId), []);
        applyScryfallImage(Number(productId), null);
      });
  };

  if ('IntersectionObserver' in window) {
    scryfallInfoObserver = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        loadForTarget(entry.target);
        scryfallInfoObserver.unobserve(entry.target);
      }
    }, { rootMargin: '200px 0px' });
    targets.forEach(target => scryfallInfoObserver.observe(target));
  } else {
    targets.forEach(loadForTarget);
  }
}

function isMobileViewport() {
  return window.matchMedia('(max-width:700px)').matches;
}

function rowMarkup(row) {
  const name = escapeHtml(row.card_name);
  return `<tr><td><div class="cm-table-card-name">${name}</div>${promoMarkup(row, 'cm-table-promo-types')}</td><td>${escapeHtml(row.expansion)}</td><td>${escapeHtml(row.expansion_name || 'Not found')}</td><td>${variantHtml(row.nonfoil, true)}</td><td>${variantHtml(row.foil)}</td><td>${cardmarketActionsHtml(row)}</td>${cardmarketMobileMarkup(row)}</tr>`;
}

function desktopGridMarkup(row) {
  const url = cardmarketUrl(row);
  const name = escapeHtml(row.card_name || 'Card');
  const expansion = escapeHtml(row.expansion || 'Unknown');
  const productId = cardmarketProductId(row);
  const image = productId !== null
    ? `<div class="cm-grid-image-frame"><img class="cm-grid-image" data-scryfall-product-id="${productId}" alt="${name}" loading="lazy" decoding="async"><div class="cm-image-placeholder cm-grid-image-placeholder" hidden aria-hidden="true">Scryfall was unable to fetch image</div></div>`
    : '<div class="cm-grid-image-frame"><div class="cm-image-placeholder cm-grid-image-placeholder" aria-hidden="true">Scryfall was unable to fetch image</div></div>';
  const title = `<div class="cm-grid-title" title="${name}"><div class="cm-grid-title-main">${name} <span class="cm-grid-expansion">${expansion}</span></div>${promoMarkup(row)}</div>`;
  const prices = `<div class="cm-grid-prices"><div class="cm-grid-price-head"><span></span><span>Low</span><span>Trend</span><span>7d</span></div>${mobileVariantHtml('Non-foil', row.nonfoil, true)}${mobileVariantHtml('Foil', row.foil)}</div>`;
  const content = `<article class="cm-grid-card${url ? '' : ' cm-grid-card-unavailable'}">${title}${image}${prices}</article>`;
  return url
    ? `<a class="cm-grid-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" aria-label="View ${name} on Cardmarket">${content}</a>`
    : `<div class="cm-grid-link cm-grid-link-unavailable">${content}</div>`;
}

function renderCardmarketRows(rows, append = false) {
  if (append) {
    bodyEl.insertAdjacentHTML('beforeend', rows.map(rowMarkup).join(''));
    if (gridEl && desktopView === 'grid' && !isMobileViewport()) {
      gridEl.insertAdjacentHTML('beforeend', rows.map(desktopGridMarkup).join(''));
    }
  } else {
    bodyEl.innerHTML = rows.length
      ? rows.map(rowMarkup).join('')
      : '<tr><td colspan="6" class="empty">No local rows matched the current search.</td></tr>';
    if (gridEl) {
      gridEl.innerHTML = rows.length
        ? rows.map(desktopGridMarkup).join('')
        : '<div class="cm-grid-empty">No local rows matched the current search.</div>';
    }
  }
  prepareCardmarketScryfall();
}

function applyDesktopView() {
  const mobile = isMobileViewport();
  const useGrid = !mobile && desktopView === 'grid';
  if (tableWrapEl) tableWrapEl.hidden = useGrid;
  if (gridEl) gridEl.hidden = !useGrid;
  if (tableViewEl) {
    tableViewEl.classList.toggle('active', !useGrid);
    tableViewEl.setAttribute('aria-pressed', String(!useGrid));
  }
  if (gridViewEl) {
    gridViewEl.classList.toggle('active', useGrid);
    gridViewEl.setAttribute('aria-pressed', String(useGrid));
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

function eur(value) {
  return value === null || value === undefined ? '—' : `€ ${Number(value).toFixed(2)}`;
}

function isMissingNonfoilPriceData(data) {
  if (!data || data.low === null || data.low === undefined) return false;
  const isMissingMetric = value => value === null || value === undefined || Number(value) === 0;
  return isMissingMetric(data.trend) && isMissingMetric(data.avg7);
}

function variantHtml(data, isNonfoil = false) {
  if (isNonfoil && isMissingNonfoilPriceData(data)) return '<span class="cm-muted">Not found</span>';
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

function cardmarketPreviewHtml(row) {
  const productId = cardmarketProductId(row);
  const title = escapeHtml(row.card_name || 'Card');
  if (productId === null) return '<span class="preview-button preview-button-disabled" aria-disabled="true">Preview</span>';
  return `<span class="preview-button cm-preview-button" tabindex="0" data-product-id="${productId}" data-image-title="${title}" aria-label="Preview card image">Preview</span>`;
}

function cardmarketActionsHtml(row) {
  return `<div class="cm-cardmarket-actions">${cardmarketLinkHtml(row)}${cardmarketPreviewHtml(row)}</div>`;
}

function mobileVariantHtml(label, data, isNonfoil = false) {
  if (!data || (isNonfoil && isMissingNonfoilPriceData(data))) {
    return `<div class="cm-mobile-price-row cm-mobile-price-row-missing"><span class="cm-mobile-variant-label">${label}</span><span class="cm-mobile-not-found">Not found</span></div>`;
  }
  return `<div class="cm-mobile-price-row"><span class="cm-mobile-variant-label">${label}</span><span class="cm-mobile-metric">${eur(data.low)}</span><span class="cm-mobile-metric">${eur(data.trend)}</span><span class="cm-mobile-metric">${eur(data.avg7)}</span></div>`;
}

function cardmarketMobileMarkup(row) {
  const url = cardmarketUrl(row);
  const productId = cardmarketProductId(row);
  const name = escapeHtml(row.card_name || 'Card');
  const expansion = escapeHtml(row.expansion || 'Unknown');
  const prices = `${mobileVariantHtml('Non-foil', row.nonfoil, true)}${mobileVariantHtml('Foil', row.foil)}`;
  const image = productId !== null
    ? `<div class="cm-mobile-image-frame"><img class="cm-mobile-image" data-scryfall-product-id="${productId}" alt="${name}" loading="lazy" decoding="async"><div class="cm-image-placeholder cm-mobile-image-placeholder" hidden aria-hidden="true">Scryfall was unable to fetch image</div></div>`
    : '<div class="cm-mobile-image-frame"><div class="cm-image-placeholder cm-mobile-image-placeholder" aria-hidden="true">Scryfall was unable to fetch image</div></div>'; 
  const content = `<div class="cm-mobile-card${url ? '' : ' cm-mobile-card-unavailable'}">
      <div class="cm-mobile-image-wrap">${image}</div>
      <div class="cm-mobile-info">
        <div class="cm-mobile-title-line"><div class="cm-mobile-title-main"><span class="cm-mobile-name">${name}</span><span class="cm-mobile-expansion">${expansion}</span></div>${promoMarkup(row)}</div>
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

let cmPreviewOverlay = null;
let cmPreviewHideTimer = null;

function ensureCardmarketPreviewOverlay() {
  if (cmPreviewOverlay) return cmPreviewOverlay;
  cmPreviewOverlay = document.createElement('div');
  cmPreviewOverlay.className = 'image-preview-overlay cm-image-preview-overlay';
  cmPreviewOverlay.setAttribute('role', 'tooltip');
  cmPreviewOverlay.hidden = true;
  document.body.appendChild(cmPreviewOverlay);
  return cmPreviewOverlay;
}

function hideCardmarketPreview() {
  if (cmPreviewHideTimer) clearTimeout(cmPreviewHideTimer);
  const overlay = ensureCardmarketPreviewOverlay();
  overlay.hidden = true;
  overlay.classList.remove('foil-preview');
  overlay.innerHTML = '';
}

function positionCardmarketPreview(button) {
  const overlay = ensureCardmarketPreviewOverlay();
  const rect = button.getBoundingClientRect();
  const overlayRect = overlay.getBoundingClientRect();
  const gap = 10;
  const viewportPadding = 10;
  const left = Math.min(
    Math.max(viewportPadding, rect.right + gap),
    window.innerWidth - overlayRect.width - viewportPadding,
  );
  const canPlaceAbove = rect.top >= overlayRect.height + gap + viewportPadding;
  const top = canPlaceAbove
    ? rect.top - overlayRect.height - gap
    : Math.min(window.innerHeight - overlayRect.height - viewportPadding, rect.bottom + gap);
  overlay.style.left = `${Math.max(viewportPadding, left)}px`;
  overlay.style.top = `${Math.max(viewportPadding, top)}px`;
}

function showCardmarketPreview(button) {
  const productId = Number(button?.dataset.productId);
  if (!Number.isInteger(productId) || productId <= 0) return;
  if (cmPreviewHideTimer) clearTimeout(cmPreviewHideTimer);
  const overlay = ensureCardmarketPreviewOverlay();
  overlay.hidden = false;
  overlay.innerHTML = '<div class="cm-image-placeholder cm-desktop-image-placeholder">Loading…</div>';
  positionCardmarketPreview(button);

  getCardmarketScryfallInfo(productId).then(info => {
    if (overlay.hidden) return;
    overlay.innerHTML = '';
    if (!info?.image_url) {
      overlay.innerHTML = '<div class="cm-image-placeholder cm-desktop-image-placeholder">Scryfall was unable to fetch image</div>';
      positionCardmarketPreview(button);
      return;
    }

    const image = document.createElement('img');
    image.alt = button.dataset.imageTitle || 'Card image';
    image.src = info.image_url;
    image.addEventListener('load', () => positionCardmarketPreview(button), { once: true });
    image.addEventListener('error', () => {
      overlay.innerHTML = '<div class="cm-image-placeholder cm-desktop-image-placeholder">Scryfall was unable to fetch image</div>';
      positionCardmarketPreview(button);
    }, { once: true });
    overlay.appendChild(image);
    positionCardmarketPreview(button);
  }).catch(() => {
    if (overlay.hidden) return;
    overlay.innerHTML = '<div class="cm-image-placeholder cm-desktop-image-placeholder">Scryfall was unable to fetch image</div>';
    positionCardmarketPreview(button);
  });
}

document.addEventListener('mouseenter', event => {
  const button = event.target.closest('.cm-preview-button');
  if (button) showCardmarketPreview(button);
}, true);

document.addEventListener('mouseleave', event => {
  const button = event.target.closest('.cm-preview-button');
  if (!button) return;
  cmPreviewHideTimer = setTimeout(hideCardmarketPreview, 80);
}, true);

document.addEventListener('focusin', event => {
  const button = event.target.closest('.cm-preview-button');
  if (button) showCardmarketPreview(button);
});

document.addEventListener('focusout', event => {
  const button = event.target.closest('.cm-preview-button');
  if (!button) return;
  cmPreviewHideTimer = setTimeout(hideCardmarketPreview, 80);
});

window.addEventListener('scroll', hideCardmarketPreview, true);
window.addEventListener('resize', hideCardmarketPreview);
window.addEventListener('resize', () => {
  const mobile = isMobileViewport();
  applyDesktopView();
  if (!mobile && desktopView === 'grid' && gridEl && hasSearched) {
    gridEl.innerHTML = loadedRows.length ? loadedRows.map(desktopGridMarkup).join('') : '<div class="cm-grid-empty">No local rows matched the current search.</div>';
    prepareCardmarketScryfall();
  }
});

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
  const mobile = isMobileViewport();
  const currentPageSize = mobile ? mobilePageSize : desktopPageSize;
  const params = new URLSearchParams({ page: String(page), page_size: String(currentPageSize) });
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
    const visibleRows = Array.isArray(data.rows) ? data.rows.filter(isRenderableCardmarketRow) : [];
    if (mobile) {
      if (page === 1) {
        loadedRows = visibleRows;
        renderCardmarketRows(loadedRows);
      } else {
        loadedRows = loadedRows.concat(visibleRows);
        renderCardmarketRows(visibleRows, true);
      }
      saveCardmarketSession(loadedRows);
      setupMobileInfiniteScroll();
      updateMobileLoadMoreState();
    } else {
      loadedRows = data.rows;
      renderCardmarketRows(data.rows);
      applyDesktopView();
      saveCardmarketSession(data.rows);
      statusEl.textContent = `Local dataset • ${total.toLocaleString()} matching rows`;
      const pageCount = Math.max(1, Math.ceil(total / desktopPageSize));
      pageStatusEl.textContent = `Page ${page} of ${pageCount}`;
      prevEl.disabled = page <= 1;
      nextEl.disabled = page >= pageCount;
    }
    statusEl.textContent = `Local dataset • ${total.toLocaleString()} matching rows`;
  } catch (error) {
    if (mobile && page > 1) {
      statusEl.textContent = `Local dataset • ${total.toLocaleString()} matching rows`;
      setMobileLoadMessage('Could not load more results.');
    } else {
      bodyEl.innerHTML = `<tr><td colspan="6" class="error">${escapeHtml(error.message)}</td></tr>`;
      statusEl.textContent = 'Unable to read local Cardmarket data.';
    }
    if (!mobile) {
      pageStatusEl.textContent = '';
      prevEl.disabled = true;
      nextEl.disabled = true;
    }
  } finally {
    searchEl.disabled = false;
    if (mobile) mobileLoading = false;
    updateMobileLoadMoreState();
  }
}

function resetMobileSearch() {
  page = 1;
  loadedRows = [];
  if (isMobileViewport()) resetMobileInfiniteScrollState();
}

tableViewEl?.addEventListener('click', () => {
  desktopView = 'table';
  applyDesktopView();
  if (hasSearched) saveCardmarketSession(isMobileViewport() ? loadedRows : loadedRows);
});
gridViewEl?.addEventListener('click', () => {
  desktopView = 'grid';
  applyDesktopView();
  if (hasSearched) {
    const rows = isMobileViewport() ? loadedRows : loadedRows;
    if (gridEl && !isMobileViewport()) {
      gridEl.innerHTML = loadedRows.length ? loadedRows.map(desktopGridMarkup).join('') : '<div class="cm-grid-empty">No local rows matched the current search.</div>';
      prepareCardmarketScryfall();
    }
    saveCardmarketSession(rows);
  }
});

searchEl.addEventListener('click', () => { hideCardmarketSuggestions(); resetMobileSearch(); hasSearched = true; load(); });
queryEl.addEventListener('input', scheduleCardmarketSuggestions);
queryEl.addEventListener('focus', scheduleCardmarketSuggestions);
queryEl.addEventListener('blur', () => setTimeout(hideCardmarketSuggestions, 120));
queryEl.addEventListener('keydown', event => {
  if (event.key === 'Escape') { hideCardmarketSuggestions(); return; }
  if (event.key === 'Enter') { hideCardmarketSuggestions(); resetMobileSearch(); hasSearched = true; load(); }
});
exactEl.addEventListener('change', () => { resetMobileSearch(); if (hasSearched) load(); });
expansionEl.addEventListener('keydown', event => { if (event.key === 'Enter') { hideCardmarketSuggestions(); resetMobileSearch(); load(); } });
prevEl.addEventListener('click', () => { if (page > 1) { page -= 1; load(); } });
nextEl.addEventListener('click', () => { page += 1; load(); });

function setMobileLoadMessage(message) {
  if (!mobileLoadMoreEl) return;
  mobileLoadMoreEl.textContent = message;
}

function updateMobileLoadMoreState() {
  if (!mobileLoadMoreEl || !isMobileViewport()) return;
  const hasMore = page * mobilePageSize < total;
  mobileLoadMoreEl.hidden = !hasMore && !mobileLoading;
  mobileLoadMoreEl.textContent = mobileLoading ? 'Loading more…' : '';
}

function resetMobileInfiniteScrollState() {
  if (mobileLoadObserver) mobileLoadObserver.disconnect();
  mobileLoadObserver = null;
  mobileLoading = false;
  if (mobileLoadMoreEl) {
    mobileLoadMoreEl.hidden = true;
    mobileLoadMoreEl.textContent = '';
  }
}

function setupMobileInfiniteScroll() {
  if (!mobileLoadMoreEl) return;
  if (mobileLoadObserver) mobileLoadObserver.disconnect();
  mobileLoadObserver = null;
  updateMobileLoadMoreState();
  if (!isMobileViewport() || page * mobilePageSize >= total) return;
  if (!('IntersectionObserver' in window)) return;
  mobileLoadObserver = new IntersectionObserver(entries => {
    if (!entries.some(entry => entry.isIntersecting)) return;
    if (mobileLoading || page * mobilePageSize >= total || !hasSearched) return;
    mobileLoading = true;
    updateMobileLoadMoreState();
    page += 1;
    load();
  }, { rootMargin: '0px 0px 80px 0px' });
  mobileLoadObserver.observe(mobileLoadMoreEl);
}

async function watchFreshness() {
  const data = await loadFreshness();
  if (data?.state === 'ready' && data.updated_at) {
    const readyTransition = lastState !== null && lastState !== 'ready';
    const snapshotChanged = lastUpdatedAt !== null && data.updated_at !== lastUpdatedAt;
    if (hasSearched && (readyTransition || snapshotChanged)) {
      if (isMobileViewport()) resetMobileSearch();
      await load();
    }
    lastUpdatedAt = data.updated_at;
  }
  if (data?.state) lastState = data.state;
  freshnessTimer = setTimeout(watchFreshness, 5000);
}

restoreCardmarketSession();
applyDesktopView();
setupMobileInfiniteScroll();
watchFreshness();


document.addEventListener('click', event => {
  if (event.target.closest('.cardmarket-search-box')) return;
  hideCardmarketSuggestions();
});

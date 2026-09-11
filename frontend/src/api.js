/**
 * API client for Portfolio and Stock Monitor.
 * Interacts with Flask backend REST endpoints and Server-Sent Events (SSE).
 */

async function request(url, options = {}) {
  const response = await fetch(url, options);
  let payload = {};
  try {
    payload = await response.json();
  } catch (err) {
    throw new Error(`Server returned an invalid response (HTTP ${response.status}).`);
  }

  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `Request failed (HTTP ${response.status}).`);
  }
  return payload;
}

function sendJson(url, method, body) {
  return request(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function fetchData() {
  return request('/api/data');
}

export async function refreshAll() {
  return request('/api/refresh', { method: 'POST' });
}

export async function addTicker(portfolio, symbol) {
  return sendJson('/api/tickers', 'POST', { portfolio, symbol });
}

export async function removeTicker(portfolio, symbol) {
  return sendJson('/api/tickers', 'DELETE', { portfolio, symbol });
}

export async function fetchSchedule() {
  return request('/api/schedule');
}

export async function saveSchedule(run_times) {
  return sendJson('/api/schedule', 'POST', { run_times });
}

export async function fetchStatus() {
  return request('/api/status');
}

export async function fetchStockInfo(symbol) {
  const enc = encodeURIComponent(symbol.trim());
  return request(`/api/stock-info?symbol=${enc}`);
}

export async function fetchStockStatuses() {
  return request('/api/stock-status');
}

export async function addStockStatus(data) {
  return sendJson('/api/stock-status', 'POST', data);
}

export async function updateStockStatus(itemId, data) {
  return sendJson(`/api/stock-status/${encodeURIComponent(itemId)}`, 'PUT', data);
}

export async function deleteStockStatus(itemId) {
  return request(`/api/stock-status/${encodeURIComponent(itemId)}`, {
    method: 'DELETE',
  });
}

export async function fetchBatchQuotes(symbols) {
  return sendJson('/api/stock-quotes', 'POST', { symbols });
}

/**
 * Connects to the SSE stream on /api/stream.
 * Automatically falls back to periodic polling if SSE is unavailable or permanently closed.
 */
export function connectStatusStream({
  knownVersion = 0,
  onUpdate,
  onStateChange,
  pollSeconds = 5,
}) {
  let isPolling = false;
  let pollTimer = null;
  let eventSource = null;
  let currentVersion = knownVersion;

  function startPolling() {
    if (isPolling) return;
    isPolling = true;
    if (onStateChange) onStateChange('polling');

    pollTimer = setInterval(async () => {
      try {
        const status = await fetchStatus();
        if (status && status.version !== currentVersion) {
          currentVersion = status.version;
          if (onUpdate) onUpdate(status);
        }
      } catch (err) {
        // Transient network error, retry next tick
      }
    }, Math.max(2, pollSeconds) * 1000);
  }

  function startSSE() {
    if (typeof window.EventSource === 'undefined') {
      startPolling();
      return;
    }

    try {
      eventSource = new EventSource(`/api/stream?version=${currentVersion}`);

      eventSource.addEventListener('open', () => {
        if (!isPolling && onStateChange) onStateChange('live');
      });

      eventSource.addEventListener('update', (event) => {
        try {
          const status = JSON.parse(event.data);
          if (status && status.version !== currentVersion) {
            currentVersion = status.version;
            if (onUpdate) onUpdate(status);
          }
        } catch (e) {
          if (onUpdate) onUpdate({ version: currentVersion + 1 });
        }
      });

      eventSource.addEventListener('error', () => {
        if (eventSource.readyState === EventSource.CLOSED && !isPolling) {
          startPolling();
        }
      });
    } catch (e) {
      startPolling();
    }
  }

  startSSE();

  // Return cleanup function
  return () => {
    if (eventSource) {
      eventSource.close();
    }
    if (pollTimer) {
      clearInterval(pollTimer);
    }
  };
}

export async function fetchScreenerData(date = '') {
  const q = date ? `?date=${encodeURIComponent(date)}` : '';
  return request(`/api/screener/data${q}`);
}

export async function runScreenerFetch({ nonce, date = '', search = '', per_page = 3489 }) {
  return sendJson('/api/screener/fetch', 'POST', {
    nonce,
    date,
    search,
    per_page,
  });
}

export async function detectScreenerNonce() {
  return request('/api/screener/detect-nonce');
}

export async function syncScreenerHistory(maxDays = 11, targetDates = null) {
  return sendJson('/api/screener/sync-history', 'POST', {
    max_days: maxDays,
    target_dates: targetDates,
  });
}

export async function fetchMultiDayAnalysis(maxDays = 11) {
  return request(`/api/screener/multi-day-analysis?max_days=${maxDays}`);
}

// ---------------------------------------------------------------------------
// Portfolio Tracker API
// ---------------------------------------------------------------------------

export async function fetchPortfolioTracker(portfolio) {
  return request(`/api/portfolio-tracker/${encodeURIComponent(portfolio)}`);
}

export async function addPortfolioHolding(data) {
  return sendJson('/api/portfolio-tracker/holding', 'POST', data);
}

export async function addPortfolioLot(data) {
  return sendJson('/api/portfolio-tracker/lot', 'POST', data);
}

export async function deletePortfolioHolding(holdingId) {
  return request(`/api/portfolio-tracker/holding/${holdingId}`, { method: 'DELETE' });
}

export async function deletePortfolioLot(lotId) {
  return request(`/api/portfolio-tracker/lot/${lotId}`, { method: 'DELETE' });
}

export async function updatePortfolioLot(lotId, data) {
  return sendJson(`/api/portfolio-tracker/lot/${lotId}`, 'PUT', data);
}

export async function updatePortfolioHolding(holdingId, data) {
  return sendJson(`/api/portfolio-tracker/holding/${holdingId}`, 'PUT', data);
}

export async function updatePortfolioSold(holdingId, data) {
  return sendJson(`/api/portfolio-tracker/sold/${holdingId}`, 'PUT', data);
}

export async function sellPortfolioHolding(data) {
  return sendJson('/api/portfolio-tracker/sell', 'POST', data);
}

export async function swapPortfolioHoldings(data) {
  return sendJson('/api/portfolio-tracker/swap', 'POST', data);
}

export async function updatePortfolioNotes(holdingId, notes) {
  return sendJson(`/api/portfolio-tracker/notes/${holdingId}`, 'PUT', notes);
}

export async function fetchPortfolioMistakes() {
  return request('/api/portfolio-tracker/mistakes');
}

export async function addPortfolioDividend(data) {
  return sendJson('/api/portfolio-tracker/dividend', 'POST', data);
}

export async function deletePortfolioDividend(dividendId) {
  return request(`/api/portfolio-tracker/dividend/${dividendId}`, { method: 'DELETE' });
}

export async function fetchPortfolioSummary() {
  return request('/api/portfolio-tracker/summary');
}

export async function updatePortfolioSummary(key, value, label) {
  return sendJson('/api/portfolio-tracker/summary', 'PUT', { key, value, label });
}

export async function importPortfolioWorkbook(file = null, replace = false) {
  const url = `/api/portfolio-tracker/import?replace=${replace ? 'true' : 'false'}`;
  if (file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(url, { method: 'POST', body: formData });
    return res.json();
  }
  return request(url, { method: 'POST' });
}

export async function lookupTicker(symbol) {
  return request(`/api/portfolio-tracker/lookup-ticker?symbol=${encodeURIComponent(symbol)}`);
}

export function getExportUrl(portfolio = '', format = 'xlsx') {
  const p = portfolio ? `portfolio=${encodeURIComponent(portfolio)}&` : '';
  return `/api/portfolio-tracker/export?${p}format=${encodeURIComponent(format)}`;
}

// ---------------------------------------------------------------------------
// Swing Tracker API
// ---------------------------------------------------------------------------

export async function fetchSwingTracker() {
  return request('/api/swing-tracker');
}

export async function addSwingTrade(data) {
  return sendJson('/api/swing-tracker', 'POST', data);
}

export async function updateSwingTrade(id, data) {
  return sendJson(`/api/swing-tracker/${encodeURIComponent(id)}`, 'PUT', data);
}

export async function deleteSwingTrade(id) {
  return request(`/api/swing-tracker/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function refreshSwingTradePrice(id) {
  return sendJson(`/api/swing-tracker/${encodeURIComponent(id)}/refresh-price`, 'POST', {});
}

export async function refreshAllSwingTradePrices() {
  return sendJson('/api/swing-tracker/refresh-all', 'POST', {});
}

export async function fetchSwingSources() {
  return request('/api/swing-tracker/sources');
}

export async function addSwingSource(name) {
  return sendJson('/api/swing-tracker/sources', 'POST', { name });
}

export async function lookupSwingTicker(symbol) {
  return request(`/api/swing-tracker/lookup-ticker?symbol=${encodeURIComponent(symbol)}`);
}



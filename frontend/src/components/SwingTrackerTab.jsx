import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  Search,
  X,
  Plus,
  RefreshCw,
  Edit2,
  Trash2,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  TrendingUp,
  CheckCircle2,
} from 'lucide-react';
import * as api from '../api';
import { formatDate } from '../utils/date';
import { calculateDistancePct, isInsideBuyZone, parseRangeOrNumber } from '../utils/swingCalculations';
import SwingTradeModal from './SwingTradeModal';

function tradingViewUrl(symbol) {
  const clean = (symbol || '').replace('^', '');
  const exchange = clean.endsWith('.BO') ? 'BSE' : 'NSE';
  const base = clean.replace(/\.(NS|BO)$/, '');
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(`${exchange}:${base}`)}`;
}

// Thesis cell that preserves multi-line formatting and whitespace
function ThesisCell({ text }) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!text || !text.trim()) {
    return <span className="text-muted">—</span>;
  }

  const trimmed = text.trim();
  const lines = trimmed.split('\n');
  const isLong = trimmed.length > 80 || lines.length > 2;

  if (!isLong) {
    return (
      <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: '0.85rem' }}>
        {trimmed}
      </div>
    );
  }

  return (
    <div style={{ fontSize: '0.85rem' }}>
      <div
        style={{
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          maxHeight: isExpanded ? 'none' : '3.6em',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {trimmed}
      </div>
      <button
        type="button"
        className="btn btn-link btn-sm p-0 mt-1 d-inline-flex align-items-center gap-1 text-decoration-none text-primary"
        style={{ fontSize: '0.75rem' }}
        onClick={() => setIsExpanded((prev) => !prev)}
      >
        {isExpanded ? (
          <>
            <ChevronUp size={12} />
            <span>Show less</span>
          </>
        ) : (
          <>
            <ChevronDown size={12} />
            <span>Show more</span>
          </>
        )}
      </button>
    </div>
  );
}

// Distance percentage pill with context-aware styling
function DistancePill({ currentPrice, targetVal, type = 'target' }) {
  const dist = calculateDistancePct(currentPrice, targetVal);
  if (dist === null) return null;

  if (type === 'buy_zone') {
    const inside = isInsideBuyZone(currentPrice, targetVal);
    if (inside) {
      return (
        <div className="mt-1">
          <span className="badge bg-success-subtle text-success border border-success-subtle" style={{ fontSize: '0.72rem' }}>
            In Buy Zone
          </span>
        </div>
      );
    }
    return (
      <div className="mt-1">
        <span
          className={`badge ${dist <= 0 ? 'bg-primary-subtle text-primary border border-primary-subtle' : 'bg-secondary-subtle text-secondary'}`}
          style={{ fontSize: '0.72rem' }}
          title={`Distance from current price: ${dist >= 0 ? '+' : ''}${dist}%`}
        >
          {dist >= 0 ? `+${dist}%` : `${dist}%`}
        </span>
      </div>
    );
  }

  if (type === 'sl') {
    // If current price has breached SL (i.e. distance from current price to SL is positive, meaning current price is below SL)
    const isBreached = dist >= 0;
    return (
      <div className="mt-1">
        <span
          className={`badge ${isBreached ? 'bg-danger text-white' : 'bg-light text-muted border'}`}
          style={{ fontSize: '0.72rem' }}
          title={isBreached ? 'STOP LOSS BREACHED!' : `Distance to SL: ${dist}%`}
        >
          {isBreached ? `⚠️ SL Hit (${dist >= 0 ? '+' : ''}${dist}%)` : `${dist}%`}
        </span>
      </div>
    );
  }

  // Targets: green when positive
  return (
    <div className="mt-1">
      <span
        className={`badge ${dist >= 0 ? 'bg-success-subtle text-success border border-success-subtle' : 'bg-warning-subtle text-warning border border-warning-subtle'}`}
        style={{ fontSize: '0.72rem' }}
        title={`Distance to target: ${dist >= 0 ? '+' : ''}${dist}%`}
      >
        {dist >= 0 ? `+${dist}%` : `${dist}%`}
      </span>
    </div>
  );
}

export default function SwingTrackerTab({ showToast, isBusy, setIsBusy }) {
  const [trades, setTrades] = useState([]);
  const [sources, setSources] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [refreshingRowId, setRefreshingRowId] = useState(null);
  const [isRefreshingAll, setIsRefreshingAll] = useState(false);

  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditMode, setIsEditMode] = useState(false);
  const [editItem, setEditItem] = useState(null);

  const searchInputRef = useRef(null);

  // Load all swing trades and trade sources
  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.fetchSwingTracker();
      if (res && res.ok) {
        setTrades(res.trades || []);
        setSources(res.sources || []);
      }
    } catch (err) {
      console.error('Failed to load swing trades:', err);
      if (showToast) showToast(err.message || 'Failed to load swing tracker data.', true);
    } finally {
      setIsLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Global Ctrl+F shortcut to focus search input
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Filter trades live as-you-type
  const filteredTrades = useMemo(() => {
    if (!trades) return [];
    const q = searchQuery.trim().toLowerCase();
    if (!q) return trades;

    return trades.filter((t) => {
      const sym = (t.symbol || '').toLowerCase();
      const pattern = (t.pattern_break || '').toLowerCase();
      const thesisText = (t.thesis || '').toLowerCase();
      const src = (t.trade_source || '').toLowerCase();
      const dateStr = (t.date || '').toLowerCase();
      return (
        sym.includes(q) ||
        pattern.includes(q) ||
        thesisText.includes(q) ||
        src.includes(q) ||
        dateStr.includes(q)
      );
    });
  }, [trades, searchQuery]);

  // Open Add modal
  const handleOpenAdd = () => {
    setIsEditMode(false);
    setEditItem(null);
    setIsModalOpen(true);
  };

  // Open Edit modal
  const handleOpenEdit = (item) => {
    setIsEditMode(true);
    setEditItem(item);
    setIsModalOpen(true);
  };

  // Modal submit (Add or Edit)
  const handleModalSubmit = async (payload, tradeId) => {
    if (setIsBusy) setIsBusy(true);
    try {
      let res;
      if (tradeId) {
        res = await api.updateSwingTrade(tradeId, payload);
      } else {
        res = await api.addSwingTrade(payload);
      }

      if (res && res.ok) {
        if (res.trades) setTrades(res.trades);
        if (res.sources) setSources(res.sources);
        if (showToast) showToast(res.message || 'Trade saved successfully.', false);
      } else {
        await loadData();
      }
    } finally {
      if (setIsBusy) setIsBusy(false);
    }
  };

  // Delete trade
  const handleDeleteTrade = async (item) => {
    const confirmed = window.confirm(`Delete swing trade for ${item.symbol}?`);
    if (!confirmed) return;

    if (setIsBusy) setIsBusy(true);
    try {
      const res = await api.deleteSwingTrade(item.id);
      if (res && res.ok) {
        if (res.trades) setTrades(res.trades);
        if (showToast) showToast(res.message || `${item.symbol} deleted.`, false);
      } else {
        await loadData();
      }
    } catch (err) {
      if (showToast) showToast(err.message || 'Failed to delete trade.', true);
    } finally {
      if (setIsBusy) setIsBusy(false);
    }
  };

  // Manual refresh for a single row
  const handleRefreshRowPrice = async (item) => {
    setRefreshingRowId(item.id);
    try {
      const res = await api.refreshSwingTradePrice(item.id);
      if (res && res.ok) {
        if (res.trades) setTrades(res.trades);
        if (showToast) showToast(res.message || `Price updated for ${item.symbol}.`, false);
      }
    } catch (err) {
      if (showToast) showToast(err.message || `Failed to refresh ${item.symbol}.`, true);
    } finally {
      setRefreshingRowId(null);
    }
  };

  // Refresh all swing trade prices
  const handleRefreshAll = async () => {
    setIsRefreshingAll(true);
    try {
      const res = await api.refreshAllSwingTradePrices();
      if (res && res.ok) {
        if (res.trades) setTrades(res.trades);
        if (showToast) showToast(res.message || 'All swing trade prices refreshed.', false);
      }
    } catch (err) {
      if (showToast) showToast(err.message || 'Failed to refresh prices.', true);
    } finally {
      setIsRefreshingAll(false);
    }
  };

  return (
    <div className="swing-tracker-container">
      {/* Top Bar: Search, Stats, and Actions */}
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 mb-3">
        {/* Live Search Input (no separate search button) */}
        <div className="input-group input-group-sm" style={{ maxWidth: '340px' }}>
          <span className="input-group-text bg-white border-end-0 text-muted">
            <Search size={14} />
          </span>
          <input
            ref={searchInputRef}
            type="text"
            className="form-control border-start-0 ps-0"
            placeholder="Search symbol, pattern, thesis, source... (Ctrl+F)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button
              type="button"
              className="btn btn-outline-secondary border-start-0"
              onClick={() => {
                setSearchQuery('');
                searchInputRef.current?.focus();
              }}
              title="Clear search"
            >
              <X size={13} />
            </button>
          )}
        </div>

        {/* Action Buttons */}
        <div className="d-flex align-items-center gap-2">
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm d-inline-flex align-items-center gap-1"
            onClick={handleRefreshAll}
            disabled={isRefreshingAll || trades.length === 0}
            title="Refresh prices for all swing trades"
          >
            <RefreshCw size={14} className={isRefreshingAll ? 'spin-anim' : ''} />
            <span>{isRefreshingAll ? 'Refreshing...' : 'Refresh Prices'}</span>
          </button>

          <button
            type="button"
            className="btn btn-primary btn-sm d-inline-flex align-items-center gap-1 shadow-sm px-3"
            onClick={handleOpenAdd}
          >
            <Plus size={15} />
            <span>Add Swing Trade</span>
          </button>
        </div>
      </div>

      {/* Search Filter Indicator */}
      {searchQuery && (
        <div className="text-muted small mb-2">
          Filtering {filteredTrades.length} of {trades.length} trades matching &ldquo;
          <span className="fw-semibold text-dark">{searchQuery}</span>&rdquo;
        </div>
      )}

      {/* Main Table Card */}
      <div className="dashboard-card p-0 overflow-hidden shadow-sm">
        <div className="table-responsive-wrapper">
          <table className="table-stock m-0">
            <thead>
              <tr>
                <th className="col-sticky-ticker" style={{ minWidth: '150px' }}>
                  Ticker
                </th>
                <th style={{ minWidth: '105px' }}>Date</th>
                <th style={{ minWidth: '140px' }}>Current Price</th>
                <th style={{ minWidth: '120px' }}>Buy Zone</th>
                <th style={{ minWidth: '100px' }}>SL</th>
                <th style={{ minWidth: '110px' }}>Target 1</th>
                <th style={{ minWidth: '110px' }}>Target 2</th>
                <th style={{ minWidth: '140px' }}>Pattern Break</th>
                <th style={{ minWidth: '220px' }}>Thesis</th>
                <th style={{ minWidth: '130px' }}>Trade Source</th>
                <th style={{ width: '90px', textAlign: 'center' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredTrades.length === 0 ? (
                <tr>
                  <td colSpan="11" className="p-5 text-center text-muted">
                    {isLoading ? (
                      <div className="d-flex align-items-center justify-content-center gap-2">
                        <span className="spinner-border spinner-border-sm text-primary" role="status" />
                        <span>Loading swing trades...</span>
                      </div>
                    ) : searchQuery ? (
                      <div>
                        No swing trades matching &ldquo;<strong>{searchQuery}</strong>&rdquo;.
                      </div>
                    ) : (
                      <div>
                        No swing trades recorded yet. Click{' '}
                        <button
                          type="button"
                          className="btn btn-link p-0 align-baseline fw-semibold"
                          onClick={handleOpenAdd}
                        >
                          + Add Swing Trade
                        </button>{' '}
                        to add your first trade setup!
                      </div>
                    )}
                  </td>
                </tr>
              ) : (
                filteredTrades.map((item) => {
                  const tvUrl = tradingViewUrl(item.symbol);
                  const isRowRefreshing = refreshingRowId === item.id;
                  const cp = item.current_price;

                  return (
                    <tr key={item.id}>
                      {/* 1. Ticker */}
                      <td className="col-sticky-ticker">
                        <div className="col-ticker-wrap">
                          <a
                            href={tvUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="ticker-link d-inline-flex align-items-center gap-1"
                            title={`Open ${item.symbol} on TradingView`}
                          >
                            <span>{item.symbol}</span>
                            <ExternalLink size={12} className="opacity-75" />
                          </a>
                        </div>
                      </td>

                      {/* 2. Date */}
                      <td className="text-nowrap" style={{ fontSize: '0.85rem' }}>
                        {formatDate(item.date)}
                      </td>

                      {/* 3. Current Price */}
                      <td>
                        <div className="d-flex align-items-center justify-content-between gap-1">
                          <span className="col-price-val fw-semibold">
                            {cp !== null && cp !== undefined && !isNaN(Number(cp))
                              ? `₹${Number(cp).toLocaleString('en-IN', {
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 2,
                                })}`
                              : '—'}
                          </span>
                          <button
                            type="button"
                            className="btn btn-link p-0 text-muted opacity-75 hover-opacity-100"
                            onClick={() => handleRefreshRowPrice(item)}
                            disabled={isRowRefreshing}
                            title={`Refresh price for ${item.symbol}${item.current_price_updated_at ? ` (Last updated: ${item.current_price_updated_at})` : ''}`}
                          >
                            <RefreshCw
                              size={12}
                              className={isRowRefreshing ? 'spin-anim text-primary' : ''}
                            />
                          </button>
                        </div>
                      </td>

                      {/* 4. Buy Zone */}
                      <td>
                        <div>
                          <span className="fw-medium text-dark">{item.buy_zone || '—'}</span>
                          {item.buy_zone && <DistancePill currentPrice={cp} targetVal={item.buy_zone} type="buy_zone" />}
                        </div>
                      </td>

                      {/* 5. Stop Loss (SL) */}
                      <td>
                        <div>
                          <span className="fw-medium text-dark">{item.stop_loss || '—'}</span>
                          {item.stop_loss && <DistancePill currentPrice={cp} targetVal={item.stop_loss} type="sl" />}
                        </div>
                      </td>

                      {/* 6. Target 1 */}
                      <td>
                        <div>
                          <span className="fw-medium text-dark">{item.target1 || '—'}</span>
                          {item.target1 && <DistancePill currentPrice={cp} targetVal={item.target1} type="target" />}
                        </div>
                      </td>

                      {/* 7. Target 2 */}
                      <td>
                        <div>
                          <span className="fw-medium text-dark">{item.target2 || '—'}</span>
                          {item.target2 && <DistancePill currentPrice={cp} targetVal={item.target2} type="target" />}
                        </div>
                      </td>

                      {/* 8. Pattern Break */}
                      <td style={{ fontSize: '0.85rem' }}>
                        {item.pattern_break ? (
                          <span className="text-dark">{item.pattern_break}</span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>

                      {/* 9. Thesis (Formatting preserved) */}
                      <td>
                        <ThesisCell text={item.thesis} />
                      </td>

                      {/* 10. Trade Source */}
                      <td>
                        {item.trade_source ? (
                          <span className="badge bg-light text-dark border text-truncate" style={{ maxWidth: '140px' }} title={item.trade_source}>
                            {item.trade_source}
                          </span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>

                      {/* 11. Actions (Edit & Delete) */}
                      <td style={{ textAlign: 'center' }}>
                        <div className="d-flex align-items-center justify-content-center gap-1">
                          <button
                            type="button"
                            className="btn btn-sm btn-link p-1 text-secondary"
                            onClick={() => handleOpenEdit(item)}
                            title={`Edit ${item.symbol}`}
                          >
                            <Edit2 size={14} />
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-link p-1 text-danger"
                            onClick={() => handleDeleteTrade(item)}
                            title={`Delete ${item.symbol}`}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Swing Trade Add / Edit Modal */}
      <SwingTradeModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleModalSubmit}
        isEditMode={isEditMode}
        editItem={editItem}
        sources={sources}
        onSourceAdded={(newSources) => setSources(newSources)}
        showToast={showToast}
      />
    </div>
  );
}

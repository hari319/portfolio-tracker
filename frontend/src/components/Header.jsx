import React from 'react';
import { RefreshCw } from 'lucide-react';
import { formatDateTime } from '../utils/date';

const TAB_HEADERS = {
  tracker: {
    title: 'Portfolio and Stock Monitor',
    subtitle: (
      <>
        Live NSE/BSE prices with daily &amp; weekly EMAs. A value is shown in{' '}
        <span className="text-below-pill">red</span> only when the current price is below that EMA.
      </>
    ),
  },
  'portfolio-tracker': {
    title: 'Portfolio Tracker',
    subtitle: 'Detailed portfolio bookkeeping with lot-level purchase tracking, realized/unrealized P&L, dividend records, and portfolio balance sheets.',
  },
  status: {
    title: 'Stock Analysis & Status',
    subtitle: 'Valuation scenarios (Base, Bull, Bear), target prices, entry levels, and research status notes alongside live market quotes.',
  },
  screener: {
    title: 'Stock Screener',
    subtitle: 'Multi-day technical screening, strategy presets, and customizable metrics for NSE/BSE equities.',
  },
  'swing-tracker': {
    title: 'Swing Tracker',
    subtitle: 'Track swing trades, entry zones, stop losses, multiple targets, pattern breakouts, and trade sources with live price monitoring.',
  },
};

export default function Header({
  activeTab = 'tracker',
  generatedAt,
  source,
  stats = {},
  isRefreshing = false,
  onRefresh,
  showRefresh = true,
}) {
  const formatUpdated = (iso) => {
    if (!iso) return 'No data yet — click “Refresh now”.';
    const timeStr = formatDateTime(iso);
    return `Updated ${timeStr} ${source ? `(${source})` : ''}`;
  };

  const headerContent = TAB_HEADERS[activeTab] || TAB_HEADERS.tracker;

  return (
    <header className="app-header">
      <div className="row align-items-center g-3">
        {/* Title and Subtitle */}
        <div className="col-12 col-md-7">
          <h1 className="app-title">{headerContent.title}</h1>
          <p className="app-subtitle">{headerContent.subtitle}</p>
        </div>

        {/* Refresh button and metadata (only shown on Tracker tab) */}
        {showRefresh && (
          <div className="col-12 col-md-5 d-flex flex-column align-items-md-end align-items-start gap-2">
            <button
              type="button"
              className="btn btn-primary d-inline-flex align-items-center gap-2 px-3 py-2 fw-medium shadow-sm"
              onClick={onRefresh}
              disabled={isRefreshing}
            >
              <RefreshCw size={16} className={isRefreshing ? 'spinner-border-sm spin-anim' : ''} />
              <span>{isRefreshing ? 'Refreshing data...' : 'Refresh now'}</span>
            </button>

            <div className="d-flex flex-column align-items-md-end align-items-start text-muted" style={{ fontSize: '0.8rem' }}>
              <span>{formatUpdated(generatedAt)}</span>
              {stats && stats.total > 0 && (
                <span className="fw-semibold text-dark">
                  {stats.ok} / {stats.total} Tickers OK
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </header>
  );
}

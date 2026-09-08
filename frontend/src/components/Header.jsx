import React from 'react';
import { RefreshCw } from 'lucide-react';
import { formatDateTime } from '../utils/date';

export default function Header({
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


  return (
    <header className="app-header">
      <div className="row align-items-center g-3">
        {/* Title and Subtitle */}
        <div className="col-12 col-md-7">
          <h1 className="app-title">Portfolio and Stock Monitor</h1>
          <p className="app-subtitle">
            Live NSE/BSE prices with daily &amp; weekly EMAs. A value is shown in{' '}
            <span className="text-below-pill">red</span> only when the current price is below that EMA.
          </p>
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

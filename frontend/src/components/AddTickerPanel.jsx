import React, { useState, useMemo } from 'react';
import { PlusCircle } from 'lucide-react';

export default function AddTickerPanel({
  portfolioNames = ['BAPA', 'MADI'],
  portfolios = {},
  defaultSuffix = '.NS',
  onAddTicker,
  disabled = false,
}) {
  const [selectedPortfolio, setSelectedPortfolio] = useState(portfolioNames[0] || 'BAPA');
  const [symbol, setSymbol] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Real-time duplicate check
  const duplicateInfo = useMemo(() => {
    const raw = symbol.trim().toUpperCase();
    if (!raw) return null;

    const normalized = raw.startsWith('^') || raw.includes('.')
      ? raw
      : `${raw}${defaultSuffix}`;

    const baseRaw = raw.replace(/\.(NS|BO)$/, '');

    for (const [pName, pData] of Object.entries(portfolios)) {
      const rows = pData.rows || [];
      for (const row of rows) {
        const rowSymbol = (row.symbol || '').toUpperCase();
        const baseRow = rowSymbol.replace(/\.(NS|BO)$/, '');

        if (rowSymbol === normalized || rowSymbol === raw || baseRow === baseRaw) {
          if (pName === selectedPortfolio) {
            const sourcedText = row.is_sourced ? ' (from Portfolio Tracker)' : '';
            return {
              type: 'warning',
              message: `⚠️ ${normalized} is already in ${pName}${sourcedText}.`,
            };
          } else {
            return {
              type: 'info',
              message: `ℹ️ ${normalized} is in ${pName} (will also be added to ${selectedPortfolio}).`,
            };
          }
        }
      }
    }
    return null;
  }, [symbol, selectedPortfolio, portfolios, defaultSuffix]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const cleanSymbol = symbol.trim();
    if (!cleanSymbol) return;

    setIsSubmitting(true);
    try {
      await onAddTicker(selectedPortfolio, cleanSymbol);
      setSymbol('');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="dashboard-card p-3 h-100">
      <h3 className="panel-title">Add a Ticker</h3>

      <form onSubmit={handleSubmit} autoComplete="off">
        <div className="row g-2">
          {/* Portfolio Select */}
          <div className="col-12 col-sm-4">
            <select
              className="form-select form-select-sm"
              value={selectedPortfolio}
              onChange={(e) => setSelectedPortfolio(e.target.value)}
              disabled={disabled || isSubmitting}
              aria-label="Select Portfolio"
            >
              {portfolioNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          {/* Symbol Input */}
          <div className="col-12 col-sm-5">
            <input
              type="text"
              className="form-control form-control-sm"
              placeholder="e.g. CARTRADE or CARTRADE.NS"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              maxLength={24}
              required
              disabled={disabled || isSubmitting}
              aria-label="Ticker symbol"
            />
          </div>

          {/* Submit Button */}
          <div className="col-12 col-sm-3">
            <button
              type="submit"
              className="btn btn-primary btn-sm w-100 d-inline-flex align-items-center justify-content-center gap-1"
              disabled={disabled || isSubmitting || !symbol.trim()}
            >
              <PlusCircle size={14} />
              <span>{isSubmitting ? 'Adding...' : 'Add & fetch'}</span>
            </button>
          </div>
        </div>

        {/* Duplicate Warning/Info Hint */}
        {duplicateInfo && (
          <div className={`dup-hint ${duplicateInfo.type}`}>
            {duplicateInfo.message}
          </div>
        )}

        <p className="field-hint">
          Plain symbols get <code>{defaultSuffix}</code> automatically. Use <code>.BO</code> for BSE.
        </p>
      </form>
    </div>
  );
}

import React from 'react';
import { ExternalLink, Trash2, AlertCircle } from 'lucide-react';
import EmaCell from './EmaCell';

export default function PortfolioTable({
  portfolioName,
  rows = [],
  periods = [9, 21, 50, 100, 200],
  onRemoveTicker,
  disabled = false,
}) {
  if (!rows || rows.length === 0) {
    return (
      <div className="p-4 text-center text-muted">
        No tickers in <strong>{portfolioName}</strong> yet — add one using the form above.
      </div>
    );
  }

  return (
    <div className="table-responsive-wrapper">
      <table className="table-stock">
        <thead>
          <tr>
            <th className="col-sticky-ticker" style={{ width: '220px' }}>Ticker</th>
            <th style={{ width: '130px' }}>Current Price</th>
            <th style={{ width: '90px' }}>Signal</th>
            {periods.map((period) => (
              <th key={period} style={{ minWidth: '100px' }}>
                {period} EMA
              </th>
            ))}
            <th style={{ width: '50px', textAlign: 'center' }}>
              <span className="visually-hidden">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isError = Boolean(row.error);

            return (
              <tr key={row.symbol} className={isError ? 'row-error' : ''}>
                {/* Ticker Column */}
                <td className="col-sticky-ticker">
                  <div className="col-ticker-wrap">
                    <div className="d-flex align-items-center gap-1">
                      <a
                        href={row.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="ticker-link d-inline-flex align-items-center gap-1"
                        title={`Open ${row.symbol} on TradingView`}
                      >
                        {row.display || row.symbol}
                        <ExternalLink size={12} className="opacity-75" />
                      </a>

                      {row.notes && row.notes.length > 0 && (
                        <span
                          className="note-flag"
                          title={row.notes.join(' • ')}
                        >
                          !
                        </span>
                      )}
                    </div>

                    {row.name && (
                      <div className="stock-company-name" title={row.name}>
                        {row.name}
                      </div>
                    )}
                  </div>
                </td>

                {/* Data or Error */}
                {isError ? (
                  <td colSpan={periods.length + 2} className="text-danger py-2">
                    <div className="d-flex align-items-center gap-2">
                      <AlertCircle size={15} />
                      <span>Data unavailable — {row.error}</span>
                    </div>
                  </td>
                ) : (
                  <>
                    {/* Current Price */}
                    <td>
                      <span className="col-price-val">
                        {row.price_display || (row.price !== undefined ? row.price.toFixed(2) : '—')}
                      </span>
                    </td>

                    {/* Signal */}
                    <td>
                      <span
                        className={
                          row.signal === 'Sell'
                            ? 'badge-signal-sell'
                            : 'badge-signal-hold'
                        }
                      >
                        {row.signal || 'Hold'}
                      </span>
                    </td>

                    {/* EMAs */}
                    {periods.map((period) => {
                      const cell = row.emas ? row.emas[String(period)] : null;
                      return (
                        <td key={period}>
                          <EmaCell cell={cell} period={period} />
                        </td>
                      );
                    })}
                  </>
                )}

                {/* Actions (Delete) */}
                <td style={{ textAlign: 'center' }}>
                  <button
                    type="button"
                    className="action-del-btn"
                    title={`Remove ${row.symbol} from ${portfolioName}`}
                    disabled={disabled}
                    onClick={() => onRemoveTicker(portfolioName, row.symbol)}
                  >
                    <Trash2 size={15} />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

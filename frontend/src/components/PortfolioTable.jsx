import React from 'react';
import { ExternalLink, Trash2, AlertCircle } from 'lucide-react';
import EmaCell from './EmaCell';

function getCostRiskInfo(row) {
  const avgPrice = Number(row.avg_price);
  const currentPrice = Number(row.price);

  if (
    row.avg_price === null ||
    row.avg_price === undefined ||
    isNaN(avgPrice) ||
    avgPrice <= 0 ||
    row.price === null ||
    row.price === undefined ||
    isNaN(currentPrice) ||
    row.error
  ) {
    return null;
  }

  // Use backend tier/drawdown if provided, else compute as fallback
  const drawdownPct =
    typeof row.cost_drawdown_pct === 'number'
      ? row.cost_drawdown_pct
      : Number((((currentPrice - avgPrice) / avgPrice) * 100).toFixed(2));

  if (drawdownPct >= 0) {
    return null; // At or above cost basis, no risk pill
  }

  let tier = row.risk_tier;
  if (!tier) {
    if (drawdownPct > -5.0) {
      tier = 'mild';
    } else if (drawdownPct > -10.0) {
      tier = 'moderate';
    } else {
      tier = 'critical';
    }
  }

  const absPct = Math.abs(drawdownPct).toFixed(1);
  const formattedAvg = avgPrice.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  let tooltip = '';
  if (tier === 'mild') {
    tooltip = `Minor pullback: trading ${absPct}% below average cost (₹${formattedAvg})`;
  } else if (tier === 'moderate') {
    tooltip = `Stop-loss zone: trading ${absPct}% below average cost (₹${formattedAvg})`;
  } else {
    tooltip = `Critical drawdown: trading ${absPct}% below average cost (₹${formattedAvg})`;
  }

  return {
    tier,
    drawdownPct,
    label: `▼ -${absPct}%`,
    tooltip,
  };
}

export default function PortfolioTable({
  portfolioName,
  rows = [],
  periods = [9, 21, 50, 100, 200],
  onRemoveTicker,
  disabled = false,
  searchQuery = '',
}) {
  const sortedRows = React.useMemo(() => {
    if (!rows || rows.length === 0) return [];
    return [...rows].sort((a, b) => {
      const aErr = Boolean(a.error || a.price === null || a.price === undefined);
      const bErr = Boolean(b.error || b.price === null || b.price === undefined);
      if (aErr && !bErr) return 1;
      if (!aErr && bErr) return -1;
      return 0; // preserve server-side EMA order for normal rows
    });
  }, [rows]);

  if (!sortedRows || sortedRows.length === 0) {
    return (
      <div className="p-4 text-center text-muted">
        {searchQuery ? (
          <>No tickers matching &ldquo;{searchQuery}&rdquo; in <strong>{portfolioName}</strong>.</>
        ) : (
          <>No tickers in <strong>{portfolioName}</strong> yet — add one using the form above.</>
        )}
      </div>
    );
  }

  return (
    <div className="table-responsive-wrapper">
      <table className="table-stock">
        <thead>
          <tr>
            <th className="col-sticky-ticker" style={{ width: '220px' }}>Ticker</th>
            <th style={{ width: '120px' }}>Avg Price</th>
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
          {sortedRows.map((row) => {
            const isError = Boolean(row.error);
            const riskInfo = !isError ? getCostRiskInfo(row) : null;

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

                {/* Avg Price */}
                <td>
                  <div className="col-avg-price-wrap">
                    <span className="col-price-val">
                      {row.avg_price !== null && row.avg_price !== undefined
                        ? `₹${Number(row.avg_price).toLocaleString('en-IN', {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}`
                        : '—'}
                    </span>
                    {riskInfo && (
                      <span
                        className={`cost-risk-pill tier-${riskInfo.tier}`}
                        title={riskInfo.tooltip}
                      >
                        {riskInfo.label}
                      </span>
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
                  {row.is_sourced ? (
                    <button
                      type="button"
                      className="action-del-btn opacity-30"
                      title="Managed by Portfolio Tracker — mark as sold in Portfolio Tracker to remove"
                      disabled={true}
                      style={{ cursor: 'not-allowed' }}
                    >
                      <Trash2 size={15} />
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="action-del-btn"
                      title={`Remove ${row.symbol} from ${portfolioName}`}
                      disabled={disabled}
                      onClick={() => onRemoveTicker(portfolioName, row.symbol)}
                    >
                      <Trash2 size={15} />
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

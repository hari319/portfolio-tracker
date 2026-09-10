import React, { useState } from 'react';
import {
  ExternalLink,
  Edit2,
  Trash2,
  Calendar,
  FileText,
  Clock,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { formatDate } from '../utils/date';


const calculateDiffPercent = (current, reference) => {
  if (
    current === undefined ||
    current === null ||
    reference === undefined ||
    reference === null ||
    Number(reference) <= 0
  ) {
    return null;
  }
  return (
    ((Number(current) - Number(reference)) / Number(reference)) * 100
  );
};

const renderPriceDiffPill = (percent, title) => {
  if (percent === null || percent === undefined) return null;
  return (
    <span
      className={`price-change-pill ${percent >= 0 ? 'pos' : 'neg'}`}
      title={title}
    >
      {percent >= 0 ? '+' : ''}
      {percent.toFixed(1)}%
    </span>
  );
};

const renderStatusBadge = (status) => {
  if (!status) return <span className='text-muted'>—</span>;
  const s = status.trim().toLowerCase();
  let badgeClass = 'status-badge';
  if (s === 'buy') {
    badgeClass += ' status-badge-buy';
  } else if (s === 'avoid') {
    badgeClass += ' status-badge-avoid';
  } else if (s === 'hold') {
    badgeClass += ' status-badge-hold';
  } else if (s === 'acc on dip') {
    badgeClass += ' status-badge-acc-on-dip';
  } else {
    badgeClass += ' bg-light text-secondary border';
  }
  return <span className={badgeClass}>{status}</span>;
};

function RemarksCell({ text }) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!text || !text.trim()) {
    return <span className='text-muted'>—</span>;
  }

  const trimmed = text.trim();
  const lines = trimmed
    .split('\n')
    .filter((l) => l.trim().length > 0);
  const isLong = trimmed.length > 90 || lines.length > 1;

  if (!isLong) {
    return (
      <div className='remarks-cell-container'>
        <div className='remarks-content'>{trimmed}</div>
      </div>
    );
  }

  let preview = lines[0] || '';
  if (preview.length > 80) {
    preview = preview.slice(0, 80) + '...';
  } else if (lines.length > 1) {
    preview = preview + '...';
  }

  return (
    <div className='remarks-cell-container'>
      {isExpanded ? (
        <div className='remarks-content'>{trimmed}</div>
      ) : (
        <div className='remarks-preview'>{preview}</div>
      )}
      <button
        type='button'
        className='remarks-toggle-btn'
        onClick={() => setIsExpanded((prev) => !prev)}
      >
        {isExpanded ? (
          <>
            <ChevronUp size={12} /> Show less
          </>
        ) : (
          <>
            <ChevronDown size={12} /> Show more
          </>
        )}
      </button>
    </div>
  );
}

export default function StatusTable({
  items = [],
  liveQuotes = {},
  onEditItem,
  onDeleteItem,
  disabled = false,
}) {
  // State for selected history date per ticker: { [symbol]: selectedItemId }
  const [selectedHistoryMap, setSelectedHistoryMap] = useState({});

  const getTradingViewUrl = (symbol) => {
    let clean = (symbol || '').toUpperCase();
    if (clean.endsWith('.NS')) {
      return `https://www.tradingview.com/chart/?symbol=NSE%3A${clean.slice(0, -3)}`;
    }
    if (clean.endsWith('.BO')) {
      return `https://www.tradingview.com/chart/?symbol=BSE%3A${clean.slice(0, -3)}`;
    }
    return `https://www.tradingview.com/chart/?symbol=${clean}`;
  };

  const formatPrice = (val, currency = 'INR') => {
    if (val === null || val === undefined || val === '') return '—';
    const num = Number(val);
    if (isNaN(num)) return String(val);
    return `${currency === 'INR' ? '₹' : currency + ' '}${num.toLocaleString(
      'en-IN',
      {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      },
    )}`;
  };

  const formatTimestamp = (isoStr) => {
    if (!isoStr) return '';
    const date = new Date(isoStr);
    if (isNaN(date.getTime())) {
      return isoStr;
    }
    const d = String(date.getDate()).padStart(2, '0');
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const y = date.getFullYear();
    const t = date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
    return `${d}/${m}/${y} ${t}`;
  };


  const renderScenarioTarget = (pair, typeClass) => {
    if (!pair || (!pair[0] && !pair[1])) {
      return <span className='text-muted'>—</span>;
    }
    const targetPrice = pair[0];
    const targetCagr = pair[1];

    return (
      <div className={`scenario-pill-pair ${typeClass}`}>
        <div className='scenario-item-target'>
          {targetPrice ? (
            <span className='target-num'>₹{targetPrice}</span>
          ) : (
            <span className='pill-empty'>—</span>
          )}
        </div>
        {targetCagr && (
          <div className='scenario-item-cagr'>
            <span className='cagr-val'>{targetCagr}%</span>
          </div>
        )}
      </div>
    );
  };

  if (!items || items.length === 0) {
    return (
      <div className='p-5 text-center text-muted'>
        <FileText
          size={32}
          className='opacity-40 mb-2'
        />
        <p className='mb-0'>
          No stock status records found. Click{' '}
          <strong>+ Add Stock</strong> above to create one.
        </p>
      </div>
    );
  }

  // Group items by ticker symbol
  const groupedBySymbol = {};
  items.forEach((item) => {
    const sym = item.symbol;
    if (!groupedBySymbol[sym]) {
      groupedBySymbol[sym] = [];
    }
    groupedBySymbol[sym].push(item);
  });

  // Helper to determine if an item has "Avoid" status
  const isAvoidStatus = (item) => {
    return (item?.status || '').trim().toLowerCase() === 'avoid';
  };

  // Sort unique symbols so that symbols with 'Avoid' status appear last in the table
  const uniqueSymbols = Object.keys(groupedBySymbol).sort((symA, symB) => {
    const listA = groupedBySymbol[symA] || [];
    const listB = groupedBySymbol[symB] || [];
    const idA = selectedHistoryMap[symA] || listA[0]?.id;
    const idB = selectedHistoryMap[symB] || listB[0]?.id;
    const itemA = listA.find((it) => it.id === idA) || listA[0];
    const itemB = listB.find((it) => it.id === idB) || listB[0];

    const isAvoidA = isAvoidStatus(itemA);
    const isAvoidB = isAvoidStatus(itemB);

    if (isAvoidA && !isAvoidB) return 1;
    if (!isAvoidA && isAvoidB) return -1;
    return 0; // preserve original relative order
  });

  return (
    <div className='table-responsive-wrapper'>
      <table className='table-stock status-table'>
        <thead>
          <tr>
            <th className='col-sticky-ticker' style={{ width: '180px' }}>Ticker</th>
            <th style={{ width: '160px' }}>Date of Analysis</th>
            <th style={{ width: '110px' }}>Status</th>
            <th style={{ width: '120px' }}>Price of Analysis</th>
            <th style={{ width: '140px' }}>Current Price</th>
            <th style={{ width: '140px' }}>Best Entry</th>
            <th style={{ width: '130px' }}>Base</th>
            <th style={{ width: '130px' }}>Bull</th>
            <th style={{ width: '130px' }}>Bear</th>
            <th style={{ minWidth: '220px' }}>Remarks</th>

            <th style={{ width: '75px', textAlign: 'center' }}>
              <span className='visually-hidden'>Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {uniqueSymbols.map((symbol) => {
            const historyList = groupedBySymbol[symbol] || [];
            // Default to latest (first in list) if not explicitly chosen
            const selectedId =
              selectedHistoryMap[symbol] || historyList[0]?.id;
            const activeItem =
              historyList.find((it) => it.id === selectedId) ||
              historyList[0];

            if (!activeItem) return null;

            const liveQuote = liveQuotes[symbol];
            const livePrice = liveQuote?.price;
            const hasMultipleHistory = historyList.length > 1;

            // Calculate change from analysis price & best entry using shared helper
            const currentPriceDiff = calculateDiffPercent(
              livePrice,
              activeItem.price_of_analysis,
            );
            const bestEntryDiff = calculateDiffPercent(
              livePrice,
              activeItem.best_entry,
            );

            return (
              <tr key={symbol}>
                {/* Ticker (Sticky column) */}
                <td className='col-sticky-ticker'>
                  <div className='col-ticker-wrap'>
                    <div className='d-flex align-items-center gap-1'>
                      <a
                        href={getTradingViewUrl(activeItem.symbol)}
                        target='_blank'
                        rel='noopener noreferrer'
                        className='ticker-link d-inline-flex align-items-center gap-1'
                        title={`Open ${activeItem.symbol} on TradingView`}
                      >
                        {activeItem.symbol}
                        <ExternalLink
                          size={12}
                          className='opacity-75'
                        />
                      </a>
                      {hasMultipleHistory && (
                        <span
                          className='history-count-badge'
                          title={`${historyList.length} analysis records available`}
                        >
                          <Clock
                            size={10}
                            className='me-1'
                          />
                          {historyList.length}
                        </span>
                      )}
                    </div>
                    {activeItem.name && (
                      <div
                        className='stock-company-name'
                        title={activeItem.name}
                      >
                        {activeItem.name}
                      </div>
                    )}
                  </div>
                </td>

                {/* Date of Analysis (Fancy dropdown if multiple history, badge if single) */}
                <td>
                  {hasMultipleHistory ? (
                    <div className='fancy-date-select-container'>
                      <div className='fancy-date-select-inner'>
                        <Calendar
                          size={13}
                          className='text-primary date-icon'
                        />
                        <select
                          className='fancy-date-select'
                          value={activeItem.id}
                          onChange={(e) =>
                            setSelectedHistoryMap((prev) => ({
                              ...prev,
                              [symbol]: e.target.value,
                            }))
                          }
                          aria-label={`Select analysis date for ${symbol}`}
                        >
                          {historyList.map((hist, idx) => (
                            <option
                              key={hist.id}
                              value={hist.id}
                            >
                              {formatDate(hist.date_of_analysis)}{' '}
                              {idx === 0 ? '★ Latest' : ''}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  ) : (
                    <div className='single-date-pill'>
                      <Calendar
                        size={13}
                        className='text-muted opacity-75 me-1'
                      />
                      <span className='analysis-date-val'>
                        {formatDate(activeItem.date_of_analysis)}
                      </span>
                    </div>
                  )}

                </td>

                {/* Status Column */}
                <td>{renderStatusBadge(activeItem.status)}</td>

                {/* Price of Analysis */}
                <td>
                  <span className='col-price-val text-muted'>
                    {formatPrice(
                      activeItem.price_of_analysis,
                      activeItem.currency,
                    )}
                  </span>
                </td>

                {/* Current Price (Price upside, Time/Date downside) */}
                <td>
                  <div className='col-live-price-wrap'>
                    <div className='d-flex align-items-center gap-1'>
                      <span className='col-price-val fw-bold text-dark'>
                        {livePrice !== undefined &&
                        livePrice !== null ? (
                          formatPrice(livePrice, activeItem.currency)
                        ) : (
                          <span
                            className='spinner-border spinner-border-sm text-muted'
                            role='status'
                            style={{ width: '12px', height: '12px' }}
                          />
                        )}
                      </span>
                      {renderPriceDiffPill(
                        currentPriceDiff,
                        `Change since analysis on ${formatDate(activeItem.date_of_analysis)}`,
                      )}

                    </div>

                    {/* Date and time below price */}
                    {liveQuote && liveQuote.as_of && (
                      <div className='price-as-of-text'>
                        {liveQuote.is_cached && (
                          <span
                            className='cached-badge me-1'
                            title='Live quote unavailable, showing last stored price'
                          >
                            Last known
                          </span>
                        )}
                        <span>
                          {formatTimestamp(liveQuote.as_of)}
                        </span>
                      </div>
                    )}
                  </div>
                </td>

                {/* Best Entry (Price + Percentage difference relative to Current Price) */}
                <td>
                  {activeItem.best_entry !== undefined &&
                  activeItem.best_entry !== null &&
                  activeItem.best_entry !== '' ? (
                    <div className='d-flex align-items-center gap-1'>
                      <span className='col-price-val fw-bold text-dark'>
                        {formatPrice(
                          activeItem.best_entry,
                          activeItem.currency,
                        )}
                      </span>
                      {renderPriceDiffPill(
                        bestEntryDiff,
                        `Difference between Current Price and Best Entry`,
                      )}
                    </div>
                  ) : (
                    <span className='text-muted'>—</span>
                  )}
                </td>

                {/* Base (Target & CAGR) */}
                <td>
                  {renderScenarioTarget(activeItem.base, 'base-pill')}
                </td>

                {/* Bull (Target & CAGR) */}
                <td>
                  {renderScenarioTarget(activeItem.bull, 'bull-pill')}
                </td>

                {/* Bear (Target & CAGR) */}
                <td>
                  {renderScenarioTarget(activeItem.bear, 'bear-pill')}
                </td>

                {/* Remarks (Collapsible, formatted with matching styling) */}
                <td>
                  <RemarksCell text={activeItem.remarks} />
                </td>
                {/* Actions: Edit & Delete (placed next to Best Entry) */}
                <td style={{ textAlign: 'center' }}>
                  <div className='d-inline-flex align-items-center gap-1'>
                    <button
                      type='button'
                      className='action-edit-btn'
                      title={`Edit or add history for ${activeItem.symbol}`}
                      disabled={disabled}
                      onClick={() => onEditItem(activeItem)}
                    >
                      <Edit2 size={14} />
                    </button>
                    <button
                      type='button'
                      className='action-del-btn'
                      title={`Delete this analysis entry (${formatDate(activeItem.date_of_analysis)})`}
                      disabled={disabled}

                      onClick={() =>
                        onDeleteItem(activeItem.id, activeItem.symbol)
                      }
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

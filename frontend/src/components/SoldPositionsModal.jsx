import React, { useRef, useState, useEffect, useMemo } from 'react';
import {
  History,
  ChevronDown,
  ChevronRight,
  FileText,
  Search,
  X,
} from 'lucide-react';
import { formatDate } from '../utils/date';


export default function SoldPositionsModal({
  show,
  onClose,
  activePortfolio,
  groupedSoldHoldings,
  soldHoldings,
  soldTotals,
  expandedSoldHoldings,
  toggleExpandSold,
  onOpenNotes,
}) {
  const topScrollRef = useRef(null);
  const tableContainerRef = useRef(null);
  const searchInputRef = useRef(null);
  const [scrollWidth, setScrollWidth] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');

  // Focus search on Ctrl+F / Cmd+F when modal is open
  useEffect(() => {
    if (!show) return;
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        e.stopPropagation();
        if (searchInputRef.current) {
          searchInputRef.current.focus();
          searchInputRef.current.select();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown, true);
    return () => window.removeEventListener('keydown', handleKeyDown, true);
  }, [show]);

  // Reset search when modal opens/closes
  useEffect(() => {
    if (!show) {
      setSearchQuery('');
    }
  }, [show]);

  // Filtered grouped sold holdings
  const filteredGroupedHoldings = useMemo(() => {
    if (!searchQuery.trim()) return groupedSoldHoldings;
    const q = searchQuery.trim().toLowerCase();
    return groupedSoldHoldings.filter((s) => {
      const scheme = (s.scheme_name || '').toLowerCase();
      const symbol = (s.symbol || '').toLowerCase();
      const remarks = (s.remarks || s.sale_remarks || '').toLowerCase();
      const person = (s.person || s.app || '').toLowerCase();
      return (
        scheme.includes(q) ||
        symbol.includes(q) ||
        remarks.includes(q) ||
        person.includes(q)
      );
    });
  }, [groupedSoldHoldings, searchQuery]);

  // Filtered sold totals
  const filteredSoldTotals = useMemo(() => {
    if (!searchQuery.trim()) return soldTotals;
    let inv = 0;
    let cur = 0;
    let earned = 0;
    let loss = 0;
    for (const g of filteredGroupedHoldings) {
      inv += g.invested_amount || 0;
      cur += g.current_total || 0;
      earned += g.earned || 0;
      loss += g.loss || 0;
    }
    return {
      invested_amount: inv,
      current_total: cur,
      earned,
      loss,
      net_profit: cur - inv,
    };
  }, [filteredGroupedHoldings, searchQuery, soldTotals]);

  useEffect(() => {
    if (!show) return;
    const updateWidth = () => {
      if (tableContainerRef.current) {
        setScrollWidth(tableContainerRef.current.scrollWidth);
      }
    };
    // Give table time to layout
    const timer = setTimeout(updateWidth, 50);
    window.addEventListener('resize', updateWidth);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', updateWidth);
    };
  }, [show, groupedSoldHoldings, expandedSoldHoldings]);

  const handleTableScroll = () => {
    if (topScrollRef.current && tableContainerRef.current) {
      topScrollRef.current.scrollLeft = tableContainerRef.current.scrollLeft;
    }
  };

  const handleTopScroll = () => {
    if (tableContainerRef.current && topScrollRef.current) {
      tableContainerRef.current.scrollLeft = topScrollRef.current.scrollLeft;
    }
  };

  if (!show) return null;

  return (
    <div
      className='modal show d-block'
      tabIndex='-1'
      style={{ backgroundColor: 'rgba(0,0,0,0.55)', zIndex: 1050 }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className='modal-dialog modal-xl modal-dialog-scrollable modal-dialog-centered'
        style={{ maxWidth: '96vw' }}
      >
        <div className='modal-content shadow-lg'>
          <div className='modal-header bg-light py-2 px-3 border-bottom d-flex flex-wrap justify-content-between align-items-center gap-2'>
            <div className='d-flex flex-wrap align-items-center gap-2'>
              <History size={18} className='text-secondary' />
              <h5 className='modal-title fw-bold text-secondary mb-0'>
                Sold Positions History — {activePortfolio}
              </h5>
              <span className='badge bg-secondary ms-1'>
                {filteredGroupedHoldings.length}
                {filteredGroupedHoldings.length !== groupedSoldHoldings.length
                  ? ` / ${groupedSoldHoldings.length}`
                  : ''}{' '}
                holdings ({soldHoldings.length} trades)
              </span>
              <span className='badge bg-light text-muted border ms-1 d-none d-md-inline'>
                Sorted: Most recent sell date first
              </span>
            </div>

            <div className='d-flex align-items-center gap-3'>
              {/* Real-time search field with Ctrl+F shortcut */}
              <div
                className='input-group input-group-sm'
                style={{ width: '260px' }}
              >
                <span className='input-group-text bg-white border-end-0 text-muted'>
                  <Search size={14} />
                </span>
                <input
                  ref={searchInputRef}
                  type='text'
                  className='form-control border-start-0 ps-0'
                  placeholder='Search sold positions... (Ctrl+F)'
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                {searchQuery && (
                  <button
                    type='button'
                    className='btn btn-outline-secondary border-start-0'
                    onClick={() => {
                      setSearchQuery('');
                      searchInputRef.current?.focus();
                    }}
                    title='Clear search'
                  >
                    <X size={13} />
                  </button>
                )}
              </div>

              <button
                type='button'
                className='btn-close'
                onClick={onClose}
                aria-label='Close'
              />
            </div>
          </div>

          {/* Top KPI Summary Strip — Always visible without scrolling */}
          <div className='sold-kpi-bar d-flex flex-wrap align-items-center justify-content-between gap-2'>
            <div className='d-flex flex-wrap align-items-center gap-2'>
              <div className='sold-kpi-item'>
                <span className='text-muted small'>Sold:</span>
                <strong>{filteredGroupedHoldings.length}</strong>
                <span className='text-muted small'>({soldHoldings.length} trades)</span>
              </div>
              <div className='sold-kpi-item'>
                <span className='text-muted small'>Invested:</span>
                <strong className='text-dark'>
                  ₹{filteredSoldTotals.invested_amount?.toLocaleString()}
                </strong>
              </div>
              <div className='sold-kpi-item'>
                <span className='text-muted small'>Exit Total:</span>
                <strong className='text-dark'>
                  ₹{filteredSoldTotals.current_total?.toLocaleString()}
                </strong>
              </div>
              <div className='sold-kpi-item'>
                <span className='text-muted small'>Realized P&L:</span>
                <strong
                  className={
                    filteredSoldTotals.net_profit >= 0
                      ? 'text-success'
                      : 'text-danger'
                  }
                >
                  {filteredSoldTotals.net_profit >= 0 ? '+' : ''}₹
                  {filteredSoldTotals.net_profit?.toLocaleString()}
                  {filteredSoldTotals.invested_amount > 0 && (
                    <span className='ms-1 small fw-normal'>
                      (
                      {(
                        (filteredSoldTotals.net_profit /
                          filteredSoldTotals.invested_amount) *
                        100
                      ).toFixed(2)}
                      %)
                    </span>
                  )}
                </strong>
              </div>
            </div>

            <div className='d-flex align-items-center gap-2'>
              {filteredSoldTotals.earned > 0 && (
                <span className='badge bg-success-subtle text-success border border-success-subtle px-2 py-1'>
                  Earned: +₹{filteredSoldTotals.earned?.toLocaleString()}
                </span>
              )}
              {filteredSoldTotals.loss < 0 && (
                <span className='badge bg-danger-subtle text-danger border border-danger-subtle px-2 py-1'>
                  Loss: -₹{Math.abs(filteredSoldTotals.loss)?.toLocaleString()}
                </span>
              )}
            </div>
          </div>

          {/* Top Horizontal Scrollbar - Easy access without scrolling to bottom */}
          {scrollWidth > 0 && (
            <div
              ref={topScrollRef}
              onScroll={handleTopScroll}
              style={{
                overflowX: 'auto',
                overflowY: 'hidden',
                height: '14px',
                backgroundColor: '#f1f3f5',
                borderBottom: '1px solid #dee2e6',
              }}
            >
              <div style={{ width: scrollWidth, height: '1px' }} />
            </div>
          )}

          <div className='modal-body p-0'>
            <div
              ref={tableContainerRef}
              onScroll={handleTableScroll}
              className='table-responsive'
              style={{
                maxHeight: 'calc(85vh - 170px)',
                overflow: 'auto',
              }}
            >
              <table className='table table-hover table-striped table-sticky-tfoot align-middle mb-0 text-nowrap'>
                <thead
                  className='table-light position-sticky top-0'
                  style={{ zIndex: 3 }}
                >
                  <tr style={{ fontSize: '0.82rem' }}>
                    <th className='col-sticky-expand'></th>
                    <th className='col-sticky-scheme'>Scheme</th>
                    <th>Invest Date</th>
                    <th>Sell Date</th>
                    <th className='text-end' title='Years held'>Y</th>
                    <th className='text-end' title='Total months held'>M</th>
                    <th className='text-end'>Q</th>
                    <th className='text-end'>Avg (₹)</th>
                    <th className='text-end'>Exit LTP (₹)</th>
                    <th className='text-end'>Invested (₹)</th>
                    <th className='text-end'>Buy Chg</th>
                    <th className='text-end'>Sell Chg</th>
                    <th className='text-end'>Exit Total (₹)</th>
                    <th className='text-end'>Earned (₹)</th>
                    <th className='text-end'>Loss (₹)</th>
                    <th className='text-end'>Annual %</th>
                    <th className='text-end'>Return %</th>
                    {activePortfolio === 'LOAN' && <th>Person</th>}
                    <th>Remarks</th>
                    <th className='text-center'>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {groupedSoldHoldings.length === 0 ? (
                    <tr>
                      <td
                        colSpan={activePortfolio === 'LOAN' ? 20 : 19}
                        className='text-center py-4 text-muted'
                      >
                        No sold positions recorded yet for {activePortfolio}.
                      </td>
                    </tr>
                  ) : filteredGroupedHoldings.length === 0 ? (
                    <tr>
                      <td
                        colSpan={activePortfolio === 'LOAN' ? 20 : 19}
                        className='text-center py-4 text-muted'
                      >
                        No sold positions matching "{searchQuery}".
                        <button
                          type='button'
                          className='btn btn-sm btn-link p-0 ms-1'
                          onClick={() => setSearchQuery('')}
                        >
                          Clear search
                        </button>
                      </td>
                    </tr>
                  ) : (
                    filteredGroupedHoldings.map((s) => {
                      const isExpanded = !!expandedSoldHoldings[s.groupKey];
                      const hasMultipleSales = s.hasMultipleSales;
                      const isPositive = s.total_return >= 0;

                      return (
                        <React.Fragment key={s.id}>
                          <tr>
                            <td className='col-sticky-expand text-center'>
                              {hasMultipleSales ? (
                                <button
                                  type='button'
                                  className='btn btn-sm btn-link p-0 text-decoration-none text-dark'
                                  onClick={() => toggleExpandSold(s.groupKey)}
                                  title={
                                    isExpanded
                                      ? 'Collapse sold positions'
                                      : 'Expand sold positions'
                                  }
                                >
                                  {isExpanded ? (
                                    <ChevronDown size={16} />
                                  ) : (
                                    <ChevronRight size={16} />
                                  )}
                                </button>
                              ) : null}
                            </td>
                            <td className='col-sticky-scheme'>
                              <strong>{s.scheme_name || s.symbol}</strong>
                              {hasMultipleSales && (
                                <span className='badge bg-light text-secondary ms-2 border'>
                                  {s.entries.length} sales
                                </span>
                              )}
                            </td>
                            <td>{formatDate(s.invest_date)}</td>
                            <td>
                              <span className='fw-semibold text-primary'>
                                {formatDate(s.sell_date)}
                              </span>
                            </td>
                            <td className='text-end'>{s.years}</td>
                            <td className='text-end'>{s.months}</td>
                            <td className='text-end fw-semibold'>
                              {s.quantity?.toLocaleString()}
                            </td>
                            <td className='text-end'>₹{s.avg_price?.toFixed(2)}</td>
                            <td className='text-end fw-bold'>₹{s.ltp?.toFixed(2)}</td>
                            <td className='text-end'>
                              ₹{s.invested_amount?.toLocaleString()}
                            </td>
                            <td
                              className='text-end text-muted'
                              style={{ fontSize: '0.8rem' }}
                            >
                              ₹{typeof s.buy_charge === 'number' ? s.buy_charge.toFixed(2) : s.buy_charge}
                            </td>
                            <td
                              className='text-end text-muted'
                              style={{ fontSize: '0.8rem' }}
                            >
                              ₹{typeof s.sell_charge === 'number' ? s.sell_charge.toFixed(2) : s.sell_charge}
                            </td>
                            <td className='text-end fw-bold'>
                              ₹{s.current_total?.toLocaleString()}
                            </td>
                            <td className='text-end text-success'>
                              {s.earned > 0
                                ? `+₹${s.earned.toLocaleString()}`
                                : '—'}
                            </td>
                            <td className='text-end text-danger'>
                              {s.loss < 0
                                ? `-₹${Math.abs(s.loss).toLocaleString()}`
                                : '—'}
                            </td>
                            <td className='text-end'>
                              {s.annual_return ? (
                                <span
                                  className={
                                    s.annual_return >= 0
                                      ? 'text-success'
                                      : 'text-danger'
                                  }
                                >
                                  {s.annual_return > 0 ? '+' : ''}
                                  {s.annual_return.toFixed(2)}%
                                </span>
                              ) : (
                                '—'
                              )}
                            </td>
                            <td className='text-end'>
                              <span
                                className={`badge ${isPositive ? 'bg-success' : 'bg-danger'}`}
                                style={{ fontSize: '0.8rem' }}
                              >
                                {isPositive ? '+' : ''}
                                {s.total_return?.toFixed(2)}%
                              </span>
                            </td>
                            {activePortfolio === 'LOAN' && (
                              <td>
                                <span className='badge bg-secondary'>
                                  {s.person || s.app || '—'}
                                </span>
                              </td>
                            )}
                            <td
                              className='text-muted'
                              style={{
                                minWidth: '150px',
                                maxWidth: '240px',
                                whiteSpace: 'normal',
                                wordBreak: 'break-word',
                              }}
                            >
                              {s.sale_remarks || s.remarks || '—'}
                            </td>
                            <td className='text-center'>
                              <button
                                type='button'
                                className='btn btn-sm btn-outline-secondary'
                                title='Notes & Lessons'
                                onClick={() => {
                                  const noteItem = s.entries ? s.entries[0] : s;
                                  onOpenNotes(noteItem);
                                }}
                              >
                                <FileText size={13} />
                              </button>
                            </td>
                          </tr>

                          {/* Expanded Child Sold Positions */}
                          {isExpanded && hasMultipleSales && (
                            <tr className='bg-light'>
                              <td
                                colSpan={activePortfolio === 'LOAN' ? 20 : 19}
                                className='p-3'
                              >
                                <div className='ps-4 border-start border-3 border-secondary'>
                                  <h6
                                    className='fw-bold mb-2 text-secondary'
                                    style={{ fontSize: '0.85rem' }}
                                  >
                                    Individual Sold Positions for{' '}
                                    {s.scheme_name || s.symbol}:
                                  </h6>
                                  <div className='table-responsive'>
                                    <table
                                      className='table table-sm table-bordered bg-white mb-0'
                                      style={{ fontSize: '0.8rem' }}
                                    >
                                      <thead className='table-secondary'>
                                        <tr>
                                          <th>Invest Date</th>
                                          <th>Sell Date</th>
                                          <th
                                            className='text-end'
                                            title='Years held'
                                          >
                                            Y
                                          </th>
                                          <th
                                            className='text-end'
                                            title='Total months held'
                                          >
                                            M
                                          </th>
                                          <th className='text-end'>Quantity</th>
                                          <th className='text-end'>Buy Avg (₹)</th>
                                          <th className='text-end'>Exit Price (₹)</th>
                                          <th className='text-end'>Invested (₹)</th>
                                          <th className='text-end'>Buy Chg</th>
                                          <th className='text-end'>Sell Chg</th>
                                          <th className='text-end'>Exit Total (₹)</th>
                                          <th className='text-end'>Earned (₹)</th>
                                          <th className='text-end'>Loss (₹)</th>
                                          <th className='text-end'>Annual %</th>
                                          <th className='text-end'>Return %</th>
                                          {activePortfolio === 'LOAN' && (
                                            <th>Person</th>
                                          )}
                                          <th>Remarks</th>
                                          <th className='text-center'>Notes</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {s.entries.map((entry) => {
                                          const isEntryPositive =
                                            entry.total_return >= 0;
                                          return (
                                            <tr key={entry.id}>
                                              <td>{formatDate(entry.invest_date)}</td>
                                              <td className='fw-semibold text-primary'>{formatDate(entry.sell_date)}</td>
                                              <td className='text-end'>
                                                {entry.years}
                                              </td>
                                              <td className='text-end'>
                                                {entry.months}
                                              </td>
                                              <td className='text-end fw-semibold'>
                                                {entry.quantity?.toLocaleString()}
                                              </td>
                                              <td className='text-end'>
                                                ₹{entry.avg_price?.toFixed(2)}
                                              </td>
                                              <td className='text-end fw-bold'>
                                                ₹{entry.ltp?.toFixed(2)}
                                              </td>
                                              <td className='text-end'>
                                                ₹{entry.invested_amount?.toLocaleString()}
                                              </td>
                                              <td
                                                className='text-end text-muted'
                                                style={{ fontSize: '0.75rem' }}
                                              >
                                                ₹{typeof entry.buy_charge === 'number' ? entry.buy_charge.toFixed(2) : entry.buy_charge}
                                              </td>
                                              <td
                                                className='text-end text-muted'
                                                style={{ fontSize: '0.75rem' }}
                                              >
                                                ₹{typeof entry.sell_charge === 'number' ? entry.sell_charge.toFixed(2) : entry.sell_charge}
                                              </td>
                                              <td className='text-end fw-bold'>
                                                ₹{entry.current_total?.toLocaleString()}
                                              </td>
                                              <td className='text-end text-success'>
                                                {entry.earned > 0
                                                  ? `+₹${entry.earned.toLocaleString()}`
                                                  : '—'}
                                              </td>
                                              <td className='text-end text-danger'>
                                                {entry.loss < 0
                                                  ? `-₹${Math.abs(entry.loss).toLocaleString()}`
                                                  : '—'}
                                              </td>
                                              <td className='text-end'>
                                                {entry.annual_return ? (
                                                  <span
                                                    className={
                                                      entry.annual_return >= 0
                                                        ? 'text-success'
                                                        : 'text-danger'
                                                    }
                                                  >
                                                    {entry.annual_return > 0
                                                      ? '+'
                                                      : ''}
                                                    {entry.annual_return.toFixed(
                                                      2,
                                                    )}
                                                    %
                                                  </span>
                                                ) : (
                                                  '—'
                                                )}
                                              </td>
                                              <td className='text-end'>
                                                <span
                                                  className={`badge ${isEntryPositive ? 'bg-success' : 'bg-danger'}`}
                                                  style={{ fontSize: '0.75rem' }}
                                                >
                                                  {isEntryPositive ? '+' : ''}
                                                  {entry.total_return?.toFixed(2)}%
                                                </span>
                                              </td>
                                              {activePortfolio === 'LOAN' && (
                                                <td>
                                                  <span className='badge bg-secondary'>
                                                    {entry.person ||
                                                      entry.app ||
                                                      '—'}
                                                  </span>
                                                </td>
                                              )}
                                               <td
                                                 className='text-muted'
                                                 style={{
                                                   minWidth: '150px',
                                                   maxWidth: '240px',
                                                   whiteSpace: 'normal',
                                                   wordBreak: 'break-word',
                                                 }}
                                               >
                                                 {entry.sale_remarks ||
                                                   entry.remarks ||
                                                   '—'}
                                               </td>
                                              <td className='text-center'>
                                                <button
                                                  type='button'
                                                  className='btn btn-sm btn-outline-secondary p-1'
                                                  title='Notes & Lessons'
                                                  onClick={() => onOpenNotes(entry)}
                                                >
                                                  <FileText size={12} />
                                                </button>
                                              </td>
                                            </tr>
                                          );
                                        })}
                                      </tbody>
                                    </table>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })
                  )}
                </tbody>
                {soldHoldings.length > 0 && (
                  <tfoot className='table-secondary fw-bold border-top border-2'>
                    <tr>
                      <td className='col-sticky-expand'></td>
                      <td colSpan={8} className='col-sticky-footer-label'>
                        Total Sold ({filteredGroupedHoldings.length} holdings
                        {searchQuery.trim()
                          ? ` matching "${searchQuery}"`
                          : `, ${soldHoldings.length} trades`}
                        )
                      </td>
                      <td className='text-end'>
                        <span className='text-muted small fw-normal me-1'>
                          Invested:
                        </span>
                        ₹{filteredSoldTotals.invested_amount?.toLocaleString()}
                      </td>
                      <td colSpan={2}></td>
                      <td className='text-end'>
                        <span className='text-muted small fw-normal me-1'>
                          Exit Total:
                        </span>
                        ₹{filteredSoldTotals.current_total?.toLocaleString()}
                      </td>
                      <td className='text-end text-success'>
                        {filteredSoldTotals.earned > 0
                          ? `+₹${filteredSoldTotals.earned?.toLocaleString()}`
                          : '—'}
                      </td>
                      <td className='text-end text-danger'>
                        {filteredSoldTotals.loss < 0
                          ? `-₹${Math.abs(filteredSoldTotals.loss)?.toLocaleString()}`
                          : '—'}
                      </td>
                      <td
                        colSpan={2}
                        className='text-end'
                      >
                        <span
                          className={`badge ${
                            filteredSoldTotals.net_profit >= 0
                              ? 'bg-success'
                              : 'bg-danger'
                          }`}
                        >
                          Net: ₹
                          {filteredSoldTotals.net_profit?.toLocaleString()}
                        </span>
                      </td>
                      <td
                        colSpan={activePortfolio === 'LOAN' ? 3 : 2}
                      ></td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </div>

          <div className='modal-footer py-2 px-3 bg-light d-flex justify-content-between align-items-center'>
            <div className='small text-muted'>
              💡 Click expand icon on holdings with multiple sales to inspect individual trade lots.
            </div>
            <button
              type='button'
              className='btn btn-sm btn-secondary'
              onClick={onClose}
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

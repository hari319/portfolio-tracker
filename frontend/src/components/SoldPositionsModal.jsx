import React, { useRef, useState, useEffect, useMemo } from 'react';
import {
  History,
  ChevronDown,
  ChevronRight,
  FileText,
  Search,
  X,
  Edit3,
  Info,
  CheckCircle2,
} from 'lucide-react';
import * as api from '../api';
import useTickerLookup from '../hooks/useTickerLookup';
import {
  BUY_CHARGE_RATE,
  SELL_CHARGE_RATE,
} from '../constants/portfolioCharges';
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
  onRefresh,
  showToast,
}) {
  const topScrollRef = useRef(null);
  const tableContainerRef = useRef(null);
  const searchInputRef = useRef(null);
  const [scrollWidth, setScrollWidth] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');

  // Edit Sold Position state
  const soldLookup = useTickerLookup();
  const [editSoldTarget, setEditSoldTarget] = useState(null);
  const [editSoldForm, setEditSoldForm] = useState({
    symbol: '',
    stock_name: '',
    scheme_name: '',
    name_confirmed: true,
    person: 'MADI',
    invest_date: '',
    sell_date: '',
    quantity: '',
    avg_price: '',
    sell_price: '',
    invested_amount: '',
    buy_charge: '',
    sell_charge: '',
    remarks: '',
    manual_override_invested: false,
    manual_override_buy_charge: false,
    manual_override_sell_charge: false,
  });

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
    let inv = 0;
    let cur = 0;
    let earned = 0;
    let loss = 0;

    if (!searchQuery.trim() && soldTotals && Object.keys(soldTotals).length > 0) {
      inv = soldTotals.invested_amount || 0;
      cur = soldTotals.current_total || 0;
      earned = soldTotals.earned || 0;
      loss = soldTotals.loss || 0;
    } else {
      for (const g of filteredGroupedHoldings) {
        inv += g.invested_amount || 0;
        cur += g.current_total || 0;
        earned += g.earned || 0;
        loss += g.loss || 0;
      }
    }

    // Net Profit / Realized Profit = Earned total - Loss total
    // Loss is stored as negative in the data model (e.g. -1500.00), so earned + loss equals earned - |loss|
    const netProfit = earned + (loss <= 0 ? loss : -loss);

    return {
      invested_amount: inv,
      current_total: cur,
      earned,
      loss,
      net_profit: Math.round(netProfit * 100) / 100,
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

  const openEditSold = (entry) => {
    const q = entry.sold_quantity ?? entry.quantity ?? '';
    const avg = entry.avg_price ?? '';
    const sp = entry.sell_price ?? entry.ltp ?? '';
    const expectedInv = (parseFloat(q) || 0) * (parseFloat(avg) || 0);
    const storedInv = entry.invested_amount;
    const hasManualInv =
      storedInv !== null &&
      storedInv !== undefined &&
      storedInv !== '' &&
      Math.abs(parseFloat(storedInv) - expectedInv) > 0.01;
    const storedBc = entry.buy_charge;
    const hasManualBc =
      storedBc !== null && storedBc !== undefined && storedBc !== '';
    const storedSc = entry.sell_charge;
    const hasManualSc =
      storedSc !== null && storedSc !== undefined && storedSc !== '';

    const stockNameVal = entry.stock_name || entry.scheme_name || entry.symbol || '';
    const hasValidName = Boolean(
      entry.stock_name &&
      entry.stock_name.trim().toUpperCase() !== (entry.symbol || '').trim().toUpperCase()
    );
    soldLookup.resetLookup(
      hasValidName
        ? { loading: false, found: true, message: `Current: ${stockNameVal}` }
        : { loading: false, found: null, message: '' }
    );

    setEditSoldTarget(entry);
    setEditSoldForm({
      symbol: entry.symbol || '',
      stock_name: stockNameVal,
      scheme_name: entry.scheme_name || entry.symbol || '',
      name_confirmed: Boolean(entry.name_confirmed || hasValidName),
      person: entry.person || 'MADI',
      invest_date: entry.invest_date || new Date().toISOString().slice(0, 10),
      sell_date: entry.sell_date || new Date().toISOString().slice(0, 10),
      quantity: q,
      avg_price: avg,
      sell_price: sp,
      invested_amount:
        storedInv !== null && storedInv !== undefined && storedInv !== ''
          ? storedInv
          : expectedInv > 0
          ? expectedInv.toFixed(2)
          : '',
      buy_charge:
        storedBc !== null && storedBc !== undefined && storedBc !== ''
          ? storedBc
          : '',
      sell_charge:
        storedSc !== null && storedSc !== undefined && storedSc !== ''
          ? storedSc
          : '',
      remarks: entry.sale_remarks || entry.remarks || '',
      manual_override_invested: hasManualInv,
      manual_override_buy_charge: hasManualBc,
      manual_override_sell_charge: hasManualSc,
    });
  };

  const handleEditSoldSubmit = async (e) => {
    e.preventDefault();
    if (!editSoldTarget) return;
    try {
      const q = parseFloat(editSoldForm.quantity);
      const avg = parseFloat(editSoldForm.avg_price);
      const sp = parseFloat(editSoldForm.sell_price);
      if (isNaN(q) || q <= 0 || isNaN(avg) || avg < 0 || isNaN(sp) || sp < 0) {
        if (showToast) showToast('Quantity must be > 0 and prices >= 0.', true);
        return;
      }

      if (soldLookup.lookupStatus.found === false && !editSoldForm.name_confirmed) {
        if (showToast) showToast('Please confirm the stock name before saving.', true);
        return;
      }

      const finalStockName = (editSoldForm.stock_name || editSoldForm.scheme_name || '').trim();
      await api.updatePortfolioSold(editSoldTarget.id, {
        symbol: editSoldForm.symbol.trim().toUpperCase(),
        stock_name: finalStockName,
        scheme_name: finalStockName,
        name_confirmed: Boolean(editSoldForm.name_confirmed),
        person: activePortfolio === 'LOAN' ? editSoldForm.person : null,
        invest_date: editSoldForm.invest_date,
        sell_date: editSoldForm.sell_date,
        quantity: q,
        avg_price: avg,
        sell_price: sp,
        invested_amount:
          editSoldForm.manual_override_invested && editSoldForm.invested_amount !== ''
            ? parseFloat(editSoldForm.invested_amount)
            : null,
        buy_charge:
          editSoldForm.manual_override_buy_charge && editSoldForm.buy_charge !== ''
            ? parseFloat(editSoldForm.buy_charge)
            : null,
        sell_charge:
          editSoldForm.manual_override_sell_charge && editSoldForm.sell_charge !== ''
            ? parseFloat(editSoldForm.sell_charge)
            : null,
        remarks: editSoldForm.remarks.trim(),
      });

      if (showToast) showToast('Sold position updated successfully.');
      setEditSoldTarget(null);
      if (onRefresh) onRefresh();
    } catch (err) {
      if (showToast)
        showToast(err.message || 'Failed to update sold position.', true);
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

          <div
            className='modal-body p-0'
            style={{
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div
              ref={tableContainerRef}
              onScroll={handleTableScroll}
              className='table-responsive'
              style={{
                flex: '1 1 auto',
                maxHeight: 'calc(85vh - 170px)',
                overflow: 'auto',
              }}
            >
              <table className='table table-hover table-striped table-sticky-tfoot align-middle mb-0 text-nowrap'>
                <thead className='table-light'>
                  <tr style={{ fontSize: '0.82rem' }}>
                    <th className='col-sticky-ticker col-sticky-scheme'>StockTicker</th>
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
                        colSpan={activePortfolio === 'LOAN' ? 19 : 18}
                        className='text-center py-4 text-muted'
                      >
                        No sold positions recorded yet for {activePortfolio}.
                      </td>
                    </tr>
                  ) : filteredGroupedHoldings.length === 0 ? (
                    <tr>
                      <td
                        colSpan={activePortfolio === 'LOAN' ? 19 : 18}
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
                          <tr className={hasMultipleSales ? 'multi-entry-row' : ''}>
                            <td className='col-sticky-ticker col-sticky-scheme'>
                              <div className='ticker-cell-content'>
                                <strong title={s.symbol}>{s.symbol || s.scheme_name}</strong>
                                <span
                                  className='stock-info-tooltip-trigger'
                                  tabIndex={0}
                                  title={s.stock_name || s.scheme_name || 'Name not available'}
                                  aria-label={s.stock_name || s.scheme_name || 'Name not available'}
                                >
                                  <Info size={13} className='stock-info-icon' />
                                  <span className='stock-name-tooltip' role='tooltip'>
                                    {s.stock_name || s.scheme_name || 'Name not available'}
                                  </span>
                                </span>
                                {hasMultipleSales && (
                                  <span
                                    className='entry-count-badge'
                                    title={`${s.entries.length} sell entries`}
                                  >
                                    {s.entries.length}
                                  </span>
                                )}
                                {hasMultipleSales && (
                                  <button
                                    type='button'
                                    className='expand-chevron-btn'
                                    onClick={() => toggleExpandSold(s.groupKey)}
                                    title={
                                      isExpanded
                                        ? 'Collapse sell entries'
                                        : 'Expand sell entries'
                                    }
                                  >
                                    {isExpanded ? (
                                      <ChevronDown size={14} />
                                    ) : (
                                      <ChevronRight size={14} />
                                    )}
                                  </button>
                                )}
                              </div>
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
                              <div className='btn-group btn-group-sm'>
                                {!hasMultipleSales && (
                                  <button
                                    type='button'
                                    className='btn btn-outline-primary'
                                    title='Edit Sold Position'
                                    onClick={() =>
                                      openEditSold(s.entries ? s.entries[0] : s)
                                    }
                                  >
                                    <Edit3 size={13} />
                                  </button>
                                )}
                                <button
                                  type='button'
                                  className='btn btn-outline-secondary'
                                  title='Notes & Lessons'
                                  onClick={() => {
                                    const noteItem = s.entries ? s.entries[0] : s;
                                    onOpenNotes(noteItem);
                                  }}
                                >
                                  <FileText size={13} />
                                </button>
                              </div>
                            </td>
                          </tr>

                          {/* Expanded Child Sold Positions */}
                          {isExpanded && hasMultipleSales && s.entries && s.entries.map((entry, idx) => {
                            const isEntryPositive = entry.total_return >= 0;
                            const isLastChild = idx === s.entries.length - 1;
                            return (
                              <tr
                                key={`sold-entry-${entry.id || entry.sale_id || (entry.invest_date + '_' + entry.sell_date + '_' + entry.quantity)}`}
                                className={`multi-entry-child-row ${isLastChild ? 'multi-entry-last-child' : ''}`}
                              >
                                <td
                                  className='col-sticky-ticker col-sticky-scheme col-sticky-ticker-blank col-sticky-scheme-blank'
                                  style={{ backgroundColor: '#ffffff' }}
                                ></td>
                                <td>
                                  <span className='entry-tree-indicator'>
                                    {isLastChild ? '└─' : '├─'}
                                  </span>
                                  {formatDate(entry.invest_date)}
                                </td>
                                <td>
                                  <span className='fw-semibold text-primary'>
                                    {formatDate(entry.sell_date)}
                                  </span>
                                </td>
                                <td className='text-end'>{entry.years}</td>
                                <td className='text-end'>{entry.months}</td>
                                <td className='text-end fw-semibold'>
                                  {entry.quantity?.toLocaleString()}
                                </td>
                                <td className='text-end'>₹{entry.avg_price?.toFixed(2)}</td>
                                <td className='text-end fw-bold'>₹{entry.ltp?.toFixed(2)}</td>
                                <td className='text-end'>
                                  ₹{entry.invested_amount?.toLocaleString()}
                                </td>
                                <td
                                  className='text-end text-muted'
                                  style={{ fontSize: '0.8rem' }}
                                >
                                  ₹{typeof entry.buy_charge === 'number' ? entry.buy_charge.toFixed(2) : entry.buy_charge}
                                </td>
                                <td
                                  className='text-end text-muted'
                                  style={{ fontSize: '0.8rem' }}
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
                                      {entry.annual_return > 0 ? '+' : ''}
                                      {entry.annual_return.toFixed(2)}%
                                    </span>
                                  ) : (
                                    '—'
                                  )}
                                </td>
                                <td className='text-end'>
                                  <span
                                    className={`badge ${isEntryPositive ? 'bg-success' : 'bg-danger'}`}
                                    style={{ fontSize: '0.8rem' }}
                                  >
                                    {isEntryPositive ? '+' : ''}
                                    {entry.total_return?.toFixed(2)}%
                                  </span>
                                </td>
                                {activePortfolio === 'LOAN' && (
                                  <td>
                                    <span className='badge bg-secondary'>
                                      {entry.person || entry.app || '—'}
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
                                  {entry.sale_remarks || entry.remarks || '—'}
                                </td>
                                <td className='text-center'>
                                  <div className='btn-group btn-group-sm'>
                                    <button
                                      type='button'
                                      className='btn btn-outline-primary'
                                      title='Edit Sold Entry'
                                      onClick={() => openEditSold(entry)}
                                    >
                                      <Edit3 size={13} />
                                    </button>
                                    <button
                                      type='button'
                                      className='btn btn-outline-secondary'
                                      title='Notes & Lessons'
                                      onClick={() => onOpenNotes(entry)}
                                    >
                                      <FileText size={13} />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </React.Fragment>
                      );
                    })
                  )}
                </tbody>
                {soldHoldings.length > 0 && (
                  <tfoot className='table-secondary fw-bold border-top border-2'>
                    <tr>
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

      {/* Edit Sold Position Modal */}
      {editSoldTarget && (
        <div
          className='modal-backdrop-custom'
          role='dialog'
          aria-modal='true'
          style={{ zIndex: 1100 }}
        >
          <div className='modal-dialog-custom' style={{ maxWidth: '580px' }}>
            <div className='modal-header-custom'>
              <div>
                <h3 className='modal-title-custom'>Edit Sold Position</h3>
                <p className='modal-subtitle-custom'>
                  {editSoldForm.stock_name || editSoldForm.scheme_name || editSoldForm.symbol}
                  {editSoldForm.symbol ? ` (${editSoldForm.symbol})` : ''}
                </p>
              </div>
              <button
                type='button'
                className='modal-close-btn'
                onClick={() => setEditSoldTarget(null)}
                aria-label='Close modal'
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleEditSoldSubmit} autoComplete='off'>
              <div>
                <div className='p-3 mb-3 bg-light rounded-3 border'>
                  <div className='small fw-bold text-muted mb-2 text-uppercase' style={{ letterSpacing: '0.04em' }}>
                    Position Metadata
                  </div>
                  {activePortfolio === 'LOAN' && (
                    <div className='mb-3'>
                      <label className='form-label-custom'>Person / Account *</label>
                      <div className='d-flex gap-3'>
                        {['MADI', 'BAPA'].map((p) => (
                          <div className='form-check' key={p}>
                            <input
                              className='form-check-input'
                              type='radio'
                              name='editSoldPersonRadio'
                              id={`editSoldPerson_${p}`}
                              value={p}
                              checked={editSoldForm.person === p}
                              onChange={() => setEditSoldForm((prev) => ({ ...prev, person: p }))}
                            />
                            <label className='form-check-label small fw-semibold' htmlFor={`editSoldPerson_${p}`}>
                              {p}
                            </label>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className='mb-2'>
                    <label className='form-label-custom'>StockTicker *</label>
                    <div className='input-group'>
                      <input
                        type='text'
                        className='form-control'
                        placeholder='e.g. TATAGOLD or RELIANCE'
                        value={editSoldForm.symbol}
                        onChange={(e) => {
                          const newSym = e.target.value;
                          setEditSoldForm((prev) => ({
                            ...prev,
                            symbol: newSym,
                            name_confirmed: false,
                          }));
                        }}
                        onBlur={() =>
                          soldLookup.handleLookup(
                            editSoldForm.symbol,
                            (res) => {
                              setEditSoldForm((prev) => ({
                                ...prev,
                                stock_name: res.name || prev.stock_name,
                                scheme_name: res.name || prev.scheme_name,
                                name_confirmed: true,
                              }));
                            },
                            () => {
                              setEditSoldForm((prev) => ({ ...prev, name_confirmed: false }));
                            },
                          )
                        }
                        required
                      />
                      <button
                        type='button'
                        className='btn btn-outline-secondary'
                        onClick={() =>
                          soldLookup.handleLookup(
                            editSoldForm.symbol,
                            (res) => {
                              setEditSoldForm((prev) => ({
                                ...prev,
                                stock_name: res.name || prev.stock_name,
                                scheme_name: res.name || prev.scheme_name,
                                name_confirmed: true,
                              }));
                            },
                            () => {
                              setEditSoldForm((prev) => ({ ...prev, name_confirmed: false }));
                            },
                          )
                        }
                        disabled={soldLookup.lookupStatus.loading}
                      >
                        {soldLookup.lookupStatus.loading ? 'Checking...' : 'Lookup'}
                      </button>
                    </div>
                    {soldLookup.lookupStatus.found === true && (
                      <div className='text-success small mt-1 d-flex align-items-center'>
                        <CheckCircle2 size={13} className='me-1' /> {soldLookup.lookupStatus.message}
                      </div>
                    )}
                    {soldLookup.lookupStatus.found === false && (
                      <div className='alert alert-warning py-1 px-2 small mt-1 mb-0'>
                        ⚠️ {soldLookup.lookupStatus.message}
                      </div>
                    )}
                  </div>
                  <div className='mb-2'>
                    <label className='form-label-custom'>
                      Stock Name{' '}
                      {soldLookup.lookupStatus.found === false ? '*' : '(Auto-fetched from ticker)'}
                    </label>
                    <input
                      type='text'
                      className='form-control'
                      placeholder='Company / Stock Name'
                      value={editSoldForm.stock_name || editSoldForm.scheme_name}
                      onChange={(e) =>
                        setEditSoldForm((prev) => ({
                          ...prev,
                          stock_name: e.target.value,
                          scheme_name: e.target.value,
                        }))
                      }
                      required={soldLookup.lookupStatus.found === false}
                    />
                  </div>
                  {soldLookup.lookupStatus.found === false && (
                    <div className='form-check mb-2'>
                      <input
                        type='checkbox'
                        className='form-check-input'
                        id='confirmManualSoldName'
                        checked={Boolean(editSoldForm.name_confirmed)}
                        onChange={(e) =>
                          setEditSoldForm((prev) => ({
                            ...prev,
                            name_confirmed: e.target.checked,
                          }))
                        }
                        required
                      />
                      <label className='form-check-label small' htmlFor='confirmManualSoldName'>
                        I confirm this stock name is correct (§3 requirement)
                      </label>
                    </div>
                  )}
                </div>

                <div className='small fw-bold text-muted mb-2 text-uppercase' style={{ letterSpacing: '0.04em' }}>
                  Trade & Pricing Details
                </div>

                <div className='row g-2 mb-3'>
                  <div className='col-6'>
                    <label className='form-label-custom'>Invest Date *</label>
                    <input
                      type='date'
                      className='form-control'
                      value={editSoldForm.invest_date}
                      onChange={(e) => setEditSoldForm({ ...editSoldForm, invest_date: e.target.value })}
                      required
                    />
                  </div>
                  <div className='col-6'>
                    <label className='form-label-custom'>Sell Date *</label>
                    <input
                      type='date'
                      className='form-control'
                      value={editSoldForm.sell_date}
                      onChange={(e) => setEditSoldForm({ ...editSoldForm, sell_date: e.target.value })}
                      required
                    />
                  </div>
                </div>

                <div className='row g-2 mb-3'>
                  <div className='col-4'>
                    <label className='form-label-custom'>Quantity *</label>
                    <input
                      type='number'
                      step='any'
                      className='form-control'
                      value={editSoldForm.quantity}
                      onChange={(e) => {
                        const newQ = e.target.value;
                        setEditSoldForm((prev) => {
                          const q = parseFloat(newQ) || 0;
                          const avg = parseFloat(prev.avg_price) || 0;
                          const sp = parseFloat(prev.sell_price) || 0;
                          const inv = prev.manual_override_invested
                            ? prev.invested_amount
                            : q > 0 && avg > 0
                            ? (q * avg).toFixed(2)
                            : '';
                          const bc = prev.manual_override_buy_charge
                            ? prev.buy_charge
                            : inv > 0
                            ? (inv * BUY_CHARGE_RATE).toFixed(2)
                            : '';
                          const sc = prev.manual_override_sell_charge
                            ? prev.sell_charge
                            : q > 0 && sp > 0
                            ? (q * sp * SELL_CHARGE_RATE).toFixed(2)
                            : '';
                          return {
                            ...prev,
                            quantity: newQ,
                            invested_amount: inv,
                            buy_charge: bc,
                            sell_charge: sc,
                          };
                        });
                      }}
                      required
                    />
                  </div>
                  <div className='col-4'>
                    <label className='form-label-custom'>Avg Buy Price (₹) *</label>
                    <input
                      type='number'
                      step='0.01'
                      className='form-control'
                      value={editSoldForm.avg_price}
                      onChange={(e) => {
                        const newAvg = e.target.value;
                        setEditSoldForm((prev) => {
                          const q = parseFloat(prev.quantity) || 0;
                          const avg = parseFloat(newAvg) || 0;
                          const inv = prev.manual_override_invested
                            ? prev.invested_amount
                            : q > 0 && avg > 0
                            ? (q * avg).toFixed(2)
                            : '';
                          const bc = prev.manual_override_buy_charge
                            ? prev.buy_charge
                            : inv > 0
                            ? (inv * BUY_CHARGE_RATE).toFixed(2)
                            : '';
                          return {
                            ...prev,
                            avg_price: newAvg,
                            invested_amount: inv,
                            buy_charge: bc,
                          };
                        });
                      }}
                      required
                    />
                  </div>
                  <div className='col-4'>
                    <label className='form-label-custom'>Sell Price / LTP (₹) *</label>
                    <input
                      type='number'
                      step='0.01'
                      className='form-control'
                      value={editSoldForm.sell_price}
                      onChange={(e) => {
                        const newSp = e.target.value;
                        setEditSoldForm((prev) => {
                          const q = parseFloat(prev.quantity) || 0;
                          const sp = parseFloat(newSp) || 0;
                          const sc = prev.manual_override_sell_charge
                            ? prev.sell_charge
                            : q > 0 && sp > 0
                            ? (q * sp * SELL_CHARGE_RATE).toFixed(2)
                            : '';
                          return {
                            ...prev,
                            sell_price: newSp,
                            sell_charge: sc,
                          };
                        });
                      }}
                      required
                    />
                  </div>
                </div>

                {/* Manual override for Invested Amount */}
                <div className='mb-3'>
                  <div className='d-flex justify-content-between align-items-center mb-1'>
                    <label className='form-label-custom mb-0'>Invested Amount (₹)</label>
                    <div className='form-check form-check-inline m-0'>
                      <input
                        className='form-check-input'
                        type='checkbox'
                        id='soldOverrideInvested'
                        checked={editSoldForm.manual_override_invested}
                        onChange={(e) => {
                          const checked = e.target.checked;
                          setEditSoldForm((prev) => {
                            const q = parseFloat(prev.quantity) || 0;
                            const avg = parseFloat(prev.avg_price) || 0;
                            return {
                              ...prev,
                              manual_override_invested: checked,
                              invested_amount: checked
                                ? prev.invested_amount
                                : q > 0 && avg > 0
                                ? (q * avg).toFixed(2)
                                : '',
                            };
                          });
                        }}
                      />
                      <label className='form-check-label small text-muted' htmlFor='soldOverrideInvested'>
                        Manual cost basis override
                      </label>
                    </div>
                  </div>
                  <input
                    type='number'
                    step='0.01'
                    className='form-control'
                    value={editSoldForm.invested_amount}
                    disabled={!editSoldForm.manual_override_invested}
                    onChange={(e) =>
                      setEditSoldForm({ ...editSoldForm, invested_amount: e.target.value })
                    }
                  />
                </div>

                {/* Manual overrides for Buy & Sell charges */}
                <div className='row g-2 mb-3'>
                  <div className='col-6'>
                    <div className='d-flex justify-content-between align-items-center mb-1'>
                      <label className='form-label-custom mb-0'>Buy Chg (₹)</label>
                      <div className='form-check form-check-inline m-0'>
                        <input
                          className='form-check-input'
                          type='checkbox'
                          id='soldOverrideBuyChg'
                          checked={editSoldForm.manual_override_buy_charge}
                          onChange={(e) => {
                            const checked = e.target.checked;
                            setEditSoldForm((prev) => {
                              const inv =
                                parseFloat(prev.invested_amount) ||
                                (parseFloat(prev.quantity) || 0) * (parseFloat(prev.avg_price) || 0);
                              return {
                                ...prev,
                                manual_override_buy_charge: checked,
                                buy_charge: checked
                                  ? prev.buy_charge
                                  : inv > 0
                                  ? (inv * BUY_CHARGE_RATE).toFixed(2)
                                  : '',
                              };
                            });
                          }}
                        />
                        <label className='form-check-label small text-muted' htmlFor='soldOverrideBuyChg'>
                          Override
                        </label>
                      </div>
                    </div>
                    <input
                      type='number'
                      step='0.01'
                      className='form-control'
                      value={editSoldForm.buy_charge}
                      disabled={!editSoldForm.manual_override_buy_charge}
                      onChange={(e) => setEditSoldForm({ ...editSoldForm, buy_charge: e.target.value })}
                    />
                  </div>
                  <div className='col-6'>
                    <div className='d-flex justify-content-between align-items-center mb-1'>
                      <label className='form-label-custom mb-0'>Sell Chg (₹)</label>
                      <div className='form-check form-check-inline m-0'>
                        <input
                          className='form-check-input'
                          type='checkbox'
                          id='soldOverrideSellChg'
                          checked={editSoldForm.manual_override_sell_charge}
                          onChange={(e) => {
                            const checked = e.target.checked;
                            setEditSoldForm((prev) => {
                              const q = parseFloat(prev.quantity) || 0;
                              const sp = parseFloat(prev.sell_price) || 0;
                              return {
                                ...prev,
                                manual_override_sell_charge: checked,
                                sell_charge: checked
                                  ? prev.sell_charge
                                  : q > 0 && sp > 0
                                  ? (q * sp * SELL_CHARGE_RATE).toFixed(2)
                                  : '',
                              };
                            });
                          }}
                        />
                        <label className='form-check-label small text-muted' htmlFor='soldOverrideSellChg'>
                          Override
                        </label>
                      </div>
                    </div>
                    <input
                      type='number'
                      step='0.01'
                      className='form-control'
                      value={editSoldForm.sell_charge}
                      disabled={!editSoldForm.manual_override_sell_charge}
                      onChange={(e) => setEditSoldForm({ ...editSoldForm, sell_charge: e.target.value })}
                    />
                  </div>
                </div>

                <div className='mb-3'>
                  <label className='form-label-custom'>Remarks</label>
                  <input
                    type='text'
                    className='form-control'
                    placeholder='e.g. Stop loss hit, Target reached'
                    value={editSoldForm.remarks}
                    onChange={(e) => setEditSoldForm({ ...editSoldForm, remarks: e.target.value })}
                  />
                </div>
              </div>
              <div className='modal-footer-custom'>
                <button
                  type='button'
                  className='btn btn-outline-secondary'
                  onClick={() => setEditSoldTarget(null)}
                >
                  Cancel
                </button>
                <button type='submit' className='btn btn-primary px-4'>
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

import React, { useState, useEffect, useMemo } from 'react';
import { X, CheckCircle2, AlertCircle, Plus, Search, Loader2 } from 'lucide-react';
import * as api from '../api';
import { parseRangeOrNumber, calculateDistancePct } from '../utils/swingCalculations';

export default function SwingTradeModal({
  isOpen,
  onClose,
  onSubmit,
  isEditMode = false,
  editItem = null,
  sources = [],
  onSourceAdded,
  showToast,
}) {
  const [symbol, setSymbol] = useState('');
  const [tradeDate, setTradeDate] = useState(new Date().toISOString().slice(0, 10));
  const [currentPrice, setCurrentPrice] = useState('');
  const [buyZone, setBuyZone] = useState('');
  const [stopLoss, setStopLoss] = useState('');
  const [target1, setTarget1] = useState('');
  const [target2, setTarget2] = useState('');
  const [patternBreak, setPatternBreak] = useState('');
  const [thesis, setThesis] = useState('');
  const [tradeSource, setTradeSource] = useState('');

  // Ticker lookup state
  const [isLookingUp, setIsLookingUp] = useState(false);
  const [lookupResult, setLookupResult] = useState(null); // { ok: bool, message: str, source: str }

  // New trade source inline addition state
  const [isAddingNewSource, setIsAddingNewSource] = useState(false);
  const [newSourceName, setNewSourceName] = useState('');
  const [isSavingSource, setIsSavingSource] = useState(false);

  // Submitting state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  // Initialize form when opened or editItem changes
  useEffect(() => {
    if (!isOpen) {
      setSymbol('');
      setTradeDate(new Date().toISOString().slice(0, 10));
      setCurrentPrice('');
      setBuyZone('');
      setStopLoss('');
      setTarget1('');
      setTarget2('');
      setPatternBreak('');
      setThesis('');
      setTradeSource('');
      setLookupResult(null);
      setIsAddingNewSource(false);
      setNewSourceName('');
      setFormError('');
      return;
    }

    if (isEditMode && editItem) {
      setSymbol(editItem.symbol || '');
      setTradeDate(editItem.date || new Date().toISOString().slice(0, 10));
      setCurrentPrice(
        editItem.current_price !== null && editItem.current_price !== undefined
          ? String(editItem.current_price)
          : ''
      );
      setBuyZone(editItem.buy_zone || '');
      setStopLoss(editItem.stop_loss || '');
      setTarget1(editItem.target1 || '');
      setTarget2(editItem.target2 || '');
      setPatternBreak(editItem.pattern_break || '');
      setThesis(editItem.thesis || '');
      setTradeSource(editItem.trade_source || '');
      setLookupResult(null);
      setIsAddingNewSource(false);
      setFormError('');
    } else {
      setSymbol('');
      setTradeDate(new Date().toISOString().slice(0, 10));
      setCurrentPrice('');
      setBuyZone('');
      setStopLoss('');
      setTarget1('');
      setTarget2('');
      setPatternBreak('');
      setThesis('');
      setTradeSource(sources.length > 0 ? sources[0] : '');
      setLookupResult(null);
      setIsAddingNewSource(false);
      setFormError('');
    }
  }, [isOpen, isEditMode, editItem, sources]);

  // Real-time helper calculations for display in form
  const buyZonePct = useMemo(() => calculateDistancePct(currentPrice, buyZone), [currentPrice, buyZone]);
  const slPct = useMemo(() => calculateDistancePct(currentPrice, stopLoss), [currentPrice, stopLoss]);
  const target1Pct = useMemo(() => calculateDistancePct(currentPrice, target1), [currentPrice, target1]);
  const target2Pct = useMemo(() => calculateDistancePct(currentPrice, target2), [currentPrice, target2]);

  if (!isOpen) return null;

  // Handle ticker lookup (checks Portfolio table first, then fetches quote)
  const handleTickerLookup = async (symToLookup) => {
    const raw = (symToLookup || symbol).trim();
    if (!raw) return;

    setIsLookingUp(true);
    setLookupResult(null);

    try {
      const res = await api.lookupSwingTicker(raw);
      if (res && res.ok) {
        setSymbol(res.symbol);
        if (res.price !== undefined && res.price !== null) {
          setCurrentPrice(String(res.price));
        }
        setLookupResult({
          ok: true,
          message: res.message || `Price: ₹${res.price}`,
          source: res.source,
        });
      } else {
        setLookupResult({
          ok: false,
          message: res.error || 'Ticker not found.',
        });
      }
    } catch (err) {
      setLookupResult({
        ok: false,
        message: err.message || 'Error checking ticker price.',
      });
    } finally {
      setIsLookingUp(false);
    }
  };

  // Create new source on the fly and persist it
  const handleCreateSource = async (e) => {
    if (e) e.preventDefault();
    const clean = newSourceName.trim();
    if (!clean) return;

    setIsSavingSource(true);
    try {
      const res = await api.addSwingSource(clean);
      if (res && res.ok) {
        if (onSourceAdded) {
          onSourceAdded(res.sources || []);
        }
        setTradeSource(clean);
        setIsAddingNewSource(false);
        setNewSourceName('');
        if (showToast) showToast(`Trade source "${clean}" saved!`, false);
      }
    } catch (err) {
      if (showToast) showToast(err.message || 'Failed to add source', true);
    } finally {
      setIsSavingSource(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const cleanSymbol = symbol.trim();
    if (!cleanSymbol) {
      setFormError('Ticker symbol is required.');
      return;
    }

    setIsSubmitting(true);
    setFormError('');

    try {
      const payload = {
        symbol: cleanSymbol,
        date: tradeDate,
        current_price: currentPrice.trim() !== '' ? parseFloat(currentPrice) : null,
        buy_zone: buyZone.trim(),
        stop_loss: stopLoss.trim(),
        target1: target1.trim(),
        target2: target2.trim(),
        pattern_break: patternBreak.trim(),
        thesis: thesis, // preserve whitespace & newlines
        trade_source: tradeSource.trim(),
      };

      await onSubmit(payload, isEditMode ? editItem?.id : null);
      onClose();
    } catch (err) {
      setFormError(err.message || 'Failed to save swing trade.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="modal show d-block"
      tabIndex="-1"
      style={{ backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 1055 }}
      role="dialog"
      aria-modal="true"
    >
      <div className="modal-dialog modal-lg modal-dialog-scrollable">
        <div className="modal-content shadow-lg border-0">
          <form onSubmit={handleSubmit}>
            {/* Modal Header */}
            <div className="modal-header border-bottom px-4 py-3 bg-light">
              <h5 className="modal-title fw-bold text-dark mb-0">
                {isEditMode ? `Edit Swing Trade — ${editItem?.symbol || ''}` : 'Add New Swing Trade'}
              </h5>
              <button
                type="button"
                className="btn-close"
                onClick={onClose}
                aria-label="Close"
                disabled={isSubmitting}
              />
            </div>

            {/* Modal Body */}
            <div className="modal-body p-4">
              {formError && (
                <div className="alert alert-danger py-2 px-3 small mb-3 d-flex align-items-center gap-2">
                  <AlertCircle size={16} />
                  <span>{formError}</span>
                </div>
              )}

              {/* Row 1: Ticker & Date */}
              <div className="row g-3 mb-3">
                <div className="col-12 col-md-7">
                  <label className="form-label small fw-semibold text-dark mb-1">
                    Ticker / Symbol <span className="text-danger">*</span>
                  </label>
                  <div className="input-group">
                    <input
                      type="text"
                      className="form-control"
                      placeholder="e.g. TATAMOTORS, RELIANCE, CARTRADE.NS"
                      value={symbol}
                      onChange={(e) => {
                        setSymbol(e.target.value);
                        setLookupResult(null);
                      }}
                      onBlur={() => {
                        if (symbol.trim() && (!currentPrice || lookupResult === null)) {
                          handleTickerLookup(symbol);
                        }
                      }}
                      required
                      autoFocus={!isEditMode}
                    />
                    <button
                      type="button"
                      className="btn btn-outline-secondary d-inline-flex align-items-center gap-1"
                      onClick={() => handleTickerLookup(symbol)}
                      disabled={isLookingUp || !symbol.trim()}
                    >
                      {isLookingUp ? (
                        <>
                          <Loader2 size={14} className="spin-anim" />
                          <span>Checking...</span>
                        </>
                      ) : (
                        <>
                          <Search size={14} />
                          <span>Lookup</span>
                        </>
                      )}
                    </button>
                  </div>

                  {lookupResult && lookupResult.ok && (
                    <div className="small mt-1 text-success d-flex align-items-center gap-1">
                      <CheckCircle2 size={13} />
                      <span>{lookupResult.message}</span>
                      {lookupResult.source === 'portfolio' && (
                        <span className="badge bg-primary-subtle text-primary border border-primary-subtle ms-1">
                          Reused from Portfolio
                        </span>
                      )}
                    </div>
                  )}
                  {lookupResult && !lookupResult.ok && (
                    <div className="small mt-1 text-danger d-flex align-items-center gap-1">
                      <AlertCircle size={13} />
                      <span>{lookupResult.message}</span>
                    </div>
                  )}
                </div>

                <div className="col-12 col-md-5">
                  <label className="form-label small fw-semibold text-dark mb-1">
                    Date <span className="text-danger">*</span>
                  </label>
                  <input
                    type="date"
                    className="form-control"
                    value={tradeDate}
                    onChange={(e) => setTradeDate(e.target.value)}
                    required
                  />
                  <div className="form-text text-muted" style={{ fontSize: '0.78rem' }}>
                    Entry or setup date
                  </div>
                </div>
              </div>

              {/* Row 2: Current Price & Trade Source */}
              <div className="row g-3 mb-3">
                <div className="col-12 col-md-6">
                  <label className="form-label small fw-semibold text-dark mb-1">
                    Current Price (₹)
                  </label>
                  <input
                    type="number"
                    step="any"
                    className="form-control"
                    placeholder="Auto-populated on lookup or enter manually"
                    value={currentPrice}
                    onChange={(e) => setCurrentPrice(e.target.value)}
                  />
                  <div className="form-text text-muted" style={{ fontSize: '0.78rem' }}>
                    Reuses Portfolio table price first; auto-refreshes daily at 9:30.
                  </div>
                </div>

                <div className="col-12 col-md-6">
                  <label className="form-label small fw-semibold text-dark mb-1">
                    Trade Source
                  </label>
                  {!isAddingNewSource ? (
                    <div className="input-group">
                      <select
                        className="form-select"
                        value={tradeSource}
                        onChange={(e) => {
                          if (e.target.value === '__add_new__') {
                            setIsAddingNewSource(true);
                          } else {
                            setTradeSource(e.target.value);
                          }
                        }}
                      >
                        <option value="">-- Select Trade Source --</option>
                        {sources.map((src) => (
                          <option key={src} value={src}>
                            {src}
                          </option>
                        ))}
                        <option value="__add_new__">+ Add New Source...</option>
                      </select>
                      <button
                        type="button"
                        className="btn btn-outline-secondary"
                        onClick={() => setIsAddingNewSource(true)}
                        title="Add a new Trade Source option"
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                  ) : (
                    <div className="input-group">
                      <input
                        type="text"
                        className="form-control"
                        placeholder="Enter new source name..."
                        value={newSourceName}
                        onChange={(e) => setNewSourceName(e.target.value)}
                        autoFocus
                      />
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={handleCreateSource}
                        disabled={isSavingSource || !newSourceName.trim()}
                      >
                        {isSavingSource ? 'Saving...' : 'Save Source'}
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-secondary btn-sm"
                        onClick={() => {
                          setIsAddingNewSource(false);
                          setNewSourceName('');
                        }}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  )}
                  <div className="form-text text-muted" style={{ fontSize: '0.78rem' }}>
                    Who provided or recommended this trade setup (persisted for future rows).
                  </div>
                </div>
              </div>

              {/* Row 3: Buy Zone & Stop Loss (SL) */}
              <div className="row g-3 mb-3">
                <div className="col-12 col-md-6">
                  <label className="form-label small fw-semibold text-dark mb-1">
                    Buy Zone
                  </label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Single value (e.g. 100) or range (e.g. 100-105)"
                    value={buyZone}
                    onChange={(e) => setBuyZone(e.target.value)}
                  />
                  {buyZone && (
                    <div className="small mt-1 text-muted d-flex align-items-center gap-2">
                      <span>Avg: {parseRangeOrNumber(buyZone).avg ?? '—'}</span>
                      {buyZonePct !== null && (
                        <span className={`badge ${buyZonePct >= 0 ? 'bg-primary-subtle text-primary' : 'bg-secondary-subtle text-secondary'}`}>
                          {buyZonePct >= 0 ? `+${buyZonePct}%` : `${buyZonePct}%`} from current
                        </span>
                      )}
                    </div>
                  )}
                </div>

                <div className="col-12 col-md-6">
                  <label className="form-label small fw-semibold text-dark mb-1">
                    Stop Loss (SL)
                  </label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Single value (e.g. 95) or range (e.g. 92-95)"
                    value={stopLoss}
                    onChange={(e) => setStopLoss(e.target.value)}
                  />
                  {stopLoss && (
                    <div className="small mt-1 text-muted d-flex align-items-center gap-2">
                      <span>Avg: {parseRangeOrNumber(stopLoss).avg ?? '—'}</span>
                      {slPct !== null && (
                        <span className={`badge ${slPct < 0 ? 'bg-danger-subtle text-danger' : 'bg-warning-subtle text-warning'}`}>
                          {slPct >= 0 ? `+${slPct}%` : `${slPct}%`} from current
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Row 4: Target 1 & Target 2 */}
              <div className="row g-3 mb-3">
                <div className="col-12 col-md-6">
                  <label className="form-label small fw-semibold text-dark mb-1">
                    Target 1
                  </label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Single value (e.g. 115) or range (e.g. 110-120)"
                    value={target1}
                    onChange={(e) => setTarget1(e.target.value)}
                  />
                  {target1 && (
                    <div className="small mt-1 text-muted d-flex align-items-center gap-2">
                      <span>Avg: {parseRangeOrNumber(target1).avg ?? '—'}</span>
                      {target1Pct !== null && (
                        <span className="badge bg-success-subtle text-success">
                          {target1Pct >= 0 ? `+${target1Pct}%` : `${target1Pct}%`} from current
                        </span>
                      )}
                    </div>
                  )}
                </div>

                <div className="col-12 col-md-6">
                  <label className="form-label small fw-semibold text-dark mb-1">
                    Target 2
                  </label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Single value (e.g. 130) or range (e.g. 125-135)"
                    value={target2}
                    onChange={(e) => setTarget2(e.target.value)}
                  />
                  {target2 && (
                    <div className="small mt-1 text-muted d-flex align-items-center gap-2">
                      <span>Avg: {parseRangeOrNumber(target2).avg ?? '—'}</span>
                      {target2Pct !== null && (
                        <span className="badge bg-success-subtle text-success">
                          {target2Pct >= 0 ? `+${target2Pct}%` : `${target2Pct}%`} from current
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Row 5: Pattern Break */}
              <div className="mb-3">
                <label className="form-label small fw-semibold text-dark mb-1">
                  Pattern Break
                </label>
                <input
                  type="text"
                  className="form-control"
                  placeholder="e.g. Ascending Triangle Breakout, Cup and Handle, 20 EMA bounce"
                  value={patternBreak}
                  onChange={(e) => setPatternBreak(e.target.value)}
                />
              </div>

              {/* Row 6: Thesis (Free text, preserving formatting) */}
              <div className="mb-2">
                <label className="form-label small fw-semibold text-dark mb-1">
                  Thesis
                </label>
                <textarea
                  className="form-control"
                  rows={3}
                  placeholder="Enter detailed trade thesis, reasons, volume behavior, or notes (formatting and line breaks are preserved)..."
                  value={thesis}
                  onChange={(e) => setThesis(e.target.value)}
                />
                <div className="form-text text-muted" style={{ fontSize: '0.78rem' }}>
                  Multi-line text, paragraphs, and indentation are saved and rendered with formatting intact.
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="modal-footer px-4 py-3 bg-light border-top d-flex justify-content-between">
              <button
                type="button"
                className="btn btn-secondary px-3"
                onClick={onClose}
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary px-4 fw-medium d-inline-flex align-items-center gap-1"
                disabled={isSubmitting || !symbol.trim()}
              >
                {isSubmitting ? (
                  <>
                    <Loader2 size={15} className="spin-anim" />
                    <span>Saving...</span>
                  </>
                ) : (
                  <span>{isEditMode ? 'Update Trade' : 'Save Trade'}</span>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

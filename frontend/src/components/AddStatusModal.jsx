import React, { useState, useEffect } from 'react';
import { X, Search, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';
import * as api from '../api';
import { formatDate } from '../utils/date';


export default function AddStatusModal({
  isOpen,
  onClose,
  onSubmit,
  isSubmitting = false,
  isEditMode = false,
  editItem = null,
}) {
  const [symbol, setSymbol] = useState('');
  const [stockName, setStockName] = useState('');
  const [priceOfAnalysis, setPriceOfAnalysis] = useState('');
  const [currency, setCurrency] = useState('INR');
  const [isFetchingQuote, setIsFetchingQuote] = useState(false);
  const [fetchSuccess, setFetchSuccess] = useState(false);
  const [fetchError, setFetchError] = useState('');

  // Scenario targets: [targetPrice, targetCagr]
  const [baseTarget, setBaseTarget] = useState('');
  const [baseCagr, setBaseCagr] = useState('');
  const [bullTarget, setBullTarget] = useState('');
  const [bullCagr, setBullCagr] = useState('');
  const [bearTarget, setBearTarget] = useState('');
  const [bearCagr, setBearCagr] = useState('');

  // Remarks
  const [remarks, setRemarks] = useState('');

  // Best Entry & Status
  const [bestEntry, setBestEntry] = useState('');
  const [status, setStatus] = useState('');

  // Edit switch: 'existing' | 'new'
  const [editModeType, setEditModeType] = useState('existing');

  // Reset or Populate form when modal opens
  useEffect(() => {
    if (!isOpen) {
      setSymbol('');
      setStockName('');
      setPriceOfAnalysis('');
      setCurrency('INR');
      setFetchSuccess(false);
      setFetchError('');
      setBaseTarget('');
      setBaseCagr('');
      setBullTarget('');
      setBullCagr('');
      setBearTarget('');
      setBearCagr('');
      setRemarks('');
      setBestEntry('');
      setStatus('');
      setEditModeType('existing');
      return;
    }

    if (isEditMode && editItem) {
      setSymbol(editItem.symbol || '');
      setStockName(editItem.name || '');
      setPriceOfAnalysis(editItem.price_of_analysis !== undefined ? editItem.price_of_analysis : '');
      setCurrency(editItem.currency || 'INR');
      setFetchSuccess(true);
      setFetchError('');

      const base = editItem.base || ['', ''];
      const bull = editItem.bull || ['', ''];
      const bear = editItem.bear || ['', ''];

      setBaseTarget(base[0] || '');
      setBaseCagr(base[1] || '');
      setBullTarget(bull[0] || '');
      setBullCagr(bull[1] || '');
      setBearTarget(bear[0] || '');
      setBearCagr(bear[1] || '');
      setRemarks(editItem.remarks || '');
      setBestEntry(editItem.best_entry !== undefined && editItem.best_entry !== null ? editItem.best_entry : '');
      setStatus(editItem.status || '');
      setEditModeType('existing');
    }
  }, [isOpen, isEditMode, editItem]);

  if (!isOpen) return null;

  const handleSymbolChange = (e) => {
    setSymbol(e.target.value);
    setFetchSuccess(false);
    setFetchError('');
  };

  const fetchLivePriceForSymbol = async (targetSymbol) => {
    const clean = (targetSymbol || symbol).trim();
    if (!clean) {
      setFetchError('Please enter a ticker symbol.');
      return false;
    }

    setIsFetchingQuote(true);
    setFetchError('');
    try {
      const res = await api.fetchStockInfo(clean);
      if (res && res.ok) {
        setSymbol(res.symbol || clean);
        setStockName(res.name || '');
        setPriceOfAnalysis(res.price !== undefined ? res.price : '');
        setCurrency(res.currency || 'INR');
        setFetchSuccess(true);
        return true;
      } else {
        setFetchError(res.error || 'Failed to fetch quote.');
        setFetchSuccess(false);
        return false;
      }
    } catch (err) {
      setFetchError(err.message || 'Error fetching stock data.');
      setFetchSuccess(false);
      return false;
    } finally {
      setIsFetchingQuote(false);
    }
  };

  const handleSwitchMode = async (mode) => {
    setEditModeType(mode);
    setFetchError('');

    if (mode === 'new') {
      // Fetch fresh live price for new history entry
      await fetchLivePriceForSymbol(symbol);
    } else if (mode === 'existing' && editItem) {
      // Revert to original price of analysis
      setPriceOfAnalysis(editItem.price_of_analysis !== undefined ? editItem.price_of_analysis : '');
      setFetchSuccess(true);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    // If in new history mode or initial add mode, ensure we have a fetched price
    if (!fetchSuccess && (!isEditMode || editModeType === 'new')) {
      const ok = await fetchLivePriceForSymbol(symbol);
      if (!ok) return;
    }

    const payload = {
      symbol: symbol.trim(),
      name: stockName.trim(),
      price_of_analysis: priceOfAnalysis,
      best_entry: bestEntry !== '' ? Number(bestEntry) : null,
      status: status.trim(),
      currency: currency,
      base: [baseTarget.trim(), baseCagr.trim()],
      bull: [bullTarget.trim(), bullCagr.trim()],
      bear: [bearTarget.trim(), bearCagr.trim()],
      remarks: remarks.trim(),
    };

    if (isEditMode) {
      if (editModeType === 'existing') {
        payload.date_of_analysis = editItem.date_of_analysis;
        await onSubmit(payload, 'edit_existing', editItem.id);
      } else {
        // New history entry gets today's date
        await onSubmit(payload, 'edit_new', editItem.id);
      }
    } else {
      await onSubmit(payload, 'add');
    }
  };

  return (
    <div className="modal-backdrop-custom" role="dialog" aria-modal="true">
      <div className="modal-dialog-custom">
        {/* Modal Header */}
        <div className="modal-header-custom">
          <div>
            <h3 className="modal-title-custom">
              {isEditMode
                ? editModeType === 'new'
                  ? 'Add New History Record'
                  : `Edit Stock Status (${symbol})`
                : 'Add Stock Status'}
            </h3>
            <p className="modal-subtitle-custom">
              {isEditMode
                ? editModeType === 'new'
                  ? 'Record a new analysis date and scenarios for this ticker.'
                  : 'Update targets and remarks for the existing analysis.'
                : 'Record analysis scenarios (Base, Bull, Bear) for stock monitoring.'}
            </p>
          </div>
          <button
            type="button"
            className="modal-close-btn"
            onClick={onClose}
            aria-label="Close modal"
            disabled={isSubmitting}
          >
            <X size={18} />
          </button>
        </div>

        {/* Switch on top: ONLY shown for edit version of row */}
        {isEditMode && (
          <div className="modal-top-switch-wrap mb-3">
            <div className="btn-group w-100 switch-toggle-group" role="group">
              <button
                type="button"
                className={`btn btn-sm ${editModeType === 'existing' ? 'btn-primary' : 'btn-outline-secondary'}`}
                onClick={() => handleSwitchMode('existing')}
                disabled={isSubmitting || isFetchingQuote}
              >
                Existing
              </button>
              <button
                type="button"
                className={`btn btn-sm ${editModeType === 'new' ? 'btn-primary' : 'btn-outline-secondary'}`}
                onClick={() => handleSwitchMode('new')}
                disabled={isSubmitting || isFetchingQuote}
              >
                New (History)
              </button>
            </div>
            <p className="switch-hint mt-1">
              {editModeType === 'existing'
                ? 'ℹ️ Editing targets for the existing analysis date.'
                : '✨ Creates a new history analysis with live price and current date.'}
            </p>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} autoComplete="off">
          {/* Ticker Input & Fetch Button Side by Side */}
          <div className="mb-3">
            <label className="form-label-custom">Ticker</label>
            <div className="input-group">
              <input
                type="text"
                className={`form-control ${isEditMode ? 'bg-light' : ''}`}
                placeholder="e.g. INFY, TATAMOTORS, RELIANCE"
                value={symbol}
                onChange={handleSymbolChange}
                disabled={isSubmitting || isFetchingQuote || isEditMode}
                required
              />
              {!isEditMode && (
                <button
                  type="button"
                  className="btn btn-primary d-inline-flex align-items-center gap-1"
                  onClick={() => fetchLivePriceForSymbol(symbol)}
                  disabled={isSubmitting || isFetchingQuote || !symbol.trim()}
                >
                  <Search size={15} />
                  <span>{isFetchingQuote ? 'Fetching...' : 'Fetch'}</span>
                </button>
              )}
            </div>

            {/* Fetch feedback */}
            {fetchSuccess && (
              <div className="fetch-feedback-success mt-2">
                <CheckCircle size={14} className="text-success" />
                <span>
                  <strong>{stockName || symbol}</strong> — Live Price: <strong>{currency} {priceOfAnalysis}</strong>
                </span>
              </div>
            )}
            {fetchError && (
              <div className="fetch-feedback-error mt-2">
                <AlertCircle size={14} className="text-danger" />
                <span>{fetchError}</span>
              </div>
            )}
          </div>

          {/* Price of Analysis (Disabled / Read-only) */}
          <div className="mb-3">
            <div className="d-flex justify-content-between align-items-center mb-1">
              <label className="form-label-custom mb-0">
                Price of Analysis{' '}
                <span className="text-muted fw-normal">
                  {isEditMode && editModeType === 'existing'
                    ? `(Fixed from analysis on ${formatDate(editItem?.date_of_analysis) || 'record'})`
                    : '(Auto-filled from Live Fetch)'}

                </span>
              </label>
              {isEditMode && editModeType === 'new' && (
                <button
                  type="button"
                  className="btn btn-link btn-sm p-0 text-decoration-none d-inline-flex align-items-center gap-1"
                  onClick={() => fetchLivePriceForSymbol(symbol)}
                  disabled={isSubmitting || isFetchingQuote}
                >
                  <RefreshCw size={12} className={isFetchingQuote ? 'spin-anim' : ''} />
                  <span>Re-fetch live price</span>
                </button>
              )}
            </div>
            <input
              type="text"
              className="form-control bg-light"
              placeholder="Click 'Fetch' above to retrieve current price"
              value={priceOfAnalysis ? `${currency} ${priceOfAnalysis}` : ''}
              disabled
              readOnly
            />
          </div>

          {/* Best Entry & Status */}
          <div className="row g-2 mb-3">
            <div className="col-6">
              <label className="form-label-custom">Best Entry</label>
              <div className="input-group">
                <span className="input-group-text bg-light text-muted">₹</span>
                <input
                  type="number"
                  step="any"
                  className="form-control"
                  placeholder="e.g. 1500"
                  value={bestEntry}
                  onChange={(e) => setBestEntry(e.target.value)}
                  disabled={isSubmitting}
                />
              </div>
            </div>
            <div className="col-6">
              <label className="form-label-custom">Status</label>
              <select
                className="form-select"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                disabled={isSubmitting}
              >
                <option value="">Select Status...</option>
                <option value="Buy">Buy</option>
                <option value="Avoid">Avoid</option>
                <option value="Hold">Hold</option>
                <option value="Acc on dip">Acc on dip</option>
              </select>
            </div>
          </div>

          {/* Base: Target Price & Target CAGR */}
          <div className="mb-3">
            <label className="form-label-custom">Base Scenario</label>
            <div className="row g-2">
              <div className="col-6">
                <div className="input-group input-group-sm">
                  <span className="input-group-text bg-light text-muted">₹</span>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Target Price"
                    value={baseTarget}
                    onChange={(e) => setBaseTarget(e.target.value)}
                    disabled={isSubmitting}
                  />
                </div>
              </div>
              <div className="col-6">
                <div className="input-group input-group-sm">
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Target CAGR"
                    value={baseCagr}
                    onChange={(e) => setBaseCagr(e.target.value)}
                    disabled={isSubmitting}
                  />
                  <span className="input-group-text bg-light text-muted">%</span>
                </div>
              </div>
            </div>
          </div>

          {/* Bull: Target Price & Target CAGR */}
          <div className="mb-3">
            <label className="form-label-custom">Bull Scenario</label>
            <div className="row g-2">
              <div className="col-6">
                <div className="input-group input-group-sm">
                  <span className="input-group-text bg-light text-muted">₹</span>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Target Price"
                    value={bullTarget}
                    onChange={(e) => setBullTarget(e.target.value)}
                    disabled={isSubmitting}
                  />
                </div>
              </div>
              <div className="col-6">
                <div className="input-group input-group-sm">
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Target CAGR"
                    value={bullCagr}
                    onChange={(e) => setBullCagr(e.target.value)}
                    disabled={isSubmitting}
                  />
                  <span className="input-group-text bg-light text-muted">%</span>
                </div>
              </div>
            </div>
          </div>

          {/* Bear: Target Price & Target CAGR */}
          <div className="mb-3">
            <label className="form-label-custom">Bear Scenario</label>
            <div className="row g-2">
              <div className="col-6">
                <div className="input-group input-group-sm">
                  <span className="input-group-text bg-light text-muted">₹</span>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Target Price"
                    value={bearTarget}
                    onChange={(e) => setBearTarget(e.target.value)}
                    disabled={isSubmitting}
                  />
                </div>
              </div>
              <div className="col-6">
                <div className="input-group input-group-sm">
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Target CAGR"
                    value={bearCagr}
                    onChange={(e) => setBearCagr(e.target.value)}
                    disabled={isSubmitting}
                  />
                  <span className="input-group-text bg-light text-muted">%</span>
                </div>
              </div>
            </div>
          </div>

          {/* Remarks input text field */}
          <div className="mb-4">
            <label className="form-label-custom">Remarks</label>
            <textarea
              className="form-control"
              rows={2}
              placeholder="Enter analysis notes, triggers, catalyst or stoploss..."
              value={remarks}
              onChange={(e) => setRemarks(e.target.value)}
              disabled={isSubmitting}
            />
          </div>

          {/* Submit & Cancel Footer */}
          <div className="modal-footer-custom">
            <button
              type="button"
              className="btn btn-outline-secondary"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary px-4"
              disabled={isSubmitting || !fetchSuccess}
              title={!fetchSuccess ? 'Please fetch stock price first' : 'Save analysis'}
            >
              {isSubmitting
                ? 'Saving...'
                : isEditMode
                ? editModeType === 'new'
                  ? 'Add History Entry'
                  : 'Save Changes'
                : 'Submit'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

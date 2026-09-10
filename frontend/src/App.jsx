import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Activity, Target, SlidersHorizontal, PieChart, Search, X, TrendingUp } from 'lucide-react';
import * as api from './api';
import Header from './components/Header';
import AddTickerPanel from './components/AddTickerPanel';
import SchedulePanel from './components/SchedulePanel';
import ErrorsPanel from './components/ErrorsPanel';
import PortfolioSection from './components/PortfolioSection';
import StatusTab from './components/StatusTab';
import ScreenerTab from './components/ScreenerTab';
import PortfolioTrackerTab from './components/PortfolioTrackerTab';
import SwingTrackerTab from './components/SwingTrackerTab';
import Toast from './components/Toast';
import Footer from './components/Footer';

export default function App() {
  const [activeTab, setActiveTab] = useState('tracker'); // 'tracker' | 'portfolio-tracker' | 'status' | 'screener' | 'swing-tracker'
  const [snapshot, setSnapshot] = useState(null);
  const [runTimes, setRunTimes] = useState(['09:30', '11:30']);
  const [portfolioNames, setPortfolioNames] = useState(['BAPA', 'MADI']);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const [toastInfo, setToastInfo] = useState({ message: '', isError: false });
  const [trackerSearchQuery, setTrackerSearchQuery] = useState('');
  const trackerSearchInputRef = useRef(null);

  const knownVersionRef = useRef(0);

  const showToast = useCallback((message, isError = false) => {
    if (!message) return;
    setToastInfo({ message, isError });
  }, []);

  const hideToast = useCallback(() => {
    setToastInfo({ message: '', isError: false });
  }, []);

  const loadData = useCallback(async (notifyMessage = '') => {
    try {
      const dataPayload = await api.fetchData();
      if (dataPayload) {
        setSnapshot(dataPayload);
        if (dataPayload.portfolios) {
          setPortfolioNames(Object.keys(dataPayload.portfolios));
        }
      }

      if (notifyMessage) {
        showToast(notifyMessage, false);
      }
    } catch (err) {
      console.error('Failed to load portfolio data:', err);
      showToast(err.message || 'Failed to load portfolio data.', true);
    }
  }, [showToast]);

  const loadSchedule = useCallback(async () => {
    try {
      const res = await api.fetchSchedule();
      if (res && res.run_times) {
        setRunTimes(res.run_times);
      }
    } catch (err) {
      console.error('Failed to load schedule settings:', err);
    }
  }, []);

  // Initial load & SSE connection
  useEffect(() => {
    loadData();
    loadSchedule();

    const cleanup = api.connectStatusStream({
      knownVersion: knownVersionRef.current,
      onStateChange: (status) => {
        setConnectionStatus(status);
      },
      onUpdate: (status) => {
        if (status && typeof status.version === 'number') {
          knownVersionRef.current = status.version;
        }
        const sourceLabel = status && status.source === 'scheduled' ? 'Scheduled run completed' : 'Data updated';
        loadData(`${sourceLabel} — tables refreshed.`);
      },
    });

    return () => {
      cleanup();
    };
  }, [loadData, loadSchedule]);

  // Global Ctrl+F shortcut to focus table search on Tracker tab
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (activeTab === 'tracker' && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        if (trackerSearchInputRef.current) {
          trackerSearchInputRef.current.focus();
          trackerSearchInputRef.current.select();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeTab]);

  // Refresh All Tickers
  const handleRefresh = async () => {
    setIsRefreshing(true);
    setIsBusy(true);
    try {
      const res = await api.refreshAll();
      if (res.snapshot) {
        setSnapshot(res.snapshot);
      } else {
        await loadData();
      }
      showToast(res.message || 'Data refreshed successfully.', false);
    } catch (err) {
      showToast(err.message || 'Refresh failed.', true);
    } finally {
      setIsRefreshing(false);
      setIsBusy(false);
    }
  };

  // Add Ticker
  const handleAddTicker = async (portfolio, symbol) => {
    setIsBusy(true);
    try {
      const res = await api.addTicker(portfolio, symbol);
      if (res.snapshot) {
        setSnapshot(res.snapshot);
      } else {
        await loadData();
      }
      showToast(res.message || `${symbol} added to ${portfolio}.`, false);
    } catch (err) {
      showToast(err.message || `Failed to add ${symbol}.`, true);
      throw err; // rethrow so the form keeps its input on error
    } finally {
      setIsBusy(false);
    }
  };

  // Remove Ticker
  const handleRemoveTicker = async (portfolio, symbol) => {
    const confirmed = window.confirm(`Remove ${symbol} from ${portfolio}?`);
    if (!confirmed) return;

    setIsBusy(true);
    try {
      const res = await api.removeTicker(portfolio, symbol);
      if (res.snapshot) {
        setSnapshot(res.snapshot);
      } else {
        await loadData();
      }
      showToast(res.message || `${symbol} removed from ${portfolio}.`, false);
    } catch (err) {
      showToast(err.message || `Failed to remove ${symbol}.`, true);
    } finally {
      setIsBusy(false);
    }
  };

  // Save Schedule
  const handleSaveSchedule = async (times) => {
    setIsBusy(true);
    try {
      const res = await api.saveSchedule(times);
      if (res.run_times) {
        setRunTimes(res.run_times);
      }
      showToast(res.message || 'Scheduled run times saved.', false);
    } catch (err) {
      showToast(err.message || 'Failed to save scheduled run times.', true);
    } finally {
      setIsBusy(false);
    }
  };

  const portfolios = snapshot?.portfolios || {};
  const periods = snapshot?.ema_periods || [9, 21, 50, 100, 200];
  const errors = snapshot?.errors || [];
  const stats = snapshot?.stats || {};
  const generatedAt = snapshot?.generated_at || null;
  const source = snapshot?.source || null;

  const filteredPortfolios = useMemo(() => {
    if (!portfolios) return {};
    if (!trackerSearchQuery || !trackerSearchQuery.trim()) return portfolios;
    const q = trackerSearchQuery.trim().toLowerCase();
    const res = {};
    for (const [pName, pData] of Object.entries(portfolios)) {
      const rawRows = pData?.rows || [];
      const filtered = rawRows.filter((r) => {
        const sym = (r.symbol || '').toLowerCase();
        const disp = (r.display || '').toLowerCase();
        const name = (r.name || '').toLowerCase();
        return sym.includes(q) || disp.includes(q) || name.includes(q);
      });
      res[pName] = {
        ...pData,
        rows: filtered,
        totalCount: rawRows.length,
      };
    }
    return res;
  }, [portfolios, trackerSearchQuery]);

  return (
    <div className="app-container">
      {/* Top Header */}
      <Header
        activeTab={activeTab}
        generatedAt={generatedAt}
        source={source}
        stats={stats}
        isRefreshing={isRefreshing}
        onRefresh={handleRefresh}
        showRefresh={activeTab === 'tracker'}
      />

      {/* Tab Navigation */}
      <div className="tab-navigation-bar mb-4">
        <button
          type="button"
          className={`tab-nav-item ${activeTab === 'tracker' ? 'active' : ''}`}
          onClick={() => setActiveTab('tracker')}
        >
          <Activity size={16} />
          <span>Tracker</span>
        </button>
        <button
          type="button"
          className={`tab-nav-item ${activeTab === 'portfolio-tracker' ? 'active' : ''}`}
          onClick={() => setActiveTab('portfolio-tracker')}
        >
          <PieChart size={16} />
          <span>Portfolio Tracker</span>
        </button>
        <button
          type="button"
          className={`tab-nav-item ${activeTab === 'status' ? 'active' : ''}`}
          onClick={() => setActiveTab('status')}
        >
          <Target size={16} />
          <span>Status</span>
        </button>
        <button
          type="button"
          className={`tab-nav-item ${activeTab === 'screener' ? 'active' : ''}`}
          onClick={() => setActiveTab('screener')}
        >
          <SlidersHorizontal size={16} />
          <span>Screener</span>
        </button>
        <button
          type="button"
          className={`tab-nav-item ${activeTab === 'swing-tracker' ? 'active' : ''}`}
          onClick={() => setActiveTab('swing-tracker')}
        >
          <TrendingUp size={16} />
          <span>Swing Tracker</span>
        </button>
      </div>

      {/* Tab Content: Tracker vs Status vs Screener */}
      {activeTab === 'tracker' && (
        <>
          {/* Control Panels: Add Ticker & Schedule */}
          <section className="row g-3 mb-4">
            <div className="col-12 col-lg-7">
              <AddTickerPanel
                portfolioNames={portfolioNames}
                portfolios={portfolios}
                onAddTicker={handleAddTicker}
                disabled={isBusy}
              />
            </div>
            <div className="col-12 col-lg-5">
              <SchedulePanel
                initialRunTimes={runTimes}
                onSaveSchedule={handleSaveSchedule}
                disabled={isBusy}
              />
            </div>
          </section>

          {/* Errors / Fetch Problems */}
          <ErrorsPanel errors={errors} />

          {/* Live Search Filter for BAPA & MADI */}
          <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
            <div className="input-group input-group-sm" style={{ width: '320px' }}>
              <span className="input-group-text bg-white border-end-0 text-muted">
                <Search size={14} />
              </span>
              <input
                ref={trackerSearchInputRef}
                type="text"
                className="form-control border-start-0 ps-0"
                placeholder="Search BAPA & MADI... (Ctrl+F)"
                value={trackerSearchQuery}
                onChange={(e) => setTrackerSearchQuery(e.target.value)}
              />
              {trackerSearchQuery && (
                <button
                  type="button"
                  className="btn btn-outline-secondary border-start-0"
                  onClick={() => {
                    setTrackerSearchQuery('');
                    trackerSearchInputRef.current?.focus();
                  }}
                  title="Clear search"
                >
                  <X size={13} />
                </button>
              )}
            </div>
            {trackerSearchQuery && (
              <div className="text-muted" style={{ fontSize: '0.85rem' }}>
                Filtering tickers by <span className="fw-semibold text-dark">&ldquo;{trackerSearchQuery}&rdquo;</span>
              </div>
            )}
          </div>

          {/* Main Portfolio Tables */}
          <main className={isBusy ? 'busy-overlay' : ''}>
            {portfolioNames.map((name) => (
              <PortfolioSection
                key={name}
                name={name}
                portfolioData={filteredPortfolios[name] || { rows: [] }}
                periods={periods}
                onRemoveTicker={handleRemoveTicker}
                disabled={isBusy}
                searchQuery={trackerSearchQuery}
              />
            ))}
          </main>
        </>
      )}

      {activeTab === 'portfolio-tracker' && (
        <PortfolioTrackerTab showToast={showToast} />
      )}

      {activeTab === 'status' && (
        <StatusTab
          showToast={showToast}
          isBusy={isBusy}
          setIsBusy={setIsBusy}
        />
      )}

      {activeTab === 'screener' && (
        <ScreenerTab showToast={showToast} />
      )}

      {activeTab === 'swing-tracker' && (
        <SwingTrackerTab
          showToast={showToast}
          isBusy={isBusy}
          setIsBusy={setIsBusy}
        />
      )}

      {/* Footer */}
      <Footer connectionStatus={connectionStatus} />

      {/* Full-screen Loading Overlay for Refresh */}
      {isRefreshing && (
        <div className="fullscreen-loading-overlay" role="status" aria-live="polite">
          <div className="loading-card">
            <div className="spinner-border text-primary loading-spinner" role="status">
              <span className="visually-hidden">Loading...</span>
            </div>
            <h4 className="loading-title">Refreshing Market Data</h4>
            <p className="loading-subtitle">Fetching latest NSE/BSE quotes and updating portfolio EMAs...</p>
          </div>
        </div>
      )}

      {/* Toast notifications */}
      <Toast
        message={toastInfo.message}
        isError={toastInfo.isError}
        onClose={hideToast}
      />
    </div>
  );
}

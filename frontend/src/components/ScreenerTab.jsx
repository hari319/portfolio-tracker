import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  Search,
  RefreshCw,
  Calendar,
  KeyRound,
  HelpCircle,
  SlidersHorizontal,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ExternalLink,
  AlertTriangle,
  CheckCircle2,
  X,
  FileSpreadsheet,
  Layers,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Sparkles,
  Database,
  HardDrive,
  Download,
  Copy,
  Check
} from 'lucide-react';
import * as api from '../api';
import ScreenerFilterPanel from './ScreenerFilterPanel';
import {
  SCREENER_CATEGORIES,
  SCREENER_COLUMNS,
  DEFAULT_VISIBLE_COLUMNS
} from '../constants/screenerColumns';
import {
  STRATEGY_PRESETS,
  evaluateItemMatchesRule
} from '../constants/screenerFilters';

// Helper to compute last 11 days (YYYY-MM-DD)
function getLast11Days() {
  const days = [];
  const now = new Date();
  for (let i = 0; i < 15; i++) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    // Skip weekends if desired, or keep all
    const dayOfWeek = d.getDay();
    if (dayOfWeek === 0 || dayOfWeek === 6) continue; // skip Sat/Sun
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    days.push(`${yyyy}-${mm}-${dd}`);
    if (days.length === 11) break;
  }
  return days;
}

export default function ScreenerTab({ showToast }) {
  // Persistence state
  const [nonce, setNonce] = useState(() => localStorage.getItem('bbw_screener_nonce') || '');
  const [visibleColumns, setVisibleColumns] = useState(() => {
    try {
      const saved = localStorage.getItem('bbw_screener_columns');
      return saved ? JSON.parse(saved) : DEFAULT_VISIBLE_COLUMNS;
    } catch {
      return DEFAULT_VISIBLE_COLUMNS;
    }
  });

  // Fetch controls
  const [selectedDate, setSelectedDate] = useState(''); // '' = Today / Latest
  const [isFetching, setIsFetching] = useState(false);
  const [isAutoDetecting, setIsAutoDetecting] = useState(false);
  const [isSyncingHistory, setIsSyncingHistory] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [errorModal, setErrorModal] = useState(null); // { title, message }
  const [nonceInfo, setNonceInfo] = useState(null);
  const [showManualNonce, setShowManualNonce] = useState(false);
  const [multiDaySummary, setMultiDaySummary] = useState(null);

  // Screener Backup state
  const [isBackingUp, setIsBackingUp] = useState(false);
  const [backupResult, setBackupResult] = useState(null);
  const [copiedPath, setCopiedPath] = useState(false);


  // Screener Data & Saved Dates
  const [screenerData, setScreenerData] = useState(null);
  const [savedDates, setSavedDates] = useState([]);
  const [activeDateView, setActiveDateView] = useState('');

  // Table Search, Sort, Pagination
  const [searchInput, setSearchInput] = useState('');
  const [activeSearch, setActiveSearch] = useState('');
  const [sortConfig, setSortConfig] = useState({ key: 'symbol', direction: 'asc' });
  const [pageSize, setPageSize] = useState(50);
  const [currentPage, setCurrentPage] = useState(1);

  // Strategy Presets & Custom Multi-Rule Filters
  const [activePreset, setActivePreset] = useState(null);
  const [customRules, setCustomRules] = useState([]);
  const [matchMode, setMatchMode] = useState('all'); // 'all' (AND) | 'any' (OR)
  const [savedCustomPresets, setSavedCustomPresets] = useState(() => {
    try {
      const saved = localStorage.getItem('bbw_saved_custom_presets');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  // Column Popover Modal
  const [showColPicker, setShowColPicker] = useState(false);
  const [colSearch, setColSearch] = useState('');
  const colPickerRef = useRef(null);

  // Helper to merge multi-day analysis metrics into screener data items
  const enrichWithMultiDayAnalysis = async (force = false) => {
    try {
      const res = await api.fetchMultiDayAnalysis(11, force);
      if (res && res.ok) {
        if (res.setups_summary) {
          setMultiDaySummary(res.setups_summary);
        }
        if (Array.isArray(res.items)) {
          const enrichedMap = new Map();
          res.items.forEach((it) => {
            if (it.symbol) enrichedMap.set(it.symbol, it);
          });

          setScreenerData((prev) => {
            if (!prev || !Array.isArray(prev.items)) return prev;
            const updatedItems = prev.items.map((item) => {
              const extra = enrichedMap.get(item.symbol);
              return extra ? { ...item, ...extra } : item;
            });
            return { ...prev, items: updatedItems };
          });
        }
      }
    } catch (err) {
      console.warn('Multi-day sequence analysis non-critical error:', err);
    }
  };

  // Available trading dates (computed or from API response)
  const last11Days = useMemo(() => {
    if (screenerData && Array.isArray(screenerData.dates) && screenerData.dates.length > 0) {
      return screenerData.dates.slice(0, 11);
    }
    return getLast11Days();
  }, [screenerData]);

  // Load cached screener data on initial render
  useEffect(() => {
    async function loadInitial() {
      try {
        const res = await api.fetchScreenerData();
        if (res && res.data) {
          setScreenerData(res.data);
          setActiveDateView(res.data.date || '');
        }
        if (res && res.saved_dates) {
          setSavedDates(res.saved_dates);
        }
        if (res && res.nonce_info) {
          setNonceInfo(res.nonce_info);
        }
        if (res && res.multi_day_summary) {
          setMultiDaySummary(res.multi_day_summary);
        }
        // If we have saved dates but no multi-day metrics attached, run analysis
        if (res && res.saved_dates && res.saved_dates.length >= 2 && !res.multi_day_summary) {
          enrichWithMultiDayAnalysis();
        }
      } catch (err) {
        console.warn('No initial cached screener data:', err);
      }
    }
    loadInitial();
  }, []);

  // Save nonce and visibleColumns to localStorage
  const handleNonceChange = (val) => {
    setNonce(val);
    localStorage.setItem('bbw_screener_nonce', val);
  };

  const handleToggleColumn = (colKey) => {
    setVisibleColumns((prev) => {
      const next = prev.includes(colKey)
        ? prev.filter((k) => k !== colKey)
        : [...prev, colKey];
      localStorage.setItem('bbw_screener_columns', JSON.stringify(next));
      return next;
    });
  };

  const handleResetColumns = () => {
    setVisibleColumns(DEFAULT_VISIBLE_COLUMNS);
    localStorage.setItem('bbw_screener_columns', JSON.stringify(DEFAULT_VISIBLE_COLUMNS));
  };

  const handleSelectAllColumns = () => {
    const allKeys = SCREENER_COLUMNS.map((c) => c.key);
    setVisibleColumns(allKeys);
    localStorage.setItem('bbw_screener_columns', JSON.stringify(allKeys));
  };

  const handleDeselectAllColumns = () => {
    setVisibleColumns([]);
    localStorage.setItem('bbw_screener_columns', JSON.stringify([]));
  };

  // Close column picker on outside click
  useEffect(() => {
    function handleClickOutside(e) {
      if (colPickerRef.current && !colPickerRef.current.contains(e.target)) {
        setShowColPicker(false);
      }
    }
    if (showColPicker) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showColPicker]);

  // Auto-detect Nonce helper
  const handleAutoDetectNonce = async () => {
    setIsAutoDetecting(true);
    try {
      const res = await api.detectScreenerNonce();
      if (res && res.nonce) {
        handleNonceChange(res.nonce);
        setNonceInfo({ nonce: res.nonce, source: 'manual', date: new Date().toISOString().split('T')[0] });
        if (showToast) showToast('Nonce detected successfully from bigbreakingwire.in!', false);
      }
    } catch (err) {
      setErrorModal({
        title: 'Auto-Detect Nonce Failed',
        message:
          'Could not automatically detect the nonce from the website. Please follow the instructions to copy it from your browser DevTools.'
      });
    } finally {
      setIsAutoDetecting(false);
    }
  };

  // Screener Manual Backup handler
  const handleCreateBackup = async () => {
    setIsBackingUp(true);
    try {
      const res = await api.backupScreener();
      if (res && res.ok) {
        setBackupResult(res);
        if (showToast) showToast(`Screener backup created: ${res.filename} (${res.size_mb} MB)`, false);
      } else {
        setErrorModal({
          title: 'Screener Backup Failed',
          message: res?.error || 'Failed to create screener database backup.'
        });
      }
    } catch (err) {
      console.error('Screener backup error:', err);
      setErrorModal({
        title: 'Screener Backup Error',
        message: err.message || 'An error occurred while creating screener backup.'
      });
    } finally {
      setIsBackingUp(false);
    }
  };

  const handleCopyPath = async (textToCopy) => {
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopiedPath(true);
      setTimeout(() => setCopiedPath(false), 2000);
    } catch (err) {
      console.error('Failed to copy path:', err);
    }
  };


  // Switch to a previously saved local date
  const handleSwitchSavedDate = async (dateStr) => {
    if (!dateStr || dateStr === activeDateView) return;
    setIsFetching(true);
    try {
      const res = await api.fetchScreenerData(dateStr);
      if (res && res.data) {
        setScreenerData(res.data);
        setActiveDateView(res.data.date || dateStr);
        setCurrentPage(1);
        if (res.nonce_info || res.data?.nonce_info) {
          setNonceInfo(res.nonce_info || res.data?.nonce_info);
        }
        if (showToast) showToast(`Loaded saved screener data for ${dateStr}`, false);
      }
    } catch (err) {
      setErrorModal({
        title: 'Failed to Load Saved Date',
        message: err.message || 'Could not load data for the selected date.'
      });
    } finally {
      setIsFetching(false);
    }
  };

  // Trigger Manual Fetch (Nonce is auto-managed by backend, with optional manual override)
  const handleFetchData = async () => {
    setIsFetching(true);
    try {
      const res = await api.runScreenerFetch({
        nonce: nonce.trim(), // sent if manually set, otherwise backend auto-detects
        date: selectedDate,
        search: '',
        per_page: 3489
      });

      if (res && res.data) {
        setScreenerData(res.data);
        setActiveDateView(res.data.date || selectedDate || 'Latest');
        setCurrentPage(1);
        if (res.saved_dates) {
          setSavedDates(res.saved_dates);
        }
        if (res.nonce_info) {
          setNonceInfo(res.nonce_info);
          if (res.nonce_info.nonce) {
            handleNonceChange(res.nonce_info.nonce);
          }
        }
        if (showToast) {
          showToast(res.message || 'Screener data loaded successfully!', false);
        }
        // Run multi-day trajectory enrichment
        enrichWithMultiDayAnalysis();
      }
    } catch (err) {
      console.error('Screener fetch error:', err);
      setErrorModal({
        title: 'Fetch Failed',
        message:
          err.message ||
          'Failed to fetch screener data from bigbreakingwire.in. Please verify your internet connection.'
      });
      setShowManualNonce(true);
    } finally {
      setIsFetching(false);
    }
  };

  // Trigger Sync of Available Historical Dates (powers multi-day trajectory analysis)
  const handleSyncHistoricalDates = async () => {
    setIsSyncingHistory(true);
    try {
      const res = await api.syncScreenerHistory(11);
      if (res && res.available_saved_dates) {
        setSavedDates(res.available_saved_dates);
      }
      await enrichWithMultiDayAnalysis();
      if (showToast) {
        const count = (res.synced_dates || []).length;
        showToast(
          count > 0
            ? `Successfully synced ${count} historical dates! Multi-day trajectory analysis updated.`
            : `All ${res.total_cached || 0} available dates are already cached and analyzed!`,
          false
        );
      }
    } catch (err) {
      console.error('History sync error:', err);
      setErrorModal({
        title: 'Sync History Failed',
        message: err.message || 'Could not sync historical screener dates.',
      });
    } finally {
      setIsSyncingHistory(false);
    }
  };

  // Search handling
  const handleSearchSubmit = (e) => {
    if (e) e.preventDefault();
    setActiveSearch(searchInput.trim().toUpperCase());
    setCurrentPage(1);
  };

  const handleClearSearch = () => {
    setSearchInput('');
    setActiveSearch('');
    setCurrentPage(1);
  };

  // Preset and Custom Rule Handlers
  const handleSelectPreset = (presetId) => {
    if (activePreset === presetId) {
      setActivePreset(null);
    } else {
      setActivePreset(presetId);
      setCustomRules([]);
    }
    setCurrentPage(1);
  };

  const handleClearFilters = () => {
    setActivePreset(null);
    setCustomRules([]);
    setCurrentPage(1);
  };

  const handleSaveCustomPreset = (name, rules, mode) => {
    const newPreset = {
      id: `custom_${Date.now()}`,
      name,
      rules,
      matchMode: mode,
    };
    setSavedCustomPresets((prev) => {
      const updated = [...prev, newPreset];
      localStorage.setItem('bbw_saved_custom_presets', JSON.stringify(updated));
      return updated;
    });
    setActivePreset(newPreset.id);
    if (showToast) showToast(`Preset "${name}" saved!`, false);
  };

  const handleDeleteCustomPreset = (presetId) => {
    setSavedCustomPresets((prev) => {
      const updated = prev.filter((p) => p.id !== presetId);
      localStorage.setItem('bbw_saved_custom_presets', JSON.stringify(updated));
      return updated;
    });
    if (activePreset === presetId) setActivePreset(null);
    if (showToast) showToast('Custom preset deleted.', false);
  };

  const handleLoadCustomPreset = (preset) => {
    setActivePreset(preset.id);
    setCustomRules(preset.rules || []);
    setMatchMode(preset.matchMode || 'all');
    setCurrentPage(1);
  };

  // Filtered & Sorted items
  const rawItems = screenerData?.items || [];

  const filteredItems = useMemo(() => {
    let items = rawItems;

    // 1. Symbol Search Filter
    if (activeSearch) {
      items = items.filter((item) => {
        const sym = (item.symbol || '').toUpperCase();
        return sym.includes(activeSearch);
      });
    }

    // 2. Curated Strategy Preset Filter
    if (activePreset) {
      const preset = STRATEGY_PRESETS.find((s) => s.id === activePreset);
      if (preset && Array.isArray(preset.rules)) {
        items = items.filter((item) => {
          return preset.rules.every((rule) => evaluateItemMatchesRule(item, rule));
        });
      } else {
        // Check if it's one of user's saved custom presets
        const customPreset = savedCustomPresets.find((s) => s.id === activePreset);
        if (customPreset && Array.isArray(customPreset.rules) && customPreset.rules.length > 0) {
          items = items.filter((item) => {
            if (customPreset.matchMode === 'any') {
              return customPreset.rules.some((rule) => evaluateItemMatchesRule(item, rule));
            }
            return customPreset.rules.every((rule) => evaluateItemMatchesRule(item, rule));
          });
        }
      }
    }

    // 3. Custom Multi-Rule Builder Filter
    if (customRules.length > 0) {
      items = items.filter((item) => {
        if (matchMode === 'any') {
          return customRules.some((rule) => evaluateItemMatchesRule(item, rule));
        }
        return customRules.every((rule) => evaluateItemMatchesRule(item, rule));
      });
    }

    return items;
  }, [rawItems, activeSearch, activePreset, customRules, matchMode, savedCustomPresets]);

  const sortedItems = useMemo(() => {
    if (!sortConfig.key) return filteredItems;
    const { key, direction } = sortConfig;
    const mult = direction === 'asc' ? 1 : -1;

    return [...filteredItems].sort((a, b) => {
      let valA = a[key];
      let valB = b[key];

      if (valA === null || valA === undefined || valA === '') return 1;
      if (valB === null || valB === undefined || valB === '') return -1;

      if (typeof valA === 'number' && typeof valB === 'number') {
        return (valA - valB) * mult;
      }
      return String(valA).localeCompare(String(valB)) * mult;
    });
  }, [filteredItems, sortConfig]);

  // Pagination
  const totalItems = sortedItems.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const pageIndex = Math.min(currentPage, totalPages);

  const paginatedItems = useMemo(() => {
    const start = (pageIndex - 1) * pageSize;
    return sortedItems.slice(start, start + pageSize);
  }, [sortedItems, pageIndex, pageSize]);

  const handleSort = (key) => {
    setSortConfig((prev) => {
      if (prev.key === key) {
        return { key, direction: prev.direction === 'asc' ? 'desc' : 'asc' };
      }
      return { key, direction: 'desc' };
    });
  };

  // Lookup map for columns
  const columnMap = useMemo(() => {
    const map = new Map();
    SCREENER_COLUMNS.forEach((col) => map.set(col.key, col));
    return map;
  }, []);

  // Filter columns list for picker
  const filteredColumnsForPicker = useMemo(() => {
    if (!colSearch.trim()) return SCREENER_COLUMNS;
    const term = colSearch.toLowerCase();
    return SCREENER_COLUMNS.filter(
      (c) => c.label.toLowerCase().includes(term) || c.key.toLowerCase().includes(term)
    );
  }, [colSearch]);

  // Group columns by category for picker
  const groupedColumns = useMemo(() => {
    const groups = {};
    SCREENER_CATEGORIES.forEach((cat) => (groups[cat] = []));
    filteredColumnsForPicker.forEach((col) => {
      const cat = col.category || 'Other';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(col);
    });
    return groups;
  }, [filteredColumnsForPicker]);

  // Cell Formatter
  const renderCellContent = (item, colKey) => {
    const val = item[colKey];
    if (val === null || val === undefined || val === '') {
      return <span className="text-muted">—</span>;
    }

    const meta = columnMap.get(colKey);
    const format = meta?.format;

    if (format === 'setups') {
      const setups = Array.isArray(val) ? val : [];
      if (setups.length === 0) return <span className="text-muted">—</span>;
      return (
        <div className="d-flex flex-wrap gap-1">
          {setups.map((s) => {
            let label = s;
            let bgClass = 'bg-secondary-subtle text-secondary';
            if (s === 'silent_accumulation') {
              label = '📦 Silent Acc';
              bgClass = 'bg-success-subtle text-success border-success-subtle';
            } else if (s === 'fresh_signal_flip') {
              label = '⚡ Fresh Flip';
              bgClass = 'bg-primary-subtle text-primary border-primary-subtle';
            } else if (s === 'vcp_breakout') {
              label = '🎯 VCP Breakout';
              bgClass = 'bg-info-subtle text-info-emphasis border-info-subtle';
            } else if (s === 'momentum_staircase') {
              label = '📈 Staircase';
              bgClass = 'bg-warning-subtle text-warning-emphasis border-warning-subtle';
            }
            return (
              <span key={s} className={`badge ${bgClass} border px-1.5 py-0.5 fw-semibold`} style={{ fontSize: '10px' }}>
                {label}
              </span>
            );
          })}
        </div>
      );
    }

    if (format === 'score') {
      const num = Number(val);
      if (isNaN(num)) return val;
      let badgeClass = 'bg-secondary-subtle text-secondary border';
      if (num >= 80) badgeClass = 'bg-success-subtle text-success border border-success-subtle';
      else if (num >= 65) badgeClass = 'bg-primary-subtle text-primary border border-primary-subtle';
      else if (num >= 50) badgeClass = 'bg-warning-subtle text-warning-emphasis border border-warning-subtle';
      return <span className={`badge ${badgeClass} px-2 py-1 fw-bold`}>{num}/100</span>;
    }

    if (format === 'currency') {
      const num = Number(val);
      if (isNaN(num)) return val;
      return <span>₹{num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>;
    }

    if (format === 'percent') {
      const num = Number(val);
      if (isNaN(num)) return val;
      const isNeg = num < 0;
      const isPos = num > 0;
      const formatted = `${isPos ? '+' : ''}${num.toFixed(2)}%`;
      return (
        <span className={isNeg ? 'val-negative' : isPos ? 'val-positive' : ''}>
          {formatted}
        </span>
      );
    }

    if (format === 'integer') {
      const num = Number(val);
      if (isNaN(num)) return val;
      return <span>{num.toLocaleString('en-IN')}</span>;
    }

    if (format === 'number') {
      const num = Number(val);
      if (isNaN(num)) return val;
      return <span>{num.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</span>;
    }

    if (format === 'signal') {
      const s = String(val).toLowerCase();
      let badgeClass = 'badge-signal-neutral';
      if (s.includes('bullish')) badgeClass = 'badge-signal-bullish';
      if (s.includes('bearish')) badgeClass = 'badge-signal-bearish';
      return <span className={`signal-pill ${badgeClass}`}>{val}</span>;
    }

    if (format === 'st_dir') {
      const isBull = val === 1 || String(val).toLowerCase() === 'bullish';
      return (
        <span className={`signal-pill ${isBull ? 'badge-signal-bullish' : 'badge-signal-bearish'}`}>
          {isBull ? 'Bullish' : 'Bearish'}
        </span>
      );
    }

    if (format === 'boolean_flag') {
      return val === 1 || val === true ? (
        <span className="badge bg-primary-subtle text-primary border border-primary-subtle px-2 py-0.5 rounded">Yes</span>
      ) : (
        <span className="text-muted opacity-50">0</span>
      );
    }

    if (format === 'badge') {
      const s = String(val).toLowerCase();
      let badgeClass = 'bg-light text-dark';
      if (s.includes('bullish') || s.includes('rising') || s.includes('above') || s.includes('expanding') || s.includes('strong')) {
        badgeClass = 'badge-signal-bullish';
      } else if (s.includes('bearish') || s.includes('falling') || s.includes('below') || s.includes('breakdown')) {
        badgeClass = 'badge-signal-bearish';
      }
      return <span className={`signal-pill ${badgeClass}`}>{val}</span>;
    }

    return String(val);
  };

  const lastFetchedTimeStr = screenerData?.last_fetched_at
    ? new Date(screenerData.last_fetched_at).toLocaleString()
    : null;

  return (
    <div className="screener-container">
      {/* Top Fetch Control Card */}
      <div className="dashboard-card p-4 mb-4">
        <div className="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
          <div className="d-flex align-items-center gap-2">
            <h5 className="mb-0 fw-bold d-flex align-items-center gap-2">
              <Database size={20} className="text-primary" />
              <span>Prime Market Screener</span>
            </h5>
            {nonceInfo?.nonce ? (
              <span
                className="badge bg-success-subtle text-success border border-success-subtle px-2 py-1 d-inline-flex align-items-center gap-1"
                title={`Nonce ${nonceInfo.nonce} active for ${nonceInfo.date || 'today'}`}
              >
                <CheckCircle2 size={13} />
                <span>Nonce: Active ({nonceInfo.date || 'Today'})</span>
              </span>
            ) : (
              <span className="badge bg-info-subtle text-info-emphasis border border-info-subtle px-2 py-1 d-inline-flex align-items-center gap-1">
                <Sparkles size={13} />
                <span>Auto-managed Nonce</span>
              </span>
            )}
          </div>

          <div className="d-flex align-items-center gap-2">
            <button
              type="button"
              className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-1"
              onClick={handleCreateBackup}
              disabled={isBackingUp}
              title="Create a manual backup snapshot of the screener database"
            >
              {isBackingUp ? (
                <RefreshCw size={14} className="spin-anim text-primary" />
              ) : (
                <HardDrive size={14} />
              )}
              <span>{isBackingUp ? 'Backing up...' : 'Backup'}</span>
            </button>

            <button
              type="button"
              className={`btn btn-sm ${showManualNonce ? 'btn-secondary' : 'btn-outline-secondary'} d-flex align-items-center gap-1`}
              onClick={() => setShowManualNonce((prev) => !prev)}
            >
              <KeyRound size={14} />
              <span>{showManualNonce ? 'Hide Nonce Settings' : 'Nonce Settings'}</span>
            </button>
          </div>
        </div>

        {/* Collapsible Manual Nonce Settings & Guidance */}
        {showManualNonce && (
          <div className="alert alert-light border mb-3 p-3 rounded-3 shadow-sm">
            <div className="d-flex justify-content-between align-items-start mb-2">
              <h6 className="alert-heading fw-bold mb-0 d-flex align-items-center gap-2 small">
                <KeyRound size={15} className="text-primary" /> Nonce Management (Automatic Daily Refresh)
              </h6>
              <button
                type="button"
                className="btn-close btn-close-sm"
                onClick={() => setShowManualNonce(false)}
                aria-label="Close"
              ></button>
            </div>
            <p className="small text-muted mb-2">
              The application automatically extracts and maintains a fresh <code>X-WP-Nonce</code> from{' '}
              <a href="https://bigbreakingwire.in/screener/" target="_blank" rel="noreferrer" className="text-decoration-underline">
                bigbreakingwire.in
              </a>{' '}
              for the day. You only need to enter one manually if auto-detection is blocked.
            </p>

            <div className="row g-2 align-items-center">
              <div className="col-12 col-md-8">
                <div className="input-group input-group-sm">
                  <span className="input-group-text bg-white text-muted">
                    <KeyRound size={14} />
                  </span>
                  <input
                    type="text"
                    className="form-control font-monospace"
                    placeholder="Custom X-WP-Nonce (optional override)..."
                    value={nonce}
                    onChange={(e) => handleNonceChange(e.target.value)}
                    disabled={isFetching}
                  />
                  {nonce && (
                    <button
                      type="button"
                      className="btn btn-outline-secondary"
                      onClick={() => handleNonceChange('')}
                      title="Clear custom override to use automatic detection"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>
              <div className="col-12 col-md-4">
                <button
                  type="button"
                  className="btn btn-sm btn-outline-primary d-flex align-items-center gap-1"
                  onClick={handleAutoDetectNonce}
                  disabled={isFetching || isAutoDetecting}
                >
                  <Sparkles size={13} className={isAutoDetecting ? 'animate-spin' : ''} />
                  <span>{isAutoDetecting ? 'Detecting...' : 'Force Auto-Detect Now'}</span>
                </button>
              </div>
            </div>

            <div className="mt-2 pt-2 border-top small text-muted">
              <strong>How to find manually if needed:</strong> Open DevTools (<kbd>F12</kbd>) on{' '}
              <a href="https://bigbreakingwire.in/screener/" target="_blank" rel="noreferrer">bigbreakingwire.in/screener/</a>{' '}
              → Network tab → inspect request named <code>run</code> → copy <code>X-WP-Nonce</code> from Request Headers.
            </div>
          </div>
        )}

        {/* Primary Fetch Controls Row */}
        <div className="row g-3 align-items-end">
          {/* Date Picker */}
          <div className="col-12 col-md-5 col-lg-4">
            <label className="form-label small fw-bold text-muted mb-1">
              Trading Date
            </label>
            <div className="input-group">
              <span className="input-group-text bg-light text-muted">
                <Calendar size={16} />
              </span>
              <select
                className="form-select"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                disabled={isFetching}
              >
                <option value="">Today / Latest (Default)</option>
                {last11Days.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Fetch Button */}
          <div className="col-12 col-md-4 col-lg-3">
            <button
              type="button"
              className="btn btn-primary w-100 d-flex align-items-center justify-content-center gap-2 py-2 fw-semibold"
              onClick={handleFetchData}
              disabled={isFetching}
            >
              <RefreshCw size={16} className={isFetching ? 'animate-spin' : ''} />
              <span>{isFetching ? 'Fetching Dataset...' : 'Fetch Data'}</span>
            </button>
          </div>

          {/* Local Stored Dates Switcher */}
          {savedDates.length > 0 && (
            <div className="col-12 col-md-3 col-lg-5">
              <label className="form-label small fw-bold text-muted mb-1">
                Saved Local Dates (Compare)
              </label>
              <div className="input-group">
                <span className="input-group-text bg-light text-muted">
                  <Database size={16} />
                </span>
                <select
                  className="form-select"
                  value={activeDateView}
                  onChange={(e) => handleSwitchSavedDate(e.target.value)}
                  disabled={isFetching}
                >
                  {savedDates.map((sd) => (
                    <option key={sd.date} value={sd.date}>
                      {sd.date} — {sd.total ? `${sd.total.toLocaleString()} stocks` : 'cached'}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>

        {/* Metadata Banner */}
        <div className="d-flex flex-wrap align-items-center justify-content-between gap-3 mt-3 pt-3 border-top">
          <div className="d-flex flex-wrap align-items-center gap-3 small">
            {lastFetchedTimeStr ? (
              <span className="text-muted d-flex align-items-center gap-1">
                <strong>Last Fetched:</strong> {lastFetchedTimeStr}
              </span>
            ) : (
              <span className="text-muted fst-italic">No data fetched yet. Click "Fetch Data" above.</span>
            )}

            {screenerData?.date && (
              <span className="badge bg-primary-subtle text-primary border border-primary-subtle px-2 py-1">
                Trading Date: {screenerData.date}
              </span>
            )}

            {rawItems.length > 0 && (
              <span className="badge bg-light text-dark border px-2 py-1">
                {rawItems.length.toLocaleString()} Stocks Available
              </span>
            )}
          </div>

          {savedDates.length > 1 && (
            <div className="small text-muted">
              {savedDates.length} historical dates saved locally
            </div>
          )}
        </div>
      </div>

      {/* Strategy Presets & Custom Rule Filter Panel */}
      {rawItems.length > 0 && (
        <ScreenerFilterPanel
          activePreset={activePreset}
          onSelectPreset={handleSelectPreset}
          customRules={customRules}
          onChangeCustomRules={(rules) => {
            setCustomRules(rules);
            if (rules.length > 0) setActivePreset(null);
            setCurrentPage(1);
          }}
          matchMode={matchMode}
          onChangeMatchMode={(mode) => {
            setMatchMode(mode);
            setCurrentPage(1);
          }}
          onClearFilters={handleClearFilters}
          totalItems={totalItems}
          rawItemsCount={rawItems.length}
          savedCustomPresets={savedCustomPresets}
          onSaveCustomPreset={handleSaveCustomPreset}
          onDeleteCustomPreset={handleDeleteCustomPreset}
          onLoadCustomPreset={handleLoadCustomPreset}
          onSyncHistory={handleSyncHistoricalDates}
          isSyncingHistory={isSyncingHistory}
          savedDatesCount={savedDates.length}
          multiDaySummary={multiDaySummary}
        />
      )}

      {/* Table Controls & Filter Bar */}
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 mb-3">
        {/* Symbol Search Input (live as-you-type filter) */}
        <div className="d-flex align-items-center gap-2 flex-grow-1" style={{ maxWidth: '380px' }}>
          <div className="input-group">
            <span className="input-group-text bg-white border-end-0 text-muted">
              <Search size={15} />
            </span>
            <input
              type="text"
              className="form-control border-start-0 ps-0"
              placeholder="Search symbol (e.g. RELIANCE, TCS)..."
              value={searchInput}
              onChange={(e) => {
                const val = e.target.value;
                setSearchInput(val);
                setActiveSearch(val.trim().toUpperCase());
                setCurrentPage(1);
              }}
            />
            {searchInput && (
              <button
                type="button"
                className="btn btn-outline-secondary border-start-0"
                onClick={handleClearSearch}
                title="Clear search"
              >
                <X size={15} />
              </button>
            )}
          </div>
        </div>

        {/* Column Picker & Rows Per Page */}
        <div className="d-flex align-items-center gap-2 flex-wrap">
          {/* Column Picker Trigger */}
          <div className="position-relative" ref={colPickerRef}>
            <button
              type="button"
              className={`btn btn-sm btn-outline-secondary d-flex align-items-center gap-2 ${showColPicker ? 'active' : ''}`}
              onClick={() => setShowColPicker((prev) => !prev)}
            >
              <SlidersHorizontal size={15} />
              <span>Columns ({visibleColumns.length})</span>
            </button>

            {/* Column Picker Popover */}
            {showColPicker && (
              <div className="scr-cols-popover-menu shadow-lg">
                <div className="p-2 border-bottom bg-light">
                  <div className="d-flex justify-content-between align-items-center mb-2">
                    <span className="small fw-bold text-uppercase text-muted">Select Columns</span>
                    <button
                      type="button"
                      className="btn-close btn-close-sm"
                      onClick={() => setShowColPicker(false)}
                    ></button>
                  </div>
                  <input
                    type="text"
                    className="form-control form-control-sm mb-2"
                    placeholder="Filter columns..."
                    value={colSearch}
                    onChange={(e) => setColSearch(e.target.value)}
                  />
                  <div className="d-flex gap-1">
                    <button
                      type="button"
                      className="btn btn-xs btn-outline-primary py-0 px-2"
                      onClick={handleResetColumns}
                    >
                      Default
                    </button>
                    <button
                      type="button"
                      className="btn btn-xs btn-outline-secondary py-0 px-2"
                      onClick={handleSelectAllColumns}
                    >
                      All
                    </button>
                    <button
                      type="button"
                      className="btn btn-xs btn-outline-secondary py-0 px-2"
                      onClick={handleDeselectAllColumns}
                    >
                      Clear
                    </button>
                  </div>
                </div>

                <div className="scr-cols-scroll-body p-2">
                  {Object.entries(groupedColumns).map(([category, cols]) => {
                    if (!cols || cols.length === 0) return null;
                    return (
                      <div key={category} className="mb-2">
                        <div className="scr-cat-header">{category}</div>
                        <div className="scr-col-grid">
                          {cols.map((c) => (
                            <label key={c.key} className="scr-col-opt-label">
                              <input
                                type="checkbox"
                                checked={visibleColumns.includes(c.key)}
                                onChange={() => handleToggleColumn(c.key)}
                              />
                              <span title={c.key}>{c.label}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Rows Per Page */}
          <div className="d-flex align-items-center gap-1 small text-muted">
            <span>Show:</span>
            <select
              className="form-select form-select-sm"
              style={{ width: '80px' }}
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setCurrentPage(1);
              }}
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
        </div>
      </div>

      {/* Main Table Card */}
      <div className="dashboard-card mb-4 position-relative overflow-hidden">
        {sortedItems.length === 0 ? (
          <div className="text-center py-5">
            <FileSpreadsheet size={40} className="text-muted mb-2 opacity-50" />
            <h6 className="fw-semibold text-muted">No Stocks Found</h6>
            <p className="small text-muted mb-3">
              {rawItems.length === 0
                ? 'No screener data loaded yet. Provide your X-WP-Nonce above and click "Fetch Data".'
                : `No symbols match the search filter "${activeSearch}".`}
            </p>
            {activeSearch && (
              <button
                type="button"
                className="btn btn-sm btn-outline-secondary"
                onClick={handleClearSearch}
              >
                Clear Search Filter
              </button>
            )}
          </div>
        ) : (
          <div className="table-responsive-wrapper screener-table-scroll">
            <table className="table-stock screener-table">
              <thead>
                <tr>
                  {/* Fixed Column 1: Symbol */}
                  <th
                    className="col-sticky-symbol text-start sortable-th"
                    onClick={() => handleSort('symbol')}
                  >
                    <div className="d-flex align-items-center gap-1">
                      <span>Symbol</span>
                      {sortConfig.key === 'symbol' && (
                        sortConfig.direction === 'asc' ? <ArrowUp size={13} /> : <ArrowDown size={13} />
                      )}
                    </div>
                  </th>

                  {/* Fixed Column 2: Price */}
                  <th
                    className="col-sticky-price text-end sortable-th"
                    onClick={() => handleSort('close')}
                  >
                    <div className="d-flex align-items-center justify-content-end gap-1">
                      <span>Price</span>
                      {sortConfig.key === 'close' && (
                        sortConfig.direction === 'asc' ? <ArrowUp size={13} /> : <ArrowDown size={13} />
                      )}
                    </div>
                  </th>

                  {/* Dynamic Columns */}
                  {visibleColumns.map((colKey) => {
                    const meta = columnMap.get(colKey);
                    const label = meta?.label || colKey;
                    const isSorted = sortConfig.key === colKey;
                    return (
                      <th
                        key={colKey}
                        className={`sortable-th ${meta?.format === 'currency' || meta?.format === 'percent' || meta?.format === 'integer' || meta?.format === 'number' ? 'text-end' : 'text-start'}`}
                        onClick={() => handleSort(colKey)}
                      >
                        <div className={`d-flex align-items-center gap-1 ${meta?.format === 'currency' || meta?.format === 'percent' || meta?.format === 'integer' || meta?.format === 'number' ? 'justify-content-end' : 'justify-content-start'}`}>
                          <span>{label}</span>
                          {isSorted && (
                            sortConfig.direction === 'asc' ? <ArrowUp size={13} /> : <ArrowDown size={13} />
                          )}
                        </div>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {paginatedItems.map((item) => {
                  const symbol = item.symbol || '';
                  const companyName = item.company_name || '';
                  const tvUrl = `https://in.tradingview.com/chart/?symbol=NSE:${symbol}`;

                  return (
                    <tr key={symbol}>
                      {/* Fixed Col 1: Symbol */}
                      <td className="col-sticky-symbol">
                        <div className="d-flex flex-column">
                          <a
                            href={tvUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="stock-symbol-link d-inline-flex align-items-center gap-1 fw-bold"
                            title={`Open ${symbol} chart on TradingView`}
                          >
                            <span>{symbol}</span>
                            <ExternalLink size={12} className="opacity-50" />
                          </a>
                          {companyName && (
                            <span className="stock-company-subtext text-truncate" style={{ maxWidth: '140px' }} title={companyName}>
                              {companyName}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Fixed Col 2: Price */}
                      <td className="col-sticky-price text-end fw-semibold">
                        {renderCellContent(item, 'close')}
                      </td>

                      {/* Dynamic Columns */}
                      {visibleColumns.map((colKey) => {
                        const meta = columnMap.get(colKey);
                        const isNum = meta?.format === 'currency' || meta?.format === 'percent' || meta?.format === 'integer' || meta?.format === 'number';
                        return (
                          <td key={colKey} className={isNum ? 'text-end' : 'text-start'}>
                            {renderCellContent(item, colKey)}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {sortedItems.length > 0 && (
          <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 p-3 border-top bg-light">
            <div className="small text-muted">
              Showing <strong>{(pageIndex - 1) * pageSize + 1}</strong> to{' '}
              <strong>{Math.min(pageIndex * pageSize, totalItems)}</strong> of{' '}
              <strong>{totalItems.toLocaleString()}</strong> entries
              {activeSearch && <span> (filtered from {rawItems.length.toLocaleString()})</span>}
            </div>

            <div className="d-flex align-items-center gap-1">
              <button
                type="button"
                className="btn btn-sm btn-outline-secondary px-2"
                onClick={() => setCurrentPage(1)}
                disabled={pageIndex === 1}
                title="First Page"
              >
                <ChevronsLeft size={16} />
              </button>
              <button
                type="button"
                className="btn btn-sm btn-outline-secondary px-2"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={pageIndex === 1}
                title="Previous Page"
              >
                <ChevronLeft size={16} />
              </button>

              <span className="px-2 small fw-semibold">
                Page {pageIndex} of {totalPages}
              </span>

              <button
                type="button"
                className="btn btn-sm btn-outline-secondary px-2"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={pageIndex === totalPages}
                title="Next Page"
              >
                <ChevronRight size={16} />
              </button>
              <button
                type="button"
                className="btn btn-sm btn-outline-secondary px-2"
                onClick={() => setCurrentPage(totalPages)}
                disabled={pageIndex === totalPages}
                title="Last Page"
              >
                <ChevronsRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Middle-of-page Loading Modal */}
      {isFetching && (
        <div className="fullscreen-loading-overlay" role="status" aria-live="polite">
          <div className="loading-card shadow-lg p-4 text-center">
            <div className="spinner-border text-primary loading-spinner mb-3" style={{ width: '3rem', height: '3rem' }}>
              <span className="visually-hidden">Loading...</span>
            </div>
            <h4 className="loading-title mb-1">Fetching Screener Data</h4>
            <p className="loading-subtitle text-muted mb-0">
              Querying market dataset ({selectedDate || 'Latest / Today'})... This may take a few moments.
            </p>
          </div>
        </div>
      )}

      {/* Screener Backup Success / Info Modal */}
      {backupResult && (
        <div className="modal-backdrop-custom" role="dialog" aria-modal="true">
          <div className="modal-dialog-custom shadow-lg" style={{ maxWidth: '540px' }}>
            <div className="modal-header-custom border-bottom pb-2 d-flex align-items-center justify-content-between">
              <div className="d-flex align-items-center gap-2 text-success">
                <HardDrive size={20} />
                <h6 className="modal-title mb-0 fw-bold">Screener Backup Created</h6>
              </div>
              <button
                type="button"
                className="btn-close"
                onClick={() => setBackupResult(null)}
              ></button>
            </div>
            <div className="modal-body-custom py-3">
              <div className="alert alert-success-subtle border border-success-subtle d-flex align-items-center gap-2 p-2 mb-3 rounded-2 small text-success">
                <CheckCircle2 size={16} />
                <span>Successfully generated a standalone snapshot of the screener database.</span>
              </div>

              <div className="table-responsive mb-3">
                <table className="table table-sm table-bordered mb-0 small">
                  <tbody>
                    <tr>
                      <th className="bg-light text-muted text-nowrap" style={{ width: '120px' }}>Filename</th>
                      <td className="fw-mono fw-semibold text-dark">{backupResult.filename}</td>
                    </tr>
                    <tr>
                      <th className="bg-light text-muted text-nowrap">File Size</th>
                      <td className="fw-semibold text-dark">{backupResult.size_mb} MB</td>
                    </tr>
                    <tr>
                      <th className="bg-light text-muted text-nowrap">Full Path</th>
                      <td>
                        <div className="d-flex align-items-center justify-content-between gap-2">
                          <code className="text-break small" style={{ fontSize: '0.78rem' }}>{backupResult.path}</code>
                          <button
                            type="button"
                            className="btn btn-xs btn-outline-secondary d-inline-flex align-items-center gap-1 text-nowrap"
                            style={{ fontSize: '0.75rem', padding: '2px 6px' }}
                            onClick={() => handleCopyPath(backupResult.path)}
                            title="Copy full path to clipboard"
                          >
                            {copiedPath ? <Check size={12} className="text-success" /> : <Copy size={12} />}
                            <span>{copiedPath ? 'Copied!' : 'Copy'}</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <p className="text-muted small mb-0">
                You can download this backup directly to your machine or leave it safely stored in your project&apos;s <code>backups/</code> directory.
              </p>
            </div>
            <div className="modal-footer-custom border-top pt-2 d-flex justify-content-between align-items-center">
              <a
                href={api.getScreenerBackupDownloadUrl(backupResult.filename)}
                download={backupResult.filename}
                className="btn btn-sm btn-primary d-inline-flex align-items-center gap-1 px-3"
              >
                <Download size={14} />
                <span>Download Backup</span>
              </a>
              <button
                type="button"
                className="btn btn-sm btn-outline-secondary px-3"
                onClick={() => setBackupResult(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error Alert Modal */}
      {errorModal && (
        <div className="modal-backdrop-custom" role="dialog" aria-modal="true">
          <div className="modal-dialog-custom shadow-lg" style={{ maxWidth: '480px' }}>
            <div className="modal-header-custom border-bottom pb-2 d-flex align-items-center justify-content-between">
              <div className="d-flex align-items-center gap-2 text-danger">
                <AlertTriangle size={20} />
                <h6 className="modal-title mb-0 fw-bold">{errorModal.title}</h6>
              </div>
              <button
                type="button"
                className="btn-close"
                onClick={() => setErrorModal(null)}
              ></button>
            </div>
            <div className="modal-body-custom py-3">
              <p className="text-secondary small mb-3">{errorModal.message}</p>
              <div className="p-2 bg-light rounded small text-muted border">
                <strong>Tip:</strong> If your nonce has expired, open{' '}
                <a href="https://bigbreakingwire.in/screener/" target="_blank" rel="noreferrer" className="text-primary">
                  bigbreakingwire.in/screener/
                </a>
                , press F12 → Network tab, look for request <code>run</code>, and copy the fresh <code>X-WP-Nonce</code>.
              </div>
            </div>
            <div className="modal-footer-custom border-top pt-2 d-flex justify-content-end">
              <button
                type="button"
                className="btn btn-sm btn-primary px-3"
                onClick={() => setErrorModal(null)}
              >
                Understood
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

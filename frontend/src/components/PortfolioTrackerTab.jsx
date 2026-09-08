import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  FolderCheck,
  Plus,
  Download,
  Upload,
  ChevronDown,
  ChevronRight,
  Trash2,
  Edit3,
  DollarSign,
  AlertCircle,
  FileText,
  BookOpen,
  CheckCircle2,
  History,
  Info,
  Search,
  X,
} from 'lucide-react';
import * as api from '../api';
import useTickerLookup from '../hooks/useTickerLookup';
import SoldPositionsModal from './SoldPositionsModal';
import DividendsModal from './DividendsModal';
import {
  BUY_CHARGE_RATE,
  SELL_CHARGE_RATE,
} from '../constants/portfolioCharges';
import { formatDate } from '../utils/date';

// Feature flags for temporarily hidden UI elements (see docs/PORTFOLIO_TRACKER.md §7)
// Set either flag to true to re-enable the respective control in the UI
const SHOW_IMPORT_BUTTON = false;
const SHOW_CURRENT_DATE = false;

function calculatePeriod(date1, date2) {
  if (!date1 || !date2) return { years: 0, months: 0 };
  const d1 = new Date(date1);
  const d2 = new Date(date2);
  if (isNaN(d1.getTime()) || isNaN(d2.getTime()) || d2 < d1) {
    return { years: 0, months: 0 };
  }
  let months =
    (d2.getFullYear() - d1.getFullYear()) * 12 +
    (d2.getMonth() - d1.getMonth());
  if (d2.getDate() < d1.getDate()) {
    months -= 1;
  }
  months = Math.max(0, months);
  const years = Math.floor(months / 12);
  return { years, months };
}

export default function PortfolioTrackerTab({ showToast }) {
  const [activePortfolio, setActivePortfolio] = useState('LOAN'); // 'MADI' | 'BAPA' | 'LOAN'
  const [data, setData] = useState(null);
  const [exportingScope, setExportingScope] = useState(null); // 'all' | activePortfolio | null
  const [loading, setLoading] = useState(false);
  const [expandedHoldings, setExpandedHoldings] = useState({});
  const [expandedSoldHoldings, setExpandedSoldHoldings] = useState({});

  // Horizontal scroll sync for Open Holdings table
  const openTableContainerRef = useRef(null);
  const openTopScrollRef = useRef(null);
  const [openTableScrollWidth, setOpenTableScrollWidth] = useState(0);

  // Table search & keyboard shortcut state
  const [searchQuery, setSearchQuery] = useState('');
  const searchInputRef = useRef(null);

  // Target portfolio & person for Add Holding modal
  const [addHoldingTarget, setAddHoldingTarget] = useState({
    portfolio: 'LOAN',
    person: 'MADI',
  });

  // Balance sheet info popover states
  const [showBalanceInfo, setShowBalanceInfo] = useState(false);
  const balanceInfoRef = useRef(null);
  const [showStockProfitInfo, setShowStockProfitInfo] = useState(false);
  const stockProfitInfoRef = useRef(null);

  // Modals state
  const [showAddHoldingModal, setShowAddHoldingModal] =
    useState(false);
  const [showAddLotModal, setShowAddLotModal] = useState(null); // holding object
  const [showSellModal, setShowSellModal] = useState(null); // holding object
  const [showNotesModal, setShowNotesModal] = useState(null); // holding object
  const [showMistakesModal, setShowMistakesModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showSummaryModal, setShowSummaryModal] = useState(false);
  const [showSoldModal, setShowSoldModal] = useState(false);
  const [showDividendsModal, setShowDividendsModal] = useState(false);
  const [editTarget, setEditTarget] = useState(null); // { holding, lot, isSingleEntry, isHoldingOnly }

  // Forms state
  const [editForm, setEditForm] = useState({
    symbol: '',
    stock_name: '',
    scheme_name: '',
    name_confirmed: true,
    person: 'MADI',
    holding_remarks: '',
    invest_date: '',
    quantity: '',
    avg_price: '',
    invested_amount: '',
    buy_charge: '',
    remarks: '',
    manual_override_invested: false,
    manual_override_buy_charge: false,
  });
  const [holdingForm, setHoldingForm] = useState({
    symbol: '',
    stock_name: '',
    scheme_name: '',
    name_confirmed: false,
    invest_date: new Date().toISOString().slice(0, 10),
    quantity: '',
    avg_price: '',
    person: 'MADI',
    remarks: '',
    bought_reason: '',
  });

  const addLookup = useTickerLookup();
  const editLookup = useTickerLookup();
  const lookupStatus = addLookup.lookupStatus;
  const [loanSummary, setLoanSummary] = useState(null);

  const [lotForm, setLotForm] = useState({
    invest_date: new Date().toISOString().slice(0, 10),
    quantity: '',
    avg_price: '',
    remarks: '',
  });

  const [sellForm, setSellForm] = useState({
    sell_date: new Date().toISOString().slice(0, 10),
    sell_price: '',
    quantity: '',
    remarks: '',
    sold_reason: '',
    mistake_learned: '',
  });

  const [notesForm, setNotesForm] = useState({
    bought_reason: '',
    sold_reason: '',
    mistake_learned: '',
  });

  const [divForm, setDivForm] = useState({
    symbol: '',
    value: '',
    received_date: new Date().toISOString().slice(0, 10),
  });

  const [importFile, setImportFile] = useState(null);
  const [replaceConfirm, setReplaceConfirm] = useState(false);
  const [importReport, setImportReport] = useState(null);
  const [summaryRows, setSummaryRows] = useState([]);
  const [mistakesList, setMistakesList] = useState([]);

  // Fetch data
  const loadPortfolioData = useCallback(
    async (port = activePortfolio) => {
      setLoading(true);
      try {
        const res = await api.fetchPortfolioTracker(port);
        if (res && res.ok) {
          setData(res);
          if (res.summary) {
            setLoanSummary(res.summary);
          }
        }
        if (port !== 'LOAN') {
          api
            .fetchPortfolioTracker('LOAN')
            .then((loanRes) => {
              if (loanRes && loanRes.ok && loanRes.summary) {
                setLoanSummary(loanRes.summary);
              }
            })
            .catch(() => {});
        }
      } catch (err) {
        showToast(
          err.message || 'Failed to load portfolio tracker data.',
          true,
        );
      } finally {
        setLoading(false);
      }
    },
    [activePortfolio, showToast],
  );

  const handleTickerLookup = (sym) => {
    addLookup.handleLookup(
      sym,
      (res) => {
        setHoldingForm((prev) => ({
          ...prev,
          stock_name: res.name || prev.stock_name || prev.scheme_name,
          scheme_name: res.name || prev.scheme_name,
          name_confirmed: true,
        }));
      },
      () => {
        setHoldingForm((prev) => ({
          ...prev,
          name_confirmed: false,
        }));
      },
    );
  };

  useEffect(() => {
    loadPortfolioData(activePortfolio);
  }, [activePortfolio, loadPortfolioData]);

  // Global Ctrl+F / Cmd+F shortcut to focus table search
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        if (searchInputRef.current) {
          searchInputRef.current.focus();
          searchInputRef.current.select();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Click outside to dismiss balance sheet info popovers
  useEffect(() => {
    if (!showBalanceInfo && !showStockProfitInfo) return;
    const handleClickOutside = (e) => {
      if (balanceInfoRef.current && !balanceInfoRef.current.contains(e.target)) {
        setShowBalanceInfo(false);
      }
      if (stockProfitInfoRef.current && !stockProfitInfoRef.current.contains(e.target)) {
        setShowStockProfitInfo(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showBalanceInfo, showStockProfitInfo]);

  // Handle Excel download for All or active tab with proper feedback
  const handleExport = async (portfolioScope = '') => {
    const scopeKey = portfolioScope || 'all';
    setExportingScope(scopeKey);
    try {
      const url = api.getExportUrl(portfolioScope, 'xlsx');
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`Export failed with status ${res.status}: ${res.statusText}`);
      }
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = blobUrl;
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
      const portLabel = portfolioScope ? portfolioScope.toUpperCase() : 'ALL';
      let filename = `Portfolio_Tracker_${portLabel}_${stamp}.xlsx`;
      const cd = res.headers.get('content-disposition');
      if (cd && cd.includes('filename=')) {
        const match = cd.match(/filename=["']?([^"';]+)["']?/);
        if (match && match[1]) filename = match[1].trim();
      }
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        window.URL.revokeObjectURL(blobUrl);
        if (a.parentNode) {
          a.parentNode.removeChild(a);
        }
      }, 1500);
      showToast(
        portfolioScope
          ? `Exported ${portfolioScope} portfolio Excel sheet successfully.`
          : 'Exported all portfolios Excel workbook successfully.'
      );
    } catch (err) {
      showToast(err.message || 'Export failed.', true);
    } finally {
      setExportingScope(null);
    }
  };

  // Open Add Holding modal for specific portfolio & person
  const openAddHolding = (port = activePortfolio, person = 'MADI') => {
    setAddHoldingTarget({ portfolio: port, person });
    addLookup.resetLookup();
    setHoldingForm({
      symbol: '',
      stock_name: '',
      scheme_name: '',
      name_confirmed: false,
      invest_date: new Date().toISOString().slice(0, 10),
      quantity: '',
      avg_price: '',
      person: port === 'LOAN' ? person : (port === 'BAPA' ? 'BAPA' : 'MADI'),
      remarks: '',
      bought_reason: '',
    });
    setShowAddHoldingModal(true);
  };

  // Expand / collapse lot toggle
  const toggleExpand = (holdingId) => {
    setExpandedHoldings((prev) => ({
      ...prev,
      [holdingId]: !prev[holdingId],
    }));
  };

  // Expand / collapse sold group toggle
  const toggleExpandSold = (groupKey) => {
    setExpandedSoldHoldings((prev) => ({
      ...prev,
      [groupKey]: !prev[groupKey],
    }));
  };

  // Add holding submit
  const handleAddHoldingSubmit = async (e) => {
    e.preventDefault();
    try {
      const targetPort = addHoldingTarget.portfolio || activePortfolio;
      const finalStockName = (holdingForm.stock_name || holdingForm.scheme_name || '').trim();
      await api.addPortfolioHolding({
        portfolio: targetPort,
        symbol: holdingForm.symbol.trim().toUpperCase(),
        stock_name: finalStockName,
        scheme_name: finalStockName,
        name_confirmed: holdingForm.name_confirmed,
        invest_date: holdingForm.invest_date,
        quantity: parseFloat(holdingForm.quantity),
        avg_price: parseFloat(holdingForm.avg_price),
        person:
          targetPort === 'LOAN' ? holdingForm.person : null,
        remarks: holdingForm.remarks.trim(),
        bought_reason: holdingForm.bought_reason.trim(),
      });
      showToast(
        `Added holding for ${holdingForm.symbol} to ${targetPort}${
          targetPort === 'LOAN' ? ` (${holdingForm.person})` : ''
        }.`,
      );
      setShowAddHoldingModal(false);
      addLookup.resetLookup();
      setHoldingForm({
        symbol: '',
        stock_name: '',
        scheme_name: '',
        name_confirmed: false,
        invest_date: new Date().toISOString().slice(0, 10),
        quantity: '',
        avg_price: '',
        person: 'MADI',
        remarks: '',
        bought_reason: '',
      });
      if (targetPort !== activePortfolio) {
        setActivePortfolio(targetPort);
      } else {
        loadPortfolioData(targetPort);
      }
    } catch (err) {
      showToast(err.message, true);
    }
  };

  // Add lot submit
  const handleAddLotSubmit = async (e) => {
    e.preventDefault();
    if (!showAddLotModal) return;
    try {
      await api.addPortfolioLot({
        holding_id: showAddLotModal.id,
        invest_date: lotForm.invest_date,
        quantity: parseFloat(lotForm.quantity),
        avg_price: parseFloat(lotForm.avg_price),
        remarks: lotForm.remarks.trim(),
      });
      showToast(`Added buy lot for ${showAddLotModal.symbol}.`);
      setShowAddLotModal(null);
      setLotForm({
        invest_date: new Date().toISOString().slice(0, 10),
        quantity: '',
        avg_price: '',
        remarks: '',
      });
      loadPortfolioData();
    } catch (err) {
      showToast(err.message, true);
    }
  };

  // Delete holding
  const handleDeleteHolding = async (holding) => {
    if (
      !window.confirm(
        `Delete ${holding.symbol} (${holding.scheme_name}) from holdings?`,
      )
    )
      return;
    try {
      await api.deletePortfolioHolding(holding.id);
      showToast(`Deleted ${holding.symbol}.`);
      loadPortfolioData();
    } catch (err) {
      showToast(err.message, true);
    }
  };

  // Delete lot
  const handleDeleteLot = async (lot, holdingSymbol) => {
    if (
      !window.confirm(
        `Delete buy lot of ${lot.quantity} shares at ₹${lot.avg_price}?`,
      )
    )
      return;
    try {
      await api.deletePortfolioLot(lot.id);
      showToast(`Deleted buy lot for ${holdingSymbol}.`);
      loadPortfolioData();
    } catch (err) {
      showToast(err.message, true);
    }
  };

  // Open Edit Holding / Lot modal
  const openEditHoldingOrLot = (holding, lot = null) => {
    const isHoldingOnly = lot === null && holding.lots && holding.lots.length > 1;
    const isSingleEntry = !holding.lots || holding.lots.length <= 1;
    const targetLot = lot || (isSingleEntry && holding.lots ? holding.lots[0] : null);

    const q = targetLot ? targetLot.quantity : '';
    const avg = targetLot ? targetLot.avg_price : '';
    const expectedInv = (parseFloat(q) || 0) * (parseFloat(avg) || 0);
    const storedInv = targetLot ? targetLot.invested_amount : '';
    const hasManualInv =
      storedInv !== null &&
      storedInv !== undefined &&
      storedInv !== '' &&
      Math.abs(parseFloat(storedInv) - expectedInv) > 0.01;
    const storedBc = targetLot ? targetLot.buy_charge : '';
    const hasManualBc = storedBc !== null && storedBc !== undefined && storedBc !== '';

    setEditTarget({
      holding,
      lot: targetLot,
      isSingleEntry,
      isHoldingOnly,
    });

    const stockNameVal = holding.stock_name || holding.scheme_name || holding.symbol || '';
    const hasValidName = Boolean(
      holding.stock_name &&
      holding.stock_name.trim().toUpperCase() !== (holding.symbol || '').trim().toUpperCase()
    );
    editLookup.resetLookup(
      hasValidName
        ? { loading: false, found: true, message: `Current: ${stockNameVal}` }
        : { loading: false, found: null, message: '' }
    );

    setEditForm({
      symbol: holding.symbol || '',
      stock_name: stockNameVal,
      scheme_name: holding.scheme_name || holding.symbol || '',
      name_confirmed: Boolean(holding.name_confirmed || hasValidName),
      person: holding.person || 'MADI',
      holding_remarks: holding.remarks || '',
      invest_date: targetLot?.invest_date || new Date().toISOString().slice(0, 10),
      quantity: q,
      avg_price: avg,
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
      remarks: targetLot?.remarks || '',
      manual_override_invested: hasManualInv,
      manual_override_buy_charge: hasManualBc,
    });
  };

  // Submit Edit Holding / Lot
  const handleEditSubmit = async (e) => {
    e.preventDefault();
    if (!editTarget) return;
    try {
      const { holding, lot, isSingleEntry, isHoldingOnly } = editTarget;

      // 1. If updating lot
      if (!isHoldingOnly && lot) {
        const q = parseFloat(editForm.quantity);
        const avg = parseFloat(editForm.avg_price);
        if (isNaN(q) || q <= 0 || isNaN(avg) || avg <= 0) {
          showToast('Quantity and Avg Price must be positive numbers.', true);
          return;
        }

        await api.updatePortfolioLot(lot.id, {
          invest_date: editForm.invest_date,
          quantity: q,
          avg_price: avg,
          invested_amount:
            editForm.manual_override_invested && editForm.invested_amount !== ''
              ? parseFloat(editForm.invested_amount)
              : null,
          buy_charge:
            editForm.manual_override_buy_charge && editForm.buy_charge !== ''
              ? parseFloat(editForm.buy_charge)
              : null,
          remarks: editForm.remarks.trim(),
        });
      }

      // 2. If updating holding metadata (single-entry or holding-only)
      if (isHoldingOnly || isSingleEntry) {
        if (editLookup.lookupStatus.found === false && !editForm.name_confirmed) {
          showToast('Please confirm the stock name before saving.', true);
          return;
        }
        const finalStockName = (editForm.stock_name || editForm.scheme_name || '').trim();
        await api.updatePortfolioHolding(holding.id, {
          symbol: editForm.symbol.trim().toUpperCase(),
          stock_name: finalStockName,
          scheme_name: finalStockName,
          name_confirmed: Boolean(editForm.name_confirmed),
          person: activePortfolio === 'LOAN' ? editForm.person : null,
          remarks: editForm.holding_remarks.trim(),
        });
      }

      showToast('Holding entry updated successfully.');
      setEditTarget(null);
      loadPortfolioData(activePortfolio);
    } catch (err) {
      showToast(err.message || 'Failed to update entry.', true);
    }
  };

  // Sell submit
  const handleSellSubmit = async (e) => {
    e.preventDefault();
    if (!showSellModal) return;
    try {
      await api.sellPortfolioHolding({
        holding_id: showSellModal.id,
        sell_date: sellForm.sell_date,
        sell_price: parseFloat(sellForm.sell_price),
        quantity: sellForm.quantity
          ? parseFloat(sellForm.quantity)
          : null,
        remarks: sellForm.remarks.trim(),
        sold_reason: sellForm.sold_reason.trim(),
        mistake_learned: sellForm.mistake_learned.trim(),
      });
      showToast(`Sold position in ${showSellModal.symbol}.`);
      setShowSellModal(null);
      loadPortfolioData();
    } catch (err) {
      showToast(err.message, true);
    }
  };

  // Notes update submit
  const handleNotesSubmit = async (e) => {
    e.preventDefault();
    if (!showNotesModal) return;
    try {
      await api.updatePortfolioNotes(showNotesModal.id, notesForm);
      showToast(`Updated notes for ${showNotesModal.symbol}.`);
      setShowNotesModal(null);
      loadPortfolioData();
    } catch (err) {
      showToast(err.message, true);
    }
  };

  // Add dividend submit
  const handleAddDividend = async (e) => {
    e.preventDefault();
    if (!divForm.symbol || !divForm.value) return;
    try {
      await api.addPortfolioDividend({
        portfolio: activePortfolio,
        symbol: divForm.symbol.trim().toUpperCase(),
        value: parseFloat(divForm.value),
        received_date: divForm.received_date,
      });
      showToast(
        `Recorded dividend of ₹${divForm.value} for ${divForm.symbol}.`,
      );
      setDivForm({
        symbol: '',
        value: '',
        received_date: new Date().toISOString().slice(0, 10),
      });
      loadPortfolioData();
    } catch (err) {
      showToast(err.message, true);
    }
  };

  // Delete dividend
  const handleDeleteDividend = async (divItem) => {
    if (
      !window.confirm(
        `Delete dividend of ₹${divItem.value} for ${divItem.symbol}?`,
      )
    )
      return;
    try {
      await api.deletePortfolioDividend(divItem.id);
      showToast(`Deleted dividend for ${divItem.symbol}.`);
      loadPortfolioData();
    } catch (err) {
      showToast(err.message, true);
    }
  };

  // Import submit
  const handleImportSubmit = async (e) => {
    e.preventDefault();
    try {
      const res = await api.importPortfolioWorkbook(
        importFile,
        replaceConfirm,
      );
      if (res.requires_confirmation) {
        showToast(res.message, true);
        return;
      }
      if (res.ok) {
        setImportReport(res);
        showToast('Workbook imported successfully.');
        loadPortfolioData();
      } else {
        showToast(res.message || res.error || 'Import failed.', true);
      }
    } catch (err) {
      showToast(err.message, true);
    }
  };

  // Open summary edit modal
  const openSummaryEdit = async () => {
    try {
      const res = await api.fetchPortfolioSummary();
      if (res && res.values) {
        setSummaryRows(res.values);
        setShowSummaryModal(true);
      }
    } catch (err) {
      showToast('Failed to load summary values.', true);
    }
  };

  // Update summary field
  const handleSaveSummaryRow = async (key, val, label) => {
    try {
      await api.updatePortfolioSummary(
        key,
        parseFloat(val || 0),
        label,
      );
      showToast(`Updated ${label}.`);
      loadPortfolioData();
    } catch (err) {
      showToast(err.message, true);
    }
  };

  // Open mistakes modal
  const openMistakes = async () => {
    try {
      const res = await api.fetchPortfolioMistakes();
      if (res && res.mistakes) {
        setMistakesList(res.mistakes);
        setShowMistakesModal(true);
      }
    } catch (err) {
      showToast('Failed to load lessons.', true);
    }
  };

  const openHoldings = data?.open_holdings || [];
  const soldHoldings = data?.sold_holdings || [];
  const openTotals = data?.open_totals || {};
  const soldTotals = data?.sold_totals || {};
  const dividends = data?.dividends || [];
  const summaryData = data?.summary || null;

  const sortedOpenHoldings = useMemo(() => {
    return [...openHoldings].sort((a, b) =>
      (a.first_invest_date || a.invest_date || '').localeCompare(
        b.first_invest_date || b.invest_date || '',
      ),
    );
  }, [openHoldings]);

  // Real-time search filtered open holdings
  const filteredOpenHoldings = useMemo(() => {
    if (!searchQuery.trim()) return sortedOpenHoldings;
    const q = searchQuery.trim().toLowerCase();
    return sortedOpenHoldings.filter((h) => {
      const scheme = (h.scheme_name || '').toLowerCase();
      const symbol = (h.symbol || '').toLowerCase();
      return scheme.includes(q) || symbol.includes(q);
    });
  }, [sortedOpenHoldings, searchQuery]);

  // Count total un-filtered holdings per person in LOAN
  const allLoanPersonCounts = useMemo(() => {
    if (activePortfolio !== 'LOAN') return { madi: 0, bapa: 0, other: 0 };
    let madi = 0;
    let bapa = 0;
    let other = 0;
    for (const h of sortedOpenHoldings) {
      const personStr = `${h.person || ''} ${h.app || ''}`.toUpperCase();
      if (personStr.includes('MADI')) madi++;
      else if (personStr.includes('BAPA')) bapa++;
      else other++;
    }
    return { madi, bapa, other };
  }, [sortedOpenHoldings, activePortfolio]);

  const loanOpenGroups = useMemo(() => {
    if (activePortfolio !== 'LOAN') return null;
    const madi = [];
    const bapa = [];
    const other = [];

    for (const h of filteredOpenHoldings) {
      const personStr = `${h.person || ''} ${h.app || ''}`.toUpperCase();
      if (personStr.includes('MADI')) {
        madi.push(h);
      } else if (personStr.includes('BAPA')) {
        bapa.push(h);
      } else {
        other.push(h);
      }
    }

    const calcTotals = (list) => ({
      invested: list.reduce((sum, h) => sum + (h.invested_amount || 0), 0),
      current: list.reduce((sum, h) => sum + (h.current_total || 0), 0),
      earned: list.reduce((sum, h) => sum + (h.earned || 0), 0),
      loss: list.reduce((sum, h) => sum + (h.loss || 0), 0),
    });

    return {
      madi,
      bapa,
      other,
      madiTotals: calcTotals(madi),
      bapaTotals: calcTotals(bapa),
      otherTotals: calcTotals(other),
    };
  }, [filteredOpenHoldings, activePortfolio]);

  // Dynamic openTotals computed for filtered items
  const filteredOpenTotals = useMemo(() => {
    let inv = 0;
    let cur = 0;
    let earned = 0;
    let loss = 0;

    if (!searchQuery.trim() && openTotals && Object.keys(openTotals).length > 0) {
      inv = openTotals.invested_amount || 0;
      cur = openTotals.current_total || 0;
      earned = openTotals.earned || 0;
      loss = openTotals.loss || 0;
    } else {
      inv = filteredOpenHoldings.reduce(
        (sum, h) => sum + (h.invested_amount || 0),
        0,
      );
      cur = filteredOpenHoldings.reduce(
        (sum, h) => sum + (h.current_total || 0),
        0,
      );
      earned = filteredOpenHoldings.reduce(
        (sum, h) => sum + (h.earned || 0),
        0,
      );
      loss = filteredOpenHoldings.reduce(
        (sum, h) => sum + (h.loss || 0),
        0,
      );
    }

    const netProfit = earned + (loss <= 0 ? loss : -loss);

    return {
      invested_amount: inv,
      current_total: cur,
      earned,
      loss,
      net_profit: Math.round(netProfit * 100) / 100,
    };
  }, [filteredOpenHoldings, searchQuery, openTotals]);

  useEffect(() => {
    const updateWidth = () => {
      if (openTableContainerRef.current) {
        setOpenTableScrollWidth(openTableContainerRef.current.scrollWidth);
      }
    };
    const timer = setTimeout(updateWidth, 60);
    window.addEventListener('resize', updateWidth);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', updateWidth);
    };
  }, [openHoldings, expandedHoldings, activePortfolio]);

  const handleOpenTableScroll = () => {
    if (openTopScrollRef.current && openTableContainerRef.current) {
      openTopScrollRef.current.scrollLeft =
        openTableContainerRef.current.scrollLeft;
    }
  };

  const handleOpenTopScroll = () => {
    if (openTableContainerRef.current && openTopScrollRef.current) {
      openTableContainerRef.current.scrollLeft =
        openTopScrollRef.current.scrollLeft;
    }
  };

  const groupedSoldHoldings = useMemo(() => {
    if (!soldHoldings || soldHoldings.length === 0) return [];
    const groupsMap = new Map();
    for (const s of soldHoldings) {
      const rawKey = (s.scheme_name || s.symbol || '').trim();
      const key = rawKey.toUpperCase();
      if (!groupsMap.has(key)) {
        groupsMap.set(key, {
          key,
          rawKey,
          symbol: s.symbol,
          scheme_name: s.scheme_name || s.symbol,
          entries: [],
        });
      }
      groupsMap.get(key).entries.push(s);
    }

    const result = Array.from(groupsMap.values()).map((g) => {
      // Sort individual trade entries: most recent sell date first
      g.entries.sort((a, b) => (b.sell_date || '').localeCompare(a.sell_date || ''));

      if (g.entries.length === 1) {
        const single = g.entries[0];
        return {
          ...single,
          groupKey: g.key,
          hasMultipleSales: false,
          entries: g.entries,
          sort_sell_date: single.sell_date || '',
        };
      }

      let totalQty = 0;
      let totalInvested = 0;
      let totalExit = 0;
      let totalBuyCharge = 0;
      let totalSellCharge = 0;
      let totalEarned = 0;
      let totalLoss = 0;
      const investDates = [];
      const sellDates = [];
      const persons = new Set();
      const remarksList = [];

      for (const item of g.entries) {
        const q = parseFloat(item.quantity) || 0;
        const inv = parseFloat(item.invested_amount) || 0;
        const ext = parseFloat(item.current_total) || 0;
        const bc = parseFloat(item.buy_charge) || 0;
        const sc = parseFloat(item.sell_charge) || 0;
        const er = parseFloat(item.earned) || 0;
        const ls = parseFloat(item.loss) || 0;

        totalQty += q;
        totalInvested += inv;
        totalExit += ext;
        totalBuyCharge += bc;
        totalSellCharge += sc;
        totalEarned += er;
        totalLoss += ls;

        if (item.invest_date) investDates.push(item.invest_date);
        if (item.sell_date) sellDates.push(item.sell_date);
        if (item.person) persons.add(item.person);
        else if (item.app) persons.add(item.app);
        const rem = item.sale_remarks || item.remarks;
        if (rem && rem.trim() && !remarksList.includes(rem.trim())) {
          remarksList.push(rem.trim());
        }
      }

      investDates.sort();
      sellDates.sort();
      const firstInvestDate = investDates[0] || '';
      const firstSellDate = sellDates[0] || '';
      const lastSellDate = sellDates[sellDates.length - 1] || '';
      let { years, months } = calculatePeriod(firstInvestDate, lastSellDate);
      if (months === 0) {
        const maxMonths = Math.max(...g.entries.map((e) => e.months || 0));
        if (maxMonths > 0) {
          months = maxMonths;
          years = Math.floor(months / 12);
        }
      }

      const avgPrice = totalQty > 0 ? totalInvested / totalQty : 0;
      const exitLtp = totalQty > 0 ? totalExit / totalQty : 0;

      let totalReturn = 0;
      let annualReturn = null;
      if (totalInvested > 0) {
        totalReturn = ((totalExit / totalInvested) - 1.0) * 100.0;
        const yearsFloat = months / 12.0;
        if (yearsFloat >= 1.0 && totalExit > 0) {
          try {
            annualReturn =
              (Math.pow(totalExit / totalInvested, 1.0 / yearsFloat) - 1.0) * 100.0;
          } catch (e) {
            annualReturn = 0;
          }
        } else if (months > 0) {
          annualReturn = totalReturn * (12.0 / months);
        }
      }

      const displaySellDate = lastSellDate || firstSellDate;

      return {
        id: `group-${g.key}`,
        groupKey: g.key,
        symbol: g.symbol,
        scheme_name: g.scheme_name,
        hasMultipleSales: true,
        entries: g.entries,
        invest_date: firstInvestDate,
        sell_date: displaySellDate,
        sort_sell_date: lastSellDate || firstSellDate,
        years,
        months,
        quantity: totalQty,
        avg_price: avgPrice,
        ltp: exitLtp,
        invested_amount: totalInvested,
        buy_charge: totalBuyCharge,
        sell_charge: totalSellCharge,
        current_total: totalExit,
        earned: totalEarned,
        loss: totalLoss,
        annual_return: annualReturn,
        total_return: totalReturn,
        person: Array.from(persons).join(', ') || '—',
        remarks: remarksList.length > 0 ? remarksList.join('; ') : '—',
        bought_reason: g.entries[0]?.bought_reason || '',
        sold_reason: g.entries[0]?.sold_reason || '',
        mistake_learned: g.entries[0]?.mistake_learned || '',
      };
    });

    // Sort groups descending: most recent sell date on top
    return result.sort((a, b) =>
      (b.sort_sell_date || b.sell_date || '').localeCompare(a.sort_sell_date || a.sell_date || ''),
    );
  }, [soldHoldings]);

  const renderOpenHoldingRow = (h) => {
    const isExpanded = !!expandedHoldings[h.id];
    const hasMultipleLots = h.lots && h.lots.length > 1;
    const isPositive = h.total_return >= 0;

    return (
      <React.Fragment key={h.id}>
        <tr className={hasMultipleLots ? 'multi-entry-row' : ''}>
          <td className='col-sticky-ticker col-sticky-scheme'>
            <div className='ticker-cell-content'>
              <strong title={h.symbol}>{h.symbol || h.scheme_name}</strong>
              <span
                className='stock-info-tooltip-trigger'
                tabIndex={0}
                title={h.stock_name || h.scheme_name || 'Name not available'}
                aria-label={h.stock_name || h.scheme_name || 'Name not available'}
              >
                <Info size={13} className='stock-info-icon' />
                <span className='stock-name-tooltip' role='tooltip'>
                  {h.stock_name || h.scheme_name || 'Name not available'}
                </span>
              </span>
              {hasMultipleLots && (
                <span
                  className='entry-count-badge'
                  title={`${h.lots.length} buy entries`}
                >
                  {h.lots.length}
                </span>
              )}
              {hasMultipleLots && (
                <button
                  type='button'
                  className='expand-chevron-btn'
                  onClick={() => toggleExpand(h.id)}
                  title={
                    isExpanded
                      ? 'Collapse buy entries'
                      : 'Expand buy entries'
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
          <td>{formatDate(h.first_invest_date)}</td>
          {SHOW_CURRENT_DATE && (
            <td>
              {formatDate(h.current_date ||
                new Date().toISOString().slice(0, 10))}
            </td>
          )}
          <td className='text-end'>{h.years}</td>
          <td className='text-end'>{h.months}</td>

          <td className='text-end fw-semibold'>
            {h.quantity.toLocaleString()}
          </td>
          <td className='text-end'>
            ₹{h.avg_price.toFixed(2)}
          </td>
          <td className='text-end fw-bold'>
            ₹{h.ltp.toFixed(2)}
          </td>
          <td className='text-end'>
            ₹{h.invested_amount.toLocaleString()}
          </td>
          <td
            className='text-end text-muted'
            style={{ fontSize: '0.8rem' }}
          >
            ₹{h.buy_charge}
          </td>
          <td
            className='text-end text-muted'
            style={{ fontSize: '0.8rem' }}
          >
            ₹{h.sell_charge}
          </td>
          <td className='text-end fw-bold'>
            ₹{h.current_total.toLocaleString()}
          </td>
          <td className='text-end text-success'>
            {h.earned > 0
              ? `+₹${h.earned.toLocaleString()}`
              : '—'}
          </td>
          <td className='text-end text-danger'>
            {h.loss < 0
              ? `-₹${Math.abs(h.loss).toLocaleString()}`
              : '—'}
          </td>
          <td className='text-end'>
            {h.annual_return ? (
              <span
                className={
                  h.annual_return >= 0
                    ? 'text-success'
                    : 'text-danger'
                }
              >
                {h.annual_return > 0 ? '+' : ''}
                {h.annual_return.toFixed(2)}%
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
              {h.total_return.toFixed(2)}%
            </span>
          </td>
          <td
            className='text-muted'
            style={{
              minWidth: '150px',
              maxWidth: '240px',
              whiteSpace: 'normal',
              wordBreak: 'break-word',
            }}
          >
            {h.remarks || '—'}
          </td>
          <td className='text-center'>
            <div className='btn-group btn-group-sm'>
              <button
                type='button'
                className='btn btn-outline-primary'
                title={hasMultipleLots ? 'Edit Holding Info' : 'Edit Holding & Lot'}
                onClick={() =>
                  openEditHoldingOrLot(
                    h,
                    hasMultipleLots ? null : (h.lots && h.lots[0]),
                  )
                }
              >
                <Edit3 size={13} />
              </button>
              <button
                type='button'
                className='btn btn-outline-primary'
                title='Add Buy Lot'
                onClick={() => setShowAddLotModal(h)}
              >
                <Plus size={13} />
              </button>
              <button
                type='button'
                className='btn btn-outline-warning'
                title='Sell Stock'
                onClick={() => {
                  setSellForm({
                    sell_date: new Date()
                      .toISOString()
                      .slice(0, 10),
                    sell_price: h.ltp || h.avg_price,
                    quantity: h.quantity,
                    remarks: h.remarks || '',
                    sold_reason: '',
                    mistake_learned: '',
                  });
                  setShowSellModal(h);
                }}
              >
                Sell
              </button>
              <button
                type='button'
                className='btn btn-outline-secondary'
                title='Notes & Lessons'
                onClick={() => {
                  setNotesForm({
                    bought_reason:
                      h.bought_reason || '',
                    sold_reason: h.sold_reason || '',
                    mistake_learned:
                      h.mistake_learned || '',
                  });
                  setShowNotesModal(h);
                }}
              >
                <FileText size={13} />
              </button>
              <button
                type='button'
                className='btn btn-outline-danger'
                title='Delete Holding'
                onClick={() => handleDeleteHolding(h)}
              >
                <Trash2 size={13} />
              </button>
            </div>
          </td>
        </tr>

        {/* Expanded Child Lots */}
        {isExpanded && hasMultipleLots && h.lots && h.lots.map((lot, idx) => {
          const isLotPositive = lot.total_return >= 0;
          const isLastChild = idx === h.lots.length - 1;
          return (
            <tr
              key={`lot-${lot.id}`}
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
                {formatDate(lot.invest_date)}
              </td>
              {SHOW_CURRENT_DATE && (
                <td>
                  {formatDate(
                    lot.current_date ||
                      h.current_date ||
                      new Date().toISOString().slice(0, 10),
                  )}
                </td>
              )}
              <td className='text-end'>{lot.years}</td>
              <td className='text-end'>{lot.months}</td>
              <td className='text-end fw-semibold'>
                {lot.quantity?.toLocaleString()}
              </td>
              <td className='text-end'>₹{lot.avg_price?.toFixed(2)}</td>
              <td className='text-end fw-bold'>
                ₹{h.ltp ? h.ltp.toFixed(2) : lot.avg_price?.toFixed(2)}
              </td>
              <td className='text-end'>
                ₹{lot.invested_amount?.toLocaleString()}
              </td>
              <td
                className='text-end text-muted'
                style={{ fontSize: '0.8rem' }}
              >
                ₹{lot.buy_charge}
              </td>
              <td
                className='text-end text-muted'
                style={{ fontSize: '0.8rem' }}
              >
                ₹{lot.sell_charge}
              </td>
              <td className='text-end fw-bold'>
                ₹{lot.current_total?.toLocaleString()}
              </td>
              <td className='text-end text-success'>
                {lot.earned > 0
                  ? `+₹${lot.earned.toLocaleString()}`
                  : '—'}
              </td>
              <td className='text-end text-danger'>
                {lot.loss < 0
                  ? `-₹${Math.abs(lot.loss).toLocaleString()}`
                  : '—'}
              </td>
              <td className='text-end'>
                {lot.annual_return ? (
                  <span
                    className={
                      lot.annual_return >= 0
                        ? 'text-success'
                        : 'text-danger'
                    }
                  >
                    {lot.annual_return > 0 ? '+' : ''}
                    {lot.annual_return.toFixed(2)}%
                  </span>
                ) : (
                  '—'
                )}
              </td>
              <td className='text-end'>
                <span
                  className={`badge ${isLotPositive ? 'bg-success' : 'bg-danger'}`}
                  style={{ fontSize: '0.8rem' }}
                >
                  {isLotPositive ? '+' : ''}
                  {lot.total_return?.toFixed(2)}%
                </span>
              </td>
              <td
                className='text-muted'
                style={{
                  minWidth: '150px',
                  maxWidth: '240px',
                  whiteSpace: 'normal',
                  wordBreak: 'break-word',
                }}
              >
                {lot.remarks || '—'}
              </td>
              <td className='text-center'>
                <div className='btn-group btn-group-sm'>
                  <button
                    type='button'
                    className='btn btn-outline-primary'
                    onClick={() => openEditHoldingOrLot(h, lot)}
                    title='Edit Buy Lot'
                  >
                    <Edit3 size={13} />
                  </button>
                  <button
                    type='button'
                    className='btn btn-outline-danger'
                    onClick={() => handleDeleteLot(lot, h.symbol)}
                    title='Delete Lot'
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </td>
            </tr>
          );
        })}
      </React.Fragment>
    );
  };

  return (
    <div className='portfolio-tracker-container'>
      {/* Portfolio Selector & Top Actions */}
      <div className='d-flex flex-wrap justify-content-between align-items-center mb-4 gap-2'>
        <div
          className='btn-group'
          role='group'
        >
          {['LOAN', 'MADI', 'BAPA'].map((port) => (
            <button
              key={port}
              type='button'
              className={`btn ${activePortfolio === port ? 'btn-primary' : 'btn-outline-secondary'}`}
              onClick={() => setActivePortfolio(port)}
            >
              <FolderCheck
                size={16}
                className='me-1 inline-block'
              />
              <strong>{port}</strong>
            </button>
          ))}
        </div>

        <div className='d-flex flex-wrap gap-2'>
          <button
            type='button'
            className='btn btn-sm btn-outline-primary'
            onClick={openMistakes}
          >
            <BookOpen
              size={15}
              className='me-1 inline-block'
            />
            Mistakes & Lessons
          </button>

          {/* Export Scoping & Formats (§1.3) */}
          <div className='btn-group btn-group-sm'>
            <button
              type='button'
              className='btn btn-outline-secondary'
              onClick={() => handleExport('')}
              disabled={Boolean(exportingScope)}
              title='Download full Excel workbook with all portfolios matching Invest.xlsx'
            >
              {exportingScope === 'all' ? (
                <span
                  className='spinner-border spinner-border-sm me-1'
                  role='status'
                />
              ) : (
                <Download
                  size={14}
                  className='me-1 inline-block'
                />
              )}
              Excel (All)
            </button>
            <button
              type='button'
              className='btn btn-outline-secondary'
              onClick={() => handleExport(activePortfolio)}
              disabled={Boolean(exportingScope)}
              title={`Download Excel workbook for ${activePortfolio} only`}
            >
              {exportingScope === activePortfolio ? (
                <span
                  className='spinner-border spinner-border-sm me-1'
                  role='status'
                />
              ) : (
                <Download
                  size={14}
                  className='me-1 inline-block'
                />
              )}
              {activePortfolio} (.xlsx)
            </button>
          </div>

          {SHOW_IMPORT_BUTTON && (
            <button
              type='button'
              className='btn btn-sm btn-outline-secondary'
              onClick={() => {
                setImportReport(null);
                setShowImportModal(true);
              }}
            >
              <Upload
                size={15}
                className='me-1 inline-block'
              />
              Import Sheet
            </button>
          )}


        </div>
      </div>

      {loading && (
        <div className='text-center py-4'>
          <div
            className='spinner-border spinner-border-sm text-primary me-2'
            role='status'
          />
          <span>Loading {activePortfolio} portfolio tracker...</span>
        </div>
      )}

      {/* 1. Open Holdings Table */}
      <div className='dashboard-card mb-4'>
        <div className='card-header d-flex flex-wrap justify-content-between align-items-center py-2 px-3 border-bottom gap-3'>
          {/* Title, Counts & Search */}
          <div className='d-flex flex-wrap align-items-center gap-3'>
            <div className='d-flex align-items-center gap-2'>
              <h5 className='mb-0 fw-bold text-nowrap'>
                Open Holdings — {activePortfolio}
              </h5>
              <span className='badge bg-primary rounded-pill'>
                {filteredOpenHoldings.length}
                {filteredOpenHoldings.length !== openHoldings.length
                  ? ` / ${openHoldings.length}`
                  : ''}
              </span>
            </div>

            {/* Real-time Table Search (Ctrl+F shortcut supported) */}
            <div
              className='input-group input-group-sm'
              style={{ width: '270px' }}
            >
              <span className='input-group-text bg-white border-end-0 text-muted'>
                <Search size={14} />
              </span>
              <input
                ref={searchInputRef}
                type='text'
                className='form-control border-start-0 ps-0'
                placeholder='Search scheme or symbol... (Ctrl+F)'
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
          </div>

          {/* Action buttons with Dedicated Add Holding buttons per portfolio */}
          <div className='d-flex flex-wrap align-items-center gap-2'>
            <button
              type='button'
              className='btn btn-sm btn-primary d-flex align-items-center gap-1 shadow-sm'
              onClick={() => openAddHolding(activePortfolio)}
              title={`Add new open holding to ${activePortfolio}`}
            >
              <Plus size={15} />
              <span>Add Holding</span>
            </button>

            <div
              className='vr mx-1 d-none d-md-block'
              style={{ height: '22px' }}
            />

            <button
              type='button'
              className='btn btn-sm btn-outline-secondary d-flex align-items-center gap-1 shadow-sm'
              onClick={() => setShowSoldModal(true)}
              title={`View sold positions history for ${activePortfolio}`}
            >
              <History size={15} />
              <span>Sold Positions</span>
              <span className='badge bg-secondary ms-1'>
                {groupedSoldHoldings.length}
              </span>
            </button>

            <button
              type='button'
              className='btn btn-sm btn-outline-success d-flex align-items-center gap-1 shadow-sm'
              onClick={() => setShowDividendsModal(true)}
              title={`View and record dividends for ${activePortfolio}`}
            >
              <DollarSign size={15} />
              <span>Dividends</span>
              <span className='badge bg-success ms-1'>
                ₹{data?.total_dividends?.toLocaleString() || 0}
              </span>
            </button>
          </div>
        </div>

        {/* Top Horizontal Scrollbar */}
        {openTableScrollWidth > 0 && (
          <div
            ref={openTopScrollRef}
            onScroll={handleOpenTopScroll}
            style={{
              overflowX: 'auto',
              overflowY: 'hidden',
              height: '14px',
              backgroundColor: '#f1f3f5',
              borderBottom: '1px solid #dee2e6',
            }}
          >
            <div style={{ width: openTableScrollWidth, height: '1px' }} />
          </div>
        )}

        <div
          ref={openTableContainerRef}
          onScroll={handleOpenTableScroll}
          className='table-responsive'
          style={{
            maxHeight: '75vh',
            overflow: 'auto',
          }}
        >
          <table className='table table-hover table-striped table-sticky-tfoot align-middle mb-0 text-nowrap'>
            <thead className='table-light'>
              <tr style={{ fontSize: '0.82rem' }}>
                <th className='col-sticky-ticker col-sticky-scheme'>StockTicker</th>
                <th>Invest Date</th>
                {SHOW_CURRENT_DATE && <th>Current Date</th>}
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
                <th className='text-end'>Q</th>
                <th className='text-end'>Avg (₹)</th>
                <th className='text-end'>LTP (₹)</th>
                <th className='text-end'>Invested (₹)</th>
                <th className='text-end'>Buy Chg</th>
                <th className='text-end'>Sell Chg</th>
                <th className='text-end'>Total (₹)</th>
                <th className='text-end'>Earned (₹)</th>
                <th className='text-end'>Loss (₹)</th>
                <th className='text-end'>Annual %</th>
                <th className='text-end'>Return %</th>
                <th>Remarks</th>
                <th className='text-center'>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedOpenHoldings.length === 0 ? (
                <tr>
                  <td
                    colSpan={SHOW_CURRENT_DATE ? 18 : 17}
                    className='text-center py-4 text-muted'
                  >
                    No open holdings in {activePortfolio}. Click "Add
                    Holding" to record an investment.
                  </td>
                </tr>
              ) : activePortfolio === 'LOAN' && loanOpenGroups ? (
                <>
                  {/* MADI Section */}
                  <tr className='table-primary border-top border-bottom border-primary-subtle fw-semibold'>
                    <td colSpan={SHOW_CURRENT_DATE ? 8 : 7} className='py-2 px-3' style={{ position: 'sticky', left: 0, zIndex: 1 }}>
                      <div className='d-flex align-items-center gap-2'>
                        <span className='badge bg-primary px-2.5 py-1 text-uppercase fw-bold'>
                          MADI
                        </span>
                        <span className='text-dark'>
                          Holdings ({loanOpenGroups.madi.length}
                          {searchQuery.trim()
                            ? ` of ${allLoanPersonCounts.madi}`
                            : ''}
                          )
                        </span>
                      </div>
                    </td>
                    <td className='text-end fw-bold py-2 text-dark'>
                      <span className='text-muted small fw-normal me-1'>
                        Invested:
                      </span>
                      ₹{loanOpenGroups.madiTotals.invested.toLocaleString()}
                    </td>
                    <td colSpan={2}></td>
                    <td className='text-end fw-bold py-2 text-dark'>
                      <span className='text-muted small fw-normal me-1'>
                        Total:
                      </span>
                      ₹{loanOpenGroups.madiTotals.current.toLocaleString()}
                    </td>
                    <td colSpan={2} className='text-center fw-bold py-2'>
                      {(() => {
                        const inv = loanOpenGroups.madiTotals.invested;
                        const cur = loanOpenGroups.madiTotals.current;
                        const netPnl = cur - inv;
                        return (
                          <span
                            className={
                              netPnl >= 0 ? 'text-success' : 'text-danger'
                            }
                          >
                            <span className='text-muted small fw-normal me-1'>
                              P&L:
                            </span>
                            {netPnl >= 0 ? '+' : ''}₹
                            {netPnl.toLocaleString()}
                          </span>
                        );
                      })()}
                    </td>
                    <td colSpan={2} className='text-end py-2'>
                      {(() => {
                        const inv = loanOpenGroups.madiTotals.invested;
                        const cur = loanOpenGroups.madiTotals.current;
                        const netPnl = cur - inv;
                        const pct = inv > 0 ? (netPnl / inv) * 100 : 0;
                        return (
                          <span
                            className={`badge ${pct >= 0 ? 'bg-success' : 'bg-danger'}`}
                            title={`Net P&L: ₹${netPnl.toLocaleString()}`}
                          >
                            {pct >= 0 ? '+' : ''}
                            {pct.toFixed(2)}%
                          </span>
                        );
                      })()}
                    </td>
                    <td colSpan={2}></td>
                  </tr>
                  {loanOpenGroups.madi.length === 0 ? (
                    <tr>
                      <td
                        colSpan={SHOW_CURRENT_DATE ? 18 : 17}
                        className='text-center py-2 text-muted fst-italic bg-light'
                      >
                        {searchQuery.trim()
                          ? `No open holdings matching "${searchQuery}" for MADI`
                          : 'No open holdings for MADI'}
                      </td>
                    </tr>
                  ) : (
                    loanOpenGroups.madi.map(renderOpenHoldingRow)
                  )}

                  {/* BAPA Section */}
                  <tr className='table-info border-top border-bottom border-info-subtle fw-semibold'>
                    <td colSpan={SHOW_CURRENT_DATE ? 8 : 7} className='py-2 px-3' style={{ position: 'sticky', left: 0, zIndex: 1 }}>
                      <div className='d-flex align-items-center gap-2'>
                        <span className='badge bg-info text-dark px-2.5 py-1 text-uppercase fw-bold'>
                          BAPA
                        </span>
                        <span className='text-dark'>
                          Holdings ({loanOpenGroups.bapa.length}
                          {searchQuery.trim()
                            ? ` of ${allLoanPersonCounts.bapa}`
                            : ''}
                          )
                        </span>
                      </div>
                    </td>
                    <td className='text-end fw-bold py-2 text-dark'>
                      <span className='text-muted small fw-normal me-1'>
                        Invested:
                      </span>
                      ₹{loanOpenGroups.bapaTotals.invested.toLocaleString()}
                    </td>
                    <td colSpan={2}></td>
                    <td className='text-end fw-bold py-2 text-dark'>
                      <span className='text-muted small fw-normal me-1'>
                        Total:
                      </span>
                      ₹{loanOpenGroups.bapaTotals.current.toLocaleString()}
                    </td>
                    <td colSpan={2} className='text-center fw-bold py-2'>
                      {(() => {
                        const inv = loanOpenGroups.bapaTotals.invested;
                        const cur = loanOpenGroups.bapaTotals.current;
                        const netPnl = cur - inv;
                        return (
                          <span
                            className={
                              netPnl >= 0 ? 'text-success' : 'text-danger'
                            }
                          >
                            <span className='text-muted small fw-normal me-1'>
                              P&L:
                            </span>
                            {netPnl >= 0 ? '+' : ''}₹
                            {netPnl.toLocaleString()}
                          </span>
                        );
                      })()}
                    </td>
                    <td colSpan={2} className='text-end py-2'>
                      {(() => {
                        const inv = loanOpenGroups.bapaTotals.invested;
                        const cur = loanOpenGroups.bapaTotals.current;
                        const netPnl = cur - inv;
                        const pct = inv > 0 ? (netPnl / inv) * 100 : 0;
                        return (
                          <span
                            className={`badge ${pct >= 0 ? 'bg-success' : 'bg-danger'}`}
                            title={`Net P&L: ₹${netPnl.toLocaleString()}`}
                          >
                            {pct >= 0 ? '+' : ''}
                            {pct.toFixed(2)}%
                          </span>
                        );
                      })()}
                    </td>
                    <td colSpan={2}></td>
                  </tr>
                  {loanOpenGroups.bapa.length === 0 ? (
                    <tr>
                      <td
                        colSpan={SHOW_CURRENT_DATE ? 18 : 17}
                        className='text-center py-2 text-muted fst-italic bg-light'
                      >
                        {searchQuery.trim()
                          ? `No open holdings matching "${searchQuery}" for BAPA`
                          : 'No open holdings for BAPA'}
                      </td>
                    </tr>
                  ) : (
                    loanOpenGroups.bapa.map(renderOpenHoldingRow)
                  )}

                  {/* Other Section if present */}
                  {loanOpenGroups.other.length > 0 && (
                    <>
                      <tr className='table-secondary border-top border-bottom fw-semibold'>
                        <td colSpan={SHOW_CURRENT_DATE ? 8 : 7} className='py-2 px-3' style={{ position: 'sticky', left: 0, zIndex: 1 }}>
                          <div className='d-flex align-items-center gap-2'>
                            <span className='badge bg-secondary text-uppercase fw-bold'>
                              OTHER
                            </span>
                            <span className='text-dark'>
                              Holdings ({loanOpenGroups.other.length}
                              {searchQuery.trim()
                                ? ` of ${allLoanPersonCounts.other}`
                                : ''}
                              )
                            </span>
                          </div>
                        </td>
                        <td className='text-end fw-bold py-2 text-dark'>
                          <span className='text-muted small fw-normal me-1'>
                            Invested:
                          </span>
                          ₹{loanOpenGroups.otherTotals.invested.toLocaleString()}
                        </td>
                        <td colSpan={2}></td>
                        <td className='text-end fw-bold py-2 text-dark'>
                          <span className='text-muted small fw-normal me-1'>
                            Total:
                          </span>
                          ₹{loanOpenGroups.otherTotals.current.toLocaleString()}
                        </td>
                        <td colSpan={2} className='text-center fw-bold py-2'>
                          {(() => {
                            const inv = loanOpenGroups.otherTotals.invested;
                            const cur = loanOpenGroups.otherTotals.current;
                            const netPnl = cur - inv;
                            return (
                              <span
                                className={
                                  netPnl >= 0 ? 'text-success' : 'text-danger'
                                }
                              >
                                <span className='text-muted small fw-normal me-1'>
                                  P&L:
                                </span>
                                {netPnl >= 0 ? '+' : ''}₹
                                {netPnl.toLocaleString()}
                              </span>
                            );
                          })()}
                        </td>
                        <td colSpan={2} className='text-end py-2'>
                          {(() => {
                            const inv = loanOpenGroups.otherTotals.invested;
                            const cur = loanOpenGroups.otherTotals.current;
                            const netPnl = cur - inv;
                            const pct = inv > 0 ? (netPnl / inv) * 100 : 0;
                            return (
                              <span
                                className={`badge ${pct >= 0 ? 'bg-success' : 'bg-danger'}`}
                                title={`Net P&L: ₹${netPnl.toLocaleString()}`}
                              >
                                {pct >= 0 ? '+' : ''}
                                {pct.toFixed(2)}%
                              </span>
                            );
                          })()}
                        </td>
                        <td colSpan={2}></td>
                      </tr>
                      {loanOpenGroups.other.map(renderOpenHoldingRow)}
                    </>
                  )}
                </>
              ) : filteredOpenHoldings.length === 0 ? (
                <tr>
                  <td
                    colSpan={SHOW_CURRENT_DATE ? 18 : 17}
                    className='text-center py-4 text-muted'
                  >
                    No open holdings matching "{searchQuery}".
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
                filteredOpenHoldings.map(renderOpenHoldingRow)
              )}
            </tbody>
            {openHoldings.length > 0 && (
              <tfoot className='table-secondary fw-bold border-top border-2'>
                <tr>
                  <td colSpan={SHOW_CURRENT_DATE ? 8 : 7} className='col-sticky-footer-label'>
                    Total ({filteredOpenHoldings.length} holdings
                    {searchQuery.trim() ? ` matching "${searchQuery}"` : ''})
                  </td>
                  <td className='text-end'>
                    <span className='text-muted small fw-normal me-1'>
                      Invested:
                    </span>
                    ₹{filteredOpenTotals.invested_amount?.toLocaleString()}
                  </td>
                  <td colSpan={2}></td>
                  <td className='text-end'>
                    <span className='text-muted small fw-normal me-1'>
                      Total:
                    </span>
                    ₹{filteredOpenTotals.current_total?.toLocaleString()}
                  </td>
                  <td colSpan={2} className='text-center'>
                    <span
                      className={
                        filteredOpenTotals.net_profit >= 0
                          ? 'text-success'
                          : 'text-danger'
                      }
                    >
                      <span className='text-muted small fw-normal me-1'>
                        P&L:
                      </span>
                      {filteredOpenTotals.net_profit >= 0 ? '+' : ''}₹
                      {filteredOpenTotals.net_profit?.toLocaleString()}
                    </span>
                  </td>
                  <td colSpan={2} className='text-end'>
                    {(() => {
                      const inv = filteredOpenTotals.invested_amount || 0;
                      const net = filteredOpenTotals.net_profit || 0;
                      const pct = inv > 0 ? (net / inv) * 100 : 0;
                      return (
                        <span
                          className={`badge ${pct >= 0 ? 'bg-success' : 'bg-danger'}`}
                        >
                          {pct >= 0 ? '+' : ''}
                          {pct.toFixed(2)}%
                        </span>
                      );
                    })()}
                  </td>
                  <td colSpan={2}></td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </div>

      {/* 4. Summary Panel (Loan Portfolio Balance Sheet - LOAN portfolio only) */}
      {activePortfolio === 'LOAN' && summaryData && (
        <div className='dashboard-card p-4 mb-4 bg-white border'>
          <div className='d-flex justify-content-between align-items-center mb-3'>
            <h5 className='fw-bold mb-0 text-dark'>
              Loan Portfolio Balance Sheet & Summary (§8)
            </h5>
            <button
              type='button'
              className='btn btn-sm btn-outline-primary'
              onClick={openSummaryEdit}
            >
              <Edit3
                size={14}
                className='me-1 inline-block'
              />{' '}
              Edit Fixed Figures
            </button>
          </div>

          <div className='row g-4'>
            {/* Block A */}
            <div className='col-12 col-md-6'>
              <div className='p-3 border rounded bg-light h-100'>
                <h6 className='fw-bold text-uppercase small text-muted border-bottom pb-2 mb-3'>
                  Block A — Capital Deployment
                </h6>
                <div className='d-flex justify-content-between align-items-center py-1'>
                  <div
                    className='d-flex align-items-center gap-1 position-relative'
                    ref={balanceInfoRef}
                  >
                    <span>Current Stock & ETF Invest:</span>
                    <button
                      type='button'
                      className='btn btn-link p-0 text-primary d-inline-flex align-items-center'
                      onClick={() => setShowBalanceInfo((prev) => !prev)}
                      title='Click for calculation details'
                    >
                      <Info size={14} />
                    </button>
                    {showBalanceInfo && (
                      <div
                        className='position-absolute bg-white text-dark p-3 rounded shadow-lg border'
                        style={{
                          top: '100%',
                          left: 0,
                          zIndex: 1050,
                          width: '300px',
                          fontSize: '0.8rem',
                          lineHeight: '1.4',
                        }}
                      >
                        <div className='d-flex justify-content-between align-items-center mb-1 pb-1 border-bottom'>
                          <strong className='text-primary d-flex align-items-center gap-1'>
                            <Info size={13} /> Auto-Calculated Value
                          </strong>
                          <button
                            type='button'
                            className='btn-close'
                            style={{ fontSize: '0.65rem' }}
                            onClick={() => setShowBalanceInfo(false)}
                          />
                        </div>
                        <p className='mb-1 text-muted'>
                          Automatically calculated from the sum of all{' '}
                          <strong>Current Invested</strong> amounts in open
                          holdings under the <strong>LOAN</strong> portfolio
                          (MADI + BAPA).
                        </p>
                        <div className='bg-light p-1.5 rounded fw-bold text-dark mt-2 d-flex justify-content-between'>
                          <span>Current Stock & ETF Total:</span>
                          <span className='text-primary'>
                            ₹
                            {summaryData.block_a.current_stock_etf_invest?.toLocaleString()}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                  <strong>
                    ₹
                    {summaryData.block_a.current_stock_etf_invest?.toLocaleString()}
                  </strong>
                </div>
                <div className='d-flex justify-content-between py-1'>
                  <span>Current Mutual Fund (MF) Invest:</span>
                  <strong>
                    ₹
                    {summaryData.block_a.current_mf_invest?.toLocaleString()}
                  </strong>
                </div>
                <div className='d-flex justify-content-between py-1'>
                  <span>Current Mutual Fund (MF) Redeem:</span>
                  <strong>
                    ₹
                    {summaryData.block_a.current_mf_redeem?.toLocaleString()}
                  </strong>
                </div>
                <hr className='my-2' />
                <div className='d-flex justify-content-between py-1 fs-6 fw-bold text-primary'>
                  <span>Total Investment Deployment:</span>
                  <span>
                    ₹{summaryData.block_a.total?.toLocaleString()}
                  </span>
                </div>
              </div>
            </div>

            {/* Block B */}
            <div className='col-12 col-md-6'>
              <div className='p-3 border rounded bg-light h-100'>
                <h6 className='fw-bold text-uppercase small text-muted border-bottom pb-2 mb-3'>
                  Block B — Loan & Profit Tracking
                </h6>
                <div className='d-flex justify-content-between py-1'>
                  <span>Loan Amount:</span>
                  <strong>
                    ₹
                    {summaryData.block_b.loan_amount?.toLocaleString()}
                  </strong>
                </div>
                <div className='d-flex justify-content-between py-1'>
                  <span>Remaining Invest From Loan:</span>
                  <span
                    className={
                      summaryData.block_b.remaining_invest_loan <
                      0
                        ? 'text-danger fw-bold'
                        : 'text-success fw-bold'
                    }
                  >
                    ₹
                    {summaryData.block_b.remaining_invest_loan?.toLocaleString()}
                  </span>
                </div>
                <div className='d-flex justify-content-between align-items-center py-1'>
                  <div
                    className='d-flex align-items-center gap-1 position-relative'
                    ref={stockProfitInfoRef}
                    onMouseEnter={() => setShowStockProfitInfo(true)}
                    onMouseLeave={() => setShowStockProfitInfo(false)}
                  >
                    <span>Stock Profit:</span>
                    <button
                      type='button'
                      className='btn btn-link p-0 text-primary d-inline-flex align-items-center'
                      onClick={() => setShowStockProfitInfo((prev) => !prev)}
                      title='Earned total − Loss total of sold positions'
                      aria-label='Stock profit calculation details'
                    >
                      <Info size={14} />
                    </button>
                    {showStockProfitInfo && (
                      <div
                        className='position-absolute bg-white text-dark p-3 rounded shadow-lg border'
                        style={{
                          top: '100%',
                          left: 0,
                          zIndex: 1050,
                          width: '320px',
                          fontSize: '0.8rem',
                          lineHeight: '1.4',
                          pointerEvents: 'none',
                        }}
                      >
                        <div className='d-flex justify-content-between align-items-center mb-1 pb-1 border-bottom'>
                          <strong className='text-primary d-flex align-items-center gap-1'>
                            <Info size={13} /> Realized Stock Profit
                          </strong>
                        </div>
                        <p className='mb-2 text-muted'>
                          Calculated as <strong>Earned total − Loss total</strong> of sold positions under the <strong>LOAN</strong> portfolio.
                        </p>
                        <div className='bg-light p-2 rounded'>
                          <div className='d-flex justify-content-between text-success mb-1'>
                            <span>Sold Earned:</span>
                            <span>
                              +₹{(summaryData.block_b.sold_earned ?? soldTotals?.earned ?? 0).toLocaleString()}
                            </span>
                          </div>
                          <div className='d-flex justify-content-between text-danger mb-1'>
                            <span>Sold Loss:</span>
                            <span>
                              -₹{Math.abs(summaryData.block_b.sold_loss ?? soldTotals?.loss ?? 0).toLocaleString()}
                            </span>
                          </div>
                          <hr className='my-1' />
                          <div className='d-flex justify-content-between fw-bold text-dark'>
                            <span>Net Stock Profit:</span>
                            <span
                              className={
                                summaryData.block_b.stock_profit >= 0
                                  ? 'text-success'
                                  : 'text-danger'
                              }
                            >
                              {summaryData.block_b.stock_profit >= 0 ? '+' : ''}₹
                              {summaryData.block_b.stock_profit?.toLocaleString()}
                            </span>
                          </div>
                        </div>
                        <div className='mt-2 text-muted small' style={{ fontSize: '0.74rem' }}>
                          Includes statutory charges. Open holdings are tracked separately in Block A.
                        </div>
                      </div>
                    )}
                  </div>
                  <span
                    className={
                      summaryData.block_b.stock_profit >= 0
                        ? 'text-success fw-bold'
                        : 'text-danger fw-bold'
                    }
                  >
                    ₹
                    {summaryData.block_b.stock_profit?.toLocaleString()}
                  </span>
                </div>
                <div className='d-flex justify-content-between py-1'>
                  <span>Total Realized Dividends:</span>
                  <strong>
                    ₹
                    {summaryData.block_b.dividend?.toLocaleString()}
                  </strong>
                </div>
                <div className='d-flex justify-content-between py-1'>
                  <span>Current MF Redeem + Profit:</span>
                  <strong>
                    ₹
                    {summaryData.block_b.current_mf_redeem_profit?.toLocaleString()}
                  </strong>
                </div>
                <hr className='my-2' />
                <div className='d-flex justify-content-between py-1 fs-5 fw-bold text-success'>
                  <span>Current Remaining Balance:</span>
                  <span>
                    ₹
                    {summaryData.block_b.current_remaining?.toLocaleString()}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Modals */}
      {/* ------------------------------------------------------------- */}

      {/* Sold Positions Modal */}
      <SoldPositionsModal
        show={showSoldModal}
        onClose={() => setShowSoldModal(false)}
        activePortfolio={activePortfolio}
        groupedSoldHoldings={groupedSoldHoldings}
        soldHoldings={soldHoldings}
        soldTotals={soldTotals}
        expandedSoldHoldings={expandedSoldHoldings}
        toggleExpandSold={toggleExpandSold}
        onOpenNotes={(noteItem) => {
          setNotesForm({
            bought_reason: noteItem.bought_reason || '',
            sold_reason: noteItem.sold_reason || '',
            mistake_learned: noteItem.mistake_learned || '',
          });
          setShowNotesModal(noteItem);
        }}
        onRefresh={() => loadPortfolioData(activePortfolio)}
        showToast={showToast}
      />

      {/* Dividends Modal */}
      <DividendsModal
        show={showDividendsModal}
        onClose={() => setShowDividendsModal(false)}
        activePortfolio={activePortfolio}
        dividends={dividends}
        totalDividends={data?.total_dividends || 0}
        divForm={divForm}
        setDivForm={setDivForm}
        onAddDividend={handleAddDividend}
        onDeleteDividend={handleDeleteDividend}
      />

      {/* Edit Holding / Lot Entry Modal */}
      {editTarget && (
        <div className='modal-backdrop-custom' role='dialog' aria-modal='true'>
          <div className='modal-dialog-custom' style={{ maxWidth: '580px' }}>
            {/* Modal Header */}
            <div className='modal-header-custom'>
              <div>
                <h3 className='modal-title-custom'>
                  {editTarget.isHoldingOnly
                    ? 'Edit Holding Info'
                    : editTarget.isSingleEntry
                    ? 'Edit Holding & Entry'
                    : 'Edit Buy Lot'}
                </h3>
                <p className='modal-subtitle-custom'>
                  {editTarget.holding.stock_name || editTarget.holding.scheme_name || editTarget.holding.symbol}
                  {editTarget.holding.symbol ? ` (${editTarget.holding.symbol})` : ''}
                </p>
              </div>
              <button
                type='button'
                className='modal-close-btn'
                onClick={() => setEditTarget(null)}
                aria-label='Close modal'
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleEditSubmit} autoComplete='off'>
              <div>
                {/* Holding metadata (StockTicker / StockName / Person) if single-entry or holding-only */}
                {(editTarget.isHoldingOnly || editTarget.isSingleEntry) && (
                  <div className='p-3 mb-3 bg-light rounded-3 border'>
                    <div className='small fw-bold text-muted mb-2 text-uppercase' style={{ letterSpacing: '0.04em' }}>
                      Holding Information
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
                                name='editPersonRadio'
                                id={`editPerson_${p}`}
                                value={p}
                                checked={editForm.person === p}
                                onChange={() => setEditForm((prev) => ({ ...prev, person: p }))}
                              />
                              <label className='form-check-label small fw-semibold' htmlFor={`editPerson_${p}`}>
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
                          value={editForm.symbol}
                          onChange={(e) => {
                            const newSym = e.target.value;
                            setEditForm((prev) => ({
                              ...prev,
                              symbol: newSym,
                              name_confirmed: false,
                            }));
                          }}
                          onBlur={() =>
                            editLookup.handleLookup(
                              editForm.symbol,
                              (res) => {
                                setEditForm((prev) => ({
                                  ...prev,
                                  stock_name: res.name || prev.stock_name,
                                  scheme_name: res.name || prev.scheme_name,
                                  name_confirmed: true,
                                }));
                              },
                              () => {
                                setEditForm((prev) => ({ ...prev, name_confirmed: false }));
                              },
                            )
                          }
                          required
                        />
                        <button
                          type='button'
                          className='btn btn-outline-secondary'
                          onClick={() =>
                            editLookup.handleLookup(
                              editForm.symbol,
                              (res) => {
                                setEditForm((prev) => ({
                                  ...prev,
                                  stock_name: res.name || prev.stock_name,
                                  scheme_name: res.name || prev.scheme_name,
                                  name_confirmed: true,
                                }));
                              },
                              () => {
                                setEditForm((prev) => ({ ...prev, name_confirmed: false }));
                              },
                            )
                          }
                          disabled={editLookup.lookupStatus.loading}
                        >
                          {editLookup.lookupStatus.loading ? 'Checking...' : 'Lookup'}
                        </button>
                      </div>
                      {editLookup.lookupStatus.found === true && (
                        <div className='text-success small mt-1 d-flex align-items-center'>
                          <CheckCircle2 size={13} className='me-1' /> {editLookup.lookupStatus.message}
                        </div>
                      )}
                      {editLookup.lookupStatus.found === false && (
                        <div className='alert alert-warning py-1 px-2 small mt-1 mb-0'>
                          ⚠️ {editLookup.lookupStatus.message}
                        </div>
                      )}
                    </div>
                    <div className='mb-2'>
                      <label className='form-label-custom'>
                        Stock Name{' '}
                        {editLookup.lookupStatus.found === false ? '*' : '(Auto-fetched from ticker)'}
                      </label>
                      <input
                        type='text'
                        className='form-control'
                        placeholder='Company / Stock Name'
                        value={editForm.stock_name || editForm.scheme_name}
                        onChange={(e) =>
                          setEditForm((prev) => ({
                            ...prev,
                            stock_name: e.target.value,
                            scheme_name: e.target.value,
                          }))
                        }
                        required={editLookup.lookupStatus.found === false}
                      />
                    </div>
                    {editLookup.lookupStatus.found === false && (
                      <div className='form-check mb-2'>
                        <input
                          type='checkbox'
                          className='form-check-input'
                          id='confirmManualNameEdit'
                          checked={Boolean(editForm.name_confirmed)}
                          onChange={(e) =>
                            setEditForm((prev) => ({
                              ...prev,
                              name_confirmed: e.target.checked,
                            }))
                          }
                          required
                        />
                        <label className='form-check-label small' htmlFor='confirmManualNameEdit'>
                          I confirm this stock name is correct (§3 requirement)
                        </label>
                      </div>
                    )}
                    <div>
                      <label className='form-label-custom'>Holding Remarks</label>
                      <input
                        type='text'
                        className='form-control'
                        placeholder='Holding-level notes'
                        value={editForm.holding_remarks}
                        onChange={(e) => setEditForm({ ...editForm, holding_remarks: e.target.value })}
                      />
                    </div>
                  </div>
                )}

                {/* Lot details if not holding-only */}
                {!editTarget.isHoldingOnly && (
                  <div>
                    {!editTarget.isSingleEntry && (
                      <div className='small fw-bold text-muted mb-2 text-uppercase' style={{ letterSpacing: '0.04em' }}>
                        Buy Lot Entry Values
                      </div>
                    )}
                    <div className='row g-2 mb-3'>
                      <div className='col-6'>
                        <label className='form-label-custom'>Invest Date *</label>
                        <input
                          type='date'
                          className='form-control'
                          value={editForm.invest_date}
                          onChange={(e) => setEditForm({ ...editForm, invest_date: e.target.value })}
                          required
                        />
                      </div>
                      <div className='col-6'>
                        <label className='form-label-custom'>Quantity (Q) *</label>
                        <input
                          type='number'
                          step='any'
                          className='form-control'
                          value={editForm.quantity}
                          onChange={(e) => {
                            const newQ = e.target.value;
                            setEditForm((prev) => {
                              const q = parseFloat(newQ) || 0;
                              const avg = parseFloat(prev.avg_price) || 0;
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
                                quantity: newQ,
                                invested_amount: inv,
                                buy_charge: bc,
                              };
                            });
                          }}
                          required
                        />
                      </div>
                    </div>

                    <div className='mb-3'>
                      <label className='form-label-custom'>Avg Buy Price (₹) *</label>
                      <input
                        type='number'
                        step='0.01'
                        className='form-control'
                        value={editForm.avg_price}
                        onChange={(e) => {
                          const newAvg = e.target.value;
                          setEditForm((prev) => {
                            const avg = parseFloat(newAvg) || 0;
                            const q = parseFloat(prev.quantity) || 0;
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

                    {/* Manual override for Invested Amount */}
                    <div className='mb-3'>
                      <div className='d-flex justify-content-between align-items-center mb-1'>
                        <label className='form-label-custom mb-0'>Invested Amount (₹)</label>
                        <div className='form-check form-check-inline m-0'>
                          <input
                            className='form-check-input'
                            type='checkbox'
                            id='overrideInvested'
                            checked={editForm.manual_override_invested}
                            onChange={(e) => {
                              const checked = e.target.checked;
                              setEditForm((prev) => {
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
                          <label className='form-check-label small text-muted' htmlFor='overrideInvested'>
                            Manual cost basis override
                          </label>
                        </div>
                      </div>
                      <input
                        type='number'
                        step='0.01'
                        className='form-control'
                        value={editForm.invested_amount}
                        disabled={!editForm.manual_override_invested}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            invested_amount: e.target.value,
                          })
                        }
                      />
                    </div>

                    {/* Manual override for Buy Charge */}
                    <div className='mb-3'>
                      <div className='d-flex justify-content-between align-items-center mb-1'>
                        <label className='form-label-custom mb-0'>Buy Charge (₹)</label>
                        <div className='form-check form-check-inline m-0'>
                          <input
                            className='form-check-input'
                            type='checkbox'
                            id='overrideBuyCharge'
                            checked={editForm.manual_override_buy_charge}
                            onChange={(e) => {
                              const checked = e.target.checked;
                              setEditForm((prev) => {
                                const inv =
                                  parseFloat(prev.invested_amount) ||
                                  (parseFloat(prev.quantity) || 0) *
                                    (parseFloat(prev.avg_price) || 0);
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
                          <label className='form-check-label small text-muted' htmlFor='overrideBuyCharge'>
                            Manual override
                          </label>
                        </div>
                      </div>
                      <input
                        type='number'
                        step='0.01'
                        className='form-control'
                        value={editForm.buy_charge}
                        disabled={!editForm.manual_override_buy_charge}
                        onChange={(e) =>
                          setEditForm({ ...editForm, buy_charge: e.target.value })
                        }
                      />
                    </div>

                    <div className='mb-3'>
                      <label className='form-label-custom'>Lot Remarks</label>
                      <input
                        type='text'
                        className='form-control'
                        placeholder='e.g. Swing, Demerger, DIP buy'
                        value={editForm.remarks}
                        onChange={(e) =>
                          setEditForm({ ...editForm, remarks: e.target.value })
                        }
                      />
                    </div>
                  </div>
                )}
              </div>
              <div className='modal-footer-custom'>
                <button
                  type='button'
                  className='btn btn-outline-secondary'
                  onClick={() => setEditTarget(null)}
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

      {/* Add Holding Modal */}
      {showAddHoldingModal && (
        <div
          className='modal show d-block'
          tabIndex='-1'
          style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
        >
          <div className='modal-dialog'>
            <div className='modal-content'>
              <form onSubmit={handleAddHoldingSubmit}>
                <div className='modal-header'>
                  <h5 className='modal-title'>
                    Add Holding to{' '}
                    {addHoldingTarget.portfolio || activePortfolio}
                    {(addHoldingTarget.portfolio || activePortfolio) ===
                    'LOAN'
                      ? ` (${holdingForm.person})`
                      : ''}
                  </h5>
                  <button
                    type='button'
                    className='btn-close'
                    onClick={() => setShowAddHoldingModal(false)}
                  />
                </div>
                <div className='modal-body'>
                  {(addHoldingTarget.portfolio || activePortfolio) ===
                  'LOAN' ? (
                    <div className='mb-3 p-3 bg-light rounded border'>
                      <label className='form-label small fw-bold text-dark mb-2 d-block'>
                        Select Person / Account for Holding *
                      </label>
                      <div className='d-flex align-items-center gap-4'>
                        <div className='form-check'>
                          <input
                            className='form-check-input'
                            type='radio'
                            name='loanPersonRadio'
                            id='personRadioMADI'
                            value='MADI'
                            checked={holdingForm.person === 'MADI'}
                            onChange={() =>
                              setHoldingForm((prev) => ({
                                ...prev,
                                person: 'MADI',
                              }))
                            }
                          />
                          <label
                            className='form-check-label fw-semibold text-dark d-flex align-items-center gap-1'
                            htmlFor='personRadioMADI'
                            style={{ cursor: 'pointer' }}
                          >
                            <span className='badge bg-primary'>MADI</span>
                            <span>MADI Portfolio</span>
                          </label>
                        </div>
                        <div className='form-check'>
                          <input
                            className='form-check-input'
                            type='radio'
                            name='loanPersonRadio'
                            id='personRadioBAPA'
                            value='BAPA'
                            checked={holdingForm.person === 'BAPA'}
                            onChange={() =>
                              setHoldingForm((prev) => ({
                                ...prev,
                                person: 'BAPA',
                              }))
                            }
                          />
                          <label
                            className='form-check-label fw-semibold text-dark d-flex align-items-center gap-1'
                            htmlFor='personRadioBAPA'
                            style={{ cursor: 'pointer' }}
                          >
                            <span className='badge bg-info text-dark'>BAPA</span>
                            <span>BAPA Portfolio</span>
                          </label>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className='mb-3 p-2 bg-light rounded border d-flex justify-content-between align-items-center'>
                      <span className='small text-muted'>Target Portfolio:</span>
                      <span className='badge bg-dark'>
                        {addHoldingTarget.portfolio || activePortfolio}
                      </span>
                    </div>
                  )}
                  <div className='mb-2'>
                    <label className='form-label small mb-1'>
                      Ticker / Symbol *
                    </label>
                    <div className='input-group'>
                      <input
                        type='text'
                        className='form-control'
                        placeholder='e.g. TATAGOLD or RELIANCE'
                        value={holdingForm.symbol}
                        onChange={(e) =>
                          setHoldingForm({
                            ...holdingForm,
                            symbol: e.target.value,
                          })
                        }
                        onBlur={() =>
                          handleTickerLookup(holdingForm.symbol)
                        }
                        required
                      />
                      <button
                        type='button'
                        className='btn btn-outline-secondary'
                        onClick={() =>
                          handleTickerLookup(holdingForm.symbol)
                        }
                        disabled={lookupStatus.loading}
                      >
                        {lookupStatus.loading
                          ? 'Checking...'
                          : 'Lookup'}
                      </button>
                    </div>
                    {lookupStatus.found === true && (
                      <div className='text-success small mt-1 d-flex align-items-center'>
                        <CheckCircle2
                          size={13}
                          className='me-1'
                        />{' '}
                        {lookupStatus.message}
                      </div>
                    )}
                    {lookupStatus.found === false && (
                      <div className='alert alert-warning py-1 px-2 small mt-1 mb-0'>
                        ⚠️ {lookupStatus.message}
                      </div>
                    )}
                  </div>
                  <div className='mb-2'>
                    <label className='form-label small mb-1'>
                      Stock Name{' '}
                      {lookupStatus.found === false
                        ? '*'
                        : '(Auto-fetched if blank)'}
                    </label>
                    <input
                      type='text'
                      className='form-control'
                      placeholder='Company / Stock Name'
                      value={holdingForm.stock_name || holdingForm.scheme_name}
                      onChange={(e) =>
                        setHoldingForm({
                          ...holdingForm,
                          stock_name: e.target.value,
                          scheme_name: e.target.value,
                        })
                      }
                      required={lookupStatus.found === false}
                    />
                  </div>
                  {lookupStatus.found === false && (
                    <div className='form-check mb-2'>
                      <input
                        type='checkbox'
                        className='form-check-input'
                        id='confirmManualName'
                        checked={holdingForm.name_confirmed}
                        onChange={(e) =>
                          setHoldingForm({
                            ...holdingForm,
                            name_confirmed: e.target.checked,
                          })
                        }
                        required
                      />
                      <label
                        className='form-check-label small'
                        htmlFor='confirmManualName'
                      >
                        I confirm this stock name is correct (§3
                        requirement)
                      </label>
                    </div>
                  )}
                  <div className='row g-2 mb-2'>
                    <div className='col-6'>
                      <label className='form-label small mb-1'>
                        Invest Date
                      </label>
                      <input
                        type='date'
                        className='form-control'
                        value={holdingForm.invest_date}
                        onChange={(e) =>
                          setHoldingForm({
                            ...holdingForm,
                            invest_date: e.target.value,
                          })
                        }
                        required
                      />
                    </div>
                    <div className='col-6'>
                      <label className='form-label small mb-1'>
                        Quantity (Q) *
                      </label>
                      <input
                        type='number'
                        step='any'
                        className='form-control'
                        placeholder='Number of shares'
                        value={holdingForm.quantity}
                        onChange={(e) =>
                          setHoldingForm({
                            ...holdingForm,
                            quantity: e.target.value,
                          })
                        }
                        required
                      />
                    </div>
                  </div>
                  <div className='mb-2'>
                    <label className='form-label small mb-1'>
                      Avg Buy Price (₹) *
                    </label>
                    <input
                      type='number'
                      step='0.01'
                      className='form-control'
                      placeholder='Buy price per share'
                      value={holdingForm.avg_price}
                      onChange={(e) =>
                        setHoldingForm({
                          ...holdingForm,
                          avg_price: e.target.value,
                        })
                      }
                      required
                    />
                  </div>
                  <div className='mb-2'>
                    <label className='form-label small mb-1'>
                      Remarks
                    </label>
                    <input
                      type='text'
                      className='form-control'
                      placeholder='e.g. Swing, ETF, Long term'
                      value={holdingForm.remarks}
                      onChange={(e) =>
                        setHoldingForm({
                          ...holdingForm,
                          remarks: e.target.value,
                        })
                      }
                    />
                  </div>
                  <div className='mb-2'>
                    <label className='form-label small mb-1'>
                      Bought Reason (§6)
                    </label>
                    <textarea
                      className='form-control'
                      rows={2}
                      placeholder='Why did you buy this stock?'
                      value={holdingForm.bought_reason}
                      onChange={(e) =>
                        setHoldingForm({
                          ...holdingForm,
                          bought_reason: e.target.value,
                        })
                      }
                    />
                  </div>
                </div>
                <div className='modal-footer'>
                  <button
                    type='button'
                    className='btn btn-secondary'
                    onClick={() => setShowAddHoldingModal(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type='submit'
                    className='btn btn-primary'
                  >
                    Save Holding
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Add Buy Lot Modal */}
      {showAddLotModal && (
        <div
          className='modal show d-block'
          tabIndex='-1'
          style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
        >
          <div className='modal-dialog'>
            <div className='modal-content'>
              <form onSubmit={handleAddLotSubmit}>
                <div className='modal-header'>
                  <h5 className='modal-title'>
                    Add Buy Lot to{' '}
                    {showAddLotModal.scheme_name ||
                      showAddLotModal.symbol}
                  </h5>
                  <button
                    type='button'
                    className='btn-close'
                    onClick={() => setShowAddLotModal(null)}
                  />
                </div>
                <div className='modal-body'>
                  <div className='mb-2'>
                    <label className='form-label small mb-1'>
                      Buy Date
                    </label>
                    <input
                      type='date'
                      className='form-control'
                      value={lotForm.invest_date}
                      onChange={(e) =>
                        setLotForm({
                          ...lotForm,
                          invest_date: e.target.value,
                        })
                      }
                      required
                    />
                  </div>
                  <div className='mb-2'>
                    <label className='form-label small mb-1'>
                      Quantity
                    </label>
                    <input
                      type='number'
                      step='any'
                      className='form-control'
                      value={lotForm.quantity}
                      onChange={(e) =>
                        setLotForm({
                          ...lotForm,
                          quantity: e.target.value,
                        })
                      }
                      required
                    />
                  </div>
                  <div className='mb-2'>
                    <label className='form-label small mb-1'>
                      Buy Price (₹)
                    </label>
                    <input
                      type='number'
                      step='0.01'
                      className='form-control'
                      value={lotForm.avg_price}
                      onChange={(e) =>
                        setLotForm({
                          ...lotForm,
                          avg_price: e.target.value,
                        })
                      }
                      required
                    />
                  </div>
                  <div className='mb-2'>
                    <label className='form-label small mb-1'>
                      Remarks
                    </label>
                    <input
                      type='text'
                      className='form-control'
                      value={lotForm.remarks}
                      onChange={(e) =>
                        setLotForm({
                          ...lotForm,
                          remarks: e.target.value,
                        })
                      }
                    />
                  </div>
                </div>
                <div className='modal-footer'>
                  <button
                    type='button'
                    className='btn btn-secondary'
                    onClick={() => setShowAddLotModal(null)}
                  >
                    Cancel
                  </button>
                  <button
                    type='submit'
                    className='btn btn-primary'
                  >
                    Append Buy Lot
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Sell Modal */}
      {showSellModal && (
        <div
          className='modal show d-block'
          tabIndex='-1'
          style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
        >
          <div className='modal-dialog'>
            <div className='modal-content'>
              <form onSubmit={handleSellSubmit}>
                <div className='modal-header'>
                  <h5 className='modal-title'>
                    Sell Position:{' '}
                    {showSellModal.scheme_name ||
                      showSellModal.symbol}
                  </h5>
                  <button
                    type='button'
                    className='btn-close'
                    onClick={() => setShowSellModal(null)}
                  />
                </div>
                <div className='modal-body'>
                  <p className='small text-muted mb-3'>
                    Selling will calculate realized gain/loss and move
                    this stock to the Sold table.
                  </p>
                  <div className='row g-2 mb-2'>
                    <div className='col-6'>
                      <label className='form-label small mb-1'>
                        Sell Date
                      </label>
                      <input
                        type='date'
                        className='form-control'
                        value={sellForm.sell_date}
                        onChange={(e) =>
                          setSellForm({
                            ...sellForm,
                            sell_date: e.target.value,
                          })
                        }
                        required
                      />
                    </div>
                    <div className='col-6'>
                      <label className='form-label small mb-1'>
                        Exit Price / LTP (₹) *
                      </label>
                      <input
                        type='number'
                        step='0.01'
                        className='form-control'
                        value={sellForm.sell_price}
                        onChange={(e) =>
                          setSellForm({
                            ...sellForm,
                            sell_price: e.target.value,
                          })
                        }
                        required
                      />
                    </div>
                  </div>
                  <div className='mb-2'>
                    <label className='form-label small mb-1'>
                      Quantity to Sell (default: all{' '}
                      {showSellModal.quantity})
                    </label>
                    <input
                      type='number'
                      step='any'
                      className='form-control'
                      value={sellForm.quantity}
                      onChange={(e) =>
                        setSellForm({
                          ...sellForm,
                          quantity: e.target.value,
                        })
                      }
                    />
                  </div>

                  {/* Real-time Recalculated Preview (§4) */}
                  {(() => {
                    const sellQty =
                      parseFloat(sellForm.quantity) ||
                      parseFloat(showSellModal.quantity) ||
                      0;
                    const exitPrice =
                      parseFloat(sellForm.sell_price) || 0;
                    const avgPrice =
                      parseFloat(showSellModal.avg_price) || 0;
                    const costBasis = sellQty * avgPrice;
                    const exitTotal = sellQty * exitPrice;
                    const sellCharge = exitTotal * SELL_CHARGE_RATE;
                    const buyCharge = costBasis * BUY_CHARGE_RATE;
                    const netPnL =
                      exitTotal - costBasis - buyCharge - sellCharge;
                    const returnPct =
                      costBasis > 0
                        ? (exitTotal / costBasis - 1) * 100
                        : 0;
                    if (sellQty <= 0 || exitPrice <= 0) return null;
                    return (
                      <div className='card bg-light p-2 mb-3 border'>
                        <div className='small fw-bold mb-1 text-secondary'>
                          Real-Time Sale Preview (§4):
                        </div>
                        <div
                          className='row g-2 text-center'
                          style={{ fontSize: '0.82rem' }}
                        >
                          <div className='col-4'>
                            <span className='text-muted'>
                              Exit Total:
                            </span>
                            <div className='fw-bold'>
                              ₹
                              {Math.round(exitTotal).toLocaleString()}
                            </div>
                          </div>
                          <div className='col-4'>
                            <span className='text-muted'>
                              Est. Charges:
                            </span>
                            <div className='text-muted'>
                              ₹{(buyCharge + sellCharge).toFixed(2)}
                            </div>
                          </div>
                          <div className='col-4'>
                            <span className='text-muted'>
                              Net Realized:
                            </span>
                            <div
                              className={`fw-bold ${netPnL >= 0 ? 'text-success' : 'text-danger'}`}
                            >
                              {netPnL >= 0 ? '+' : ''}₹
                              {Math.round(netPnL).toLocaleString()} (
                              {returnPct.toFixed(2)}%)
                            </div>
                          </div>
                        </div>
                        {sellQty < showSellModal.quantity && (
                          <div
                            className='alert alert-info py-1 px-2 mb-0 mt-2'
                            style={{ fontSize: '0.78rem' }}
                          >
                            ℹ️ Partial sell: {sellQty} of{' '}
                            {showSellModal.quantity} shares will be
                            sold. Remaining{' '}
                            {(
                              showSellModal.quantity - sellQty
                            ).toFixed(2)}{' '}
                            shares stay open.
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  <div className='mb-2'>
                    <label className='form-label small mb-1'>
                      Sold Reason (§6)
                    </label>
                    <textarea
                      className='form-control'
                      rows={2}
                      placeholder='Why did you exit this position?'
                      value={sellForm.sold_reason}
                      onChange={(e) =>
                        setSellForm({
                          ...sellForm,
                          sold_reason: e.target.value,
                        })
                      }
                    />
                  </div>
                  <div className='mb-2'>
                    <label className='form-label small mb-1'>
                      Mistake / Lesson Learned (§6)
                    </label>
                    <textarea
                      className='form-control'
                      rows={2}
                      placeholder='What was learned or avoided?'
                      value={sellForm.mistake_learned}
                      onChange={(e) =>
                        setSellForm({
                          ...sellForm,
                          mistake_learned: e.target.value,
                        })
                      }
                    />
                  </div>
                </div>
                <div className='modal-footer'>
                  <button
                    type='button'
                    className='btn btn-secondary'
                    onClick={() => setShowSellModal(null)}
                  >
                    Cancel
                  </button>
                  <button
                    type='submit'
                    className='btn btn-warning'
                  >
                    Confirm Sell
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Notes & Lessons Modal */}
      {showNotesModal && (
        <div
          className='modal show d-block'
          tabIndex='-1'
          style={{ backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 1070 }}
        >
          <div className='modal-dialog'>
            <div className='modal-content'>
              <form onSubmit={handleNotesSubmit}>
                <div className='modal-header'>
                  <h5 className='modal-title'>
                    Notes & Lessons:{' '}
                    {showNotesModal.scheme_name ||
                      showNotesModal.symbol}
                  </h5>
                  <button
                    type='button'
                    className='btn-close'
                    onClick={() => setShowNotesModal(null)}
                  />
                </div>
                <div className='modal-body'>
                  <div className='mb-3'>
                    <label className='form-label fw-semibold small mb-1'>
                      Bought Reason
                    </label>
                    <textarea
                      className='form-control'
                      rows={2}
                      value={notesForm.bought_reason}
                      onChange={(e) =>
                        setNotesForm({
                          ...notesForm,
                          bought_reason: e.target.value,
                        })
                      }
                      placeholder='Thesis, entry trigger, catalyst...'
                    />
                  </div>
                  <div className='mb-3'>
                    <label className='form-label fw-semibold small mb-1'>
                      Sold Reason
                    </label>
                    <textarea
                      className='form-control'
                      rows={2}
                      value={notesForm.sold_reason}
                      onChange={(e) =>
                        setNotesForm({
                          ...notesForm,
                          sold_reason: e.target.value,
                        })
                      }
                      placeholder='Target reached, stop loss, fundamental change...'
                    />
                  </div>
                  <div className='mb-3'>
                    <label className='form-label fw-semibold small mb-1 text-danger'>
                      Mistake / Lesson Learned
                    </label>
                    <textarea
                      className='form-control'
                      rows={3}
                      value={notesForm.mistake_learned}
                      onChange={(e) =>
                        setNotesForm({
                          ...notesForm,
                          mistake_learned: e.target.value,
                        })
                      }
                      placeholder='What mistake was made, or what rule was reinforced?'
                    />
                  </div>
                </div>
                <div className='modal-footer'>
                  <button
                    type='button'
                    className='btn btn-secondary'
                    onClick={() => setShowNotesModal(null)}
                  >
                    Cancel
                  </button>
                  <button
                    type='submit'
                    className='btn btn-primary'
                  >
                    Save Notes
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Mistakes & Lessons Consolidated View Modal (§6 follow-up) */}
      {showMistakesModal && (
        <div
          className='modal show d-block'
          tabIndex='-1'
          style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
        >
          <div className='modal-dialog modal-lg'>
            <div className='modal-content'>
              <div className='modal-header'>
                <h5 className='modal-title fw-bold'>
                  <BookOpen
                    size={18}
                    className='me-2 inline-block text-primary'
                  />
                  Consolidated Mistakes & Lessons Learned (
                  {mistakesList.length})
                </h5>
                <button
                  type='button'
                  className='btn-close'
                  onClick={() => setShowMistakesModal(false)}
                />
              </div>
              <div className='modal-body'>
                {mistakesList.length === 0 ? (
                  <p className='text-muted text-center py-4'>
                    No mistakes/lessons recorded yet. Record lessons
                    when selling or editing holding notes.
                  </p>
                ) : (
                  <div className='list-group'>
                    {mistakesList.map((m) => (
                      <div
                        key={m.id}
                        className='list-group-item list-group-item-action p-3'
                      >
                        <div className='d-flex justify-content-between align-items-center mb-1'>
                          <h6 className='mb-0 fw-bold'>
                            {m.scheme_name || m.symbol} (
                            {m.portfolio_name})
                          </h6>
                          <span
                            className={`badge ${m.status === 'open' ? 'bg-primary' : 'bg-secondary'}`}
                          >
                            {m.status.toUpperCase()}
                          </span>
                        </div>
                        <p
                          className='mb-2 text-danger fw-semibold'
                          style={{ fontSize: '0.9rem' }}
                        >
                          Lesson: {m.mistake_learned}
                        </p>
                        {m.bought_reason && (
                          <p className='mb-1 text-muted small'>
                            <strong>Bought Reason:</strong>{' '}
                            {m.bought_reason}
                          </p>
                        )}
                        {m.sold_reason && (
                          <p className='mb-0 text-muted small'>
                            <strong>Sold Reason:</strong>{' '}
                            {m.sold_reason}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className='modal-footer'>
                <button
                  type='button'
                  className='btn btn-secondary'
                  onClick={() => setShowMistakesModal(false)}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Summary Fixed Figures Edit Modal */}
      {showSummaryModal && (
        <div
          className='modal show d-block'
          tabIndex='-1'
          style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
        >
          <div className='modal-dialog modal-dialog-centered'>
            <div className='modal-content'>
              <div className='modal-header'>
                <h5 className='modal-title'>
                  Edit Summary Fixed Figures
                </h5>
                <button
                  type='button'
                  className='btn-close'
                  onClick={() => setShowSummaryModal(false)}
                />
              </div>
              <div className='modal-body'>
                <p className='small text-muted mb-3'>
                  These fixed figures are stored in the database and
                  feed into the Loan Balance Sheet calculations.
                </p>
                {summaryRows
                  .filter((row) => row.key !== 'current_stock_etf_invest')
                  .map((row) => (
                  <div
                    key={row.key}
                    className='mb-3'
                  >
                    <label className='form-label small fw-semibold mb-1'>
                      {row.label}
                    </label>
                    <div className='input-group input-group-sm'>
                      <span className='input-group-text'>₹</span>
                      <input
                        type='number'
                        step='0.01'
                        className='form-control'
                        defaultValue={row.value}
                        onBlur={(e) =>
                          handleSaveSummaryRow(
                            row.key,
                            e.target.value,
                            row.label,
                          )
                        }
                      />
                    </div>
                  </div>
                ))}
              </div>
              <div className='modal-footer'>
                <button
                  type='button'
                  className='btn btn-primary'
                  onClick={() => setShowSummaryModal(false)}
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Import Workbook Modal */}
      {showImportModal && (
        <div
          className='modal show d-block'
          tabIndex='-1'
          style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
        >
          <div className='modal-dialog'>
            <div className='modal-content'>
              <form onSubmit={handleImportSubmit}>
                <div className='modal-header'>
                  <h5 className='modal-title'>
                    Import Excel Workbook (Invest.xlsx)
                  </h5>
                  <button
                    type='button'
                    className='btn-close'
                    onClick={() => setShowImportModal(false)}
                  />
                </div>
                <div className='modal-body'>
                  <p className='small text-muted mb-3'>
                    Upload an XLSX file exported from Google Sheets,
                    or leave blank to import the local{' '}
                    <code>Invest.xlsx</code> in the project directory.
                  </p>
                  <div className='mb-3'>
                    <label className='form-label small mb-1'>
                      Select File (optional)
                    </label>
                    <input
                      type='file'
                      accept='.xlsx,.xls'
                      className='form-control'
                      onChange={(e) =>
                        setImportFile(e.target.files[0] || null)
                      }
                    />
                  </div>
                  <div className='form-check mb-3'>
                    <input
                      type='checkbox'
                      className='form-check-input'
                      id='replaceConfirmCheck'
                      checked={replaceConfirm}
                      onChange={(e) =>
                        setReplaceConfirm(e.target.checked)
                      }
                    />
                    <label
                      className='form-check-label small text-danger fw-bold'
                      htmlFor='replaceConfirmCheck'
                    >
                      Replace / overwrite existing Portfolio Tracker
                      records
                    </label>
                  </div>

                  {importReport && (
                    <div
                      className='alert alert-success p-3'
                      style={{ fontSize: '0.85rem' }}
                    >
                      <h6 className='fw-bold mb-2'>
                        Import Successful!
                      </h6>
                      <ul className='mb-2 ps-3'>
                        {Object.entries(
                          importReport.portfolios || {},
                        ).map(([p, s]) => (
                          <li key={p}>
                            <strong>{p}:</strong> {s.open_holdings}{' '}
                            holdings ({s.buy_lots} buy lots),{' '}
                            {s.sold_positions} sold, {s.dividends}{' '}
                            dividends
                          </li>
                        ))}
                      </ul>
                      {importReport.flagged_items &&
                        importReport.flagged_items.length > 0 && (
                          <div>
                            <strong className='text-warning'>
                              Flagged Special Items (
                              {importReport.flagged_items.length}):
                            </strong>
                            <ul
                              className='ps-3 mb-0'
                              style={{ fontSize: '0.78rem' }}
                            >
                              {importReport.flagged_items.map(
                                (item, idx) => (
                                  <li key={idx}>
                                    {item.portfolio} {item.section}{' '}
                                    (Row {item.row}): {item.note}
                                  </li>
                                ),
                              )}
                            </ul>
                          </div>
                        )}
                    </div>
                  )}
                </div>
                <div className='modal-footer'>
                  <button
                    type='button'
                    className='btn btn-secondary'
                    onClick={() => setShowImportModal(false)}
                  >
                    Close
                  </button>
                  <button
                    type='submit'
                    className='btn btn-primary'
                  >
                    Run Import
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

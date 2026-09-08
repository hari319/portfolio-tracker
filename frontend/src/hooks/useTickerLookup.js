import { useState, useCallback } from 'react';
import * as api from '../api';

/**
 * Shared hook for stock ticker lookup and validation across Portfolio Tracker modals.
 * Encapsulates loading state, found state, formatted user feedback, and callbacks.
 */
export function useTickerLookup() {
  const [lookupStatus, setLookupStatus] = useState({
    loading: false,
    found: null,
    message: '',
  });

  const handleLookup = useCallback(async (symbol, onFound, onNotFound) => {
    const sym = (symbol || '').trim();
    if (!sym || sym.length < 2) return;

    setLookupStatus({
      loading: true,
      found: null,
      message: `Looking up ticker "${sym.toUpperCase()}"...`,
    });

    try {
      const res = await api.lookupTicker(sym);
      if (res && res.ok && res.found) {
        const status = {
          loading: false,
          found: true,
          message: `Found: ${res.name} [${res.resolved_symbol}]${
            res.price ? ` (LTP: ₹${res.price})` : ''
          }`,
        };
        setLookupStatus(status);
        if (onFound) {
          onFound({
            name: res.name,
            symbol: res.resolved_symbol || sym.toUpperCase(),
            price: res.price,
          });
        }
      } else {
        const status = {
          loading: false,
          found: false,
          message: `Stock name could not be automatically found for ticker "${sym.toUpperCase()}". Please enter Stock Name manually and confirm.`,
        };
        setLookupStatus(status);
        if (onNotFound) {
          onNotFound(sym);
        }
      }
    } catch (err) {
      const status = {
        loading: false,
        found: false,
        message: `Could not lookup ticker "${sym.toUpperCase()}". Please enter Stock Name manually.`,
      };
      setLookupStatus(status);
      if (onNotFound) {
        onNotFound(sym);
      }
    }
  }, []);

  const resetLookup = useCallback((initialStatus = { loading: false, found: null, message: '' }) => {
    setLookupStatus(initialStatus);
  }, []);

  return {
    lookupStatus,
    setLookupStatus,
    handleLookup,
    resetLookup,
  };
}

export default useTickerLookup;

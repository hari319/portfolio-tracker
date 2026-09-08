/**
 * Formats a date string, ISO timestamp, or Date object into DD/MM/YYYY.
 *
 * @param {string|Date|null|undefined} dateVal
 * @returns {string} Formatted date as DD/MM/YYYY or '—' if empty/invalid.
 */
export function formatDate(dateVal) {
  if (!dateVal || dateVal === '—' || dateVal === 'None') return '—';

  // If already in YYYY-MM-DD format (standard ISO date without time component)
  if (typeof dateVal === 'string') {
    const trimmed = dateVal.trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
      const [y, m, d] = trimmed.split('-');
      return `${d}/${m}/${y}`;
    }
    // If format like YYYY-MM-DDTHH:mm:ss
    if (/^\d{4}-\d{2}-\d{2}T/.test(trimmed)) {
      const datePart = trimmed.slice(0, 10);
      const [y, m, d] = datePart.split('-');
      return `${d}/${m}/${y}`;
    }
  }

  // Fallback for Date objects or other parseable formats
  const d = new Date(dateVal);
  if (isNaN(d.getTime())) {
    return String(dateVal);
  }

  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const year = d.getFullYear();
  return `${day}/${month}/${year}`;
}

/**
 * Formats an ISO string or Date object into DD/MM/YYYY, HH:MM:SS.
 *
 * @param {string|Date|null|undefined} isoVal
 * @returns {string}
 */
export function formatDateTime(isoVal) {
  if (!isoVal) return '';
  const d = new Date(isoVal);
  if (isNaN(d.getTime())) return String(isoVal);

  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const year = d.getFullYear();
  const time = d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  return `${day}/${month}/${year}, ${time}`;
}

import React from 'react';
import { DollarSign, Plus, Trash2 } from 'lucide-react';
import { formatDate } from '../utils/date';


export default function DividendsModal({
  show,
  onClose,
  activePortfolio,
  dividends,
  totalDividends,
  divForm,
  setDivForm,
  onAddDividend,
  onDeleteDividend,
}) {
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
      <div className='modal-dialog modal-lg modal-dialog-scrollable modal-dialog-centered'>
        <div className='modal-content'>
          <div className='modal-header bg-light py-2 px-3 border-bottom'>
            <div className='d-flex align-items-center gap-2'>
              <DollarSign size={18} className='text-success' />
              <h5 className='modal-title fw-bold text-success mb-0'>
                Dividends Received — {activePortfolio}
              </h5>
              <span className='badge bg-success ms-2'>
                Total: ₹{totalDividends?.toLocaleString() || 0}
              </span>
            </div>
            <button
              type='button'
              className='btn-close'
              onClick={onClose}
              aria-label='Close'
            />
          </div>

          <div className='modal-body p-3'>
            <div className='row g-4'>
              <div className='col-12 col-lg-7'>
                <div className='d-flex justify-content-between align-items-center mb-2'>
                  <h6 className='fw-bold text-secondary mb-0'>
                    Recorded Dividends ({dividends.length})
                  </h6>
                  <span className='badge bg-primary'>
                    ₹{totalDividends?.toLocaleString() || 0}
                  </span>
                </div>
                <div
                  className='table-responsive border rounded'
                  style={{ maxHeight: '350px', overflow: 'auto', paddingBottom: '1.5rem' }}
                >
                  <table className='table table-sm table-hover table-striped align-middle mb-0 text-nowrap'>
                    <thead className='table-light'>
                      <tr style={{ fontSize: '0.82rem' }}>
                        <th>Stock Symbol</th>
                        <th className='text-end'>Dividend (₹)</th>
                        <th>Term / Received Date</th>
                        <th className='text-center'>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dividends.length === 0 ? (
                        <tr>
                          <td
                            colSpan={4}
                            className='text-center py-4 text-muted'
                          >
                            No dividends recorded for {activePortfolio}.
                          </td>
                        </tr>
                      ) : (
                        dividends.map((divItem) => (
                          <tr key={divItem.id}>
                            <td>
                              <strong>{divItem.symbol}</strong>
                            </td>
                            <td className='text-end fw-bold text-success'>
                              ₹{divItem.value?.toLocaleString()}
                            </td>
                            <td>{formatDate(divItem.received_date)}</td>
                            <td className='text-center'>
                              <button
                                type='button'
                                className='btn btn-sm btn-link text-danger p-0'
                                onClick={() => onDeleteDividend(divItem)}
                                title={`Delete dividend for ${divItem.symbol}`}
                              >
                                <Trash2 size={13} />
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                      {/* Clearance spacer so bottom rows are not hidden */}
                      <tr style={{ height: '24px' }}>
                        <td colSpan={4} className='p-0 border-0 bg-transparent'></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div className='col-12 col-lg-5'>
                <div className='p-3 border rounded bg-light'>
                  <h6 className='fw-bold mb-3'>Record New Dividend</h6>
                  <form onSubmit={onAddDividend}>
                    <div className='mb-2'>
                      <label className='form-label small mb-1'>
                        Stock Symbol *
                      </label>
                      <input
                        type='text'
                        className='form-control form-control-sm'
                        placeholder='e.g. TATAGOLD'
                        value={divForm.symbol}
                        onChange={(e) =>
                          setDivForm({ ...divForm, symbol: e.target.value })
                        }
                        required
                      />
                    </div>
                    <div className='mb-2'>
                      <label className='form-label small mb-1'>
                        Amount (₹) *
                      </label>
                      <input
                        type='number'
                        step='0.01'
                        className='form-control form-control-sm'
                        placeholder='e.g. 150'
                        value={divForm.value}
                        onChange={(e) =>
                          setDivForm({ ...divForm, value: e.target.value })
                        }
                        required
                      />
                    </div>
                    <div className='mb-3'>
                      <label className='form-label small mb-1'>
                        Received Date / Term
                      </label>
                      <input
                        type='text'
                        className='form-control form-control-sm'
                        placeholder='YYYY-MM-DD or term e.g. 21.07'
                        value={divForm.received_date}
                        onChange={(e) =>
                          setDivForm({
                            ...divForm,
                            received_date: e.target.value,
                          })
                        }
                      />
                    </div>
                    <button
                      type='submit'
                      className='btn btn-sm btn-success w-100'
                    >
                      <Plus
                        size={14}
                        className='me-1 inline-block'
                      />{' '}
                      Save Dividend
                    </button>
                  </form>
                </div>
              </div>
            </div>
          </div>

          <div className='modal-footer py-2 px-3 bg-light'>
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

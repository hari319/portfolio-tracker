import React, { useState } from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';
import PortfolioTable from './PortfolioTable';

export default function PortfolioSection({
  name,
  portfolioData = { rows: [] },
  periods = [9, 21, 50, 100, 200],
  onRemoveTicker,
  disabled = false,
  searchQuery = '',
}) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const rows = portfolioData.rows || [];
  const count = rows.length;
  const totalCount = portfolioData.totalCount !== undefined ? portfolioData.totalCount : count;

  return (
    <section className="dashboard-card mb-4" id={`portfolio-${name}`}>
      <header className="portfolio-header">
        <div className="d-flex align-items-center gap-2">
          <h2 className="portfolio-name">{name}</h2>
          <span className="portfolio-count-pill">
            {totalCount !== count
              ? `${count} of ${totalCount} ticker${totalCount === 1 ? '' : 's'}`
              : `${count} ticker${count === 1 ? '' : 's'}`}
          </span>
        </div>

        <button
          type="button"
          className="collapse-btn"
          onClick={() => setIsCollapsed(!isCollapsed)}
          aria-expanded={!isCollapsed}
          aria-controls={`table-${name}`}
        >
          {isCollapsed ? (
            <>
              <ChevronDown size={15} />
              <span>Expand</span>
            </>
          ) : (
            <>
              <ChevronUp size={15} />
              <span>Collapse</span>
            </>
          )}
        </button>
      </header>

      {!isCollapsed && (
        <div id={`table-${name}`}>
          <PortfolioTable
            portfolioName={name}
            rows={rows}
            periods={periods}
            onRemoveTicker={onRemoveTicker}
            disabled={disabled}
            searchQuery={searchQuery}
          />
        </div>
      )}
    </section>
  );
}

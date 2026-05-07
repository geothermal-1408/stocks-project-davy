import { useState, useEffect, useCallback } from 'react';
import { Users, Filter, RefreshCw, TrendingUp, TrendingDown, DollarSign, ArrowUpRight, ArrowDownRight, Search } from 'lucide-react';
import { fetchAdminInvestments } from '../api/client';
import type { AdminInvestmentView } from '../types';

export default function AdminInvestmentsPage() {
  const [investments, setInvestments] = useState<AdminInvestmentView[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState({
    total_invested_all: 0,
    total_withdrawn_all: 0,
    active_count: 0,
  });
  const [filters, setFilters] = useState({
    email: '',
    status: '',
    ticker: '',
  });
  const [appliedFilters, setAppliedFilters] = useState(filters);
  const limit = 15;

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchAdminInvestments(
        page,
        limit,
        appliedFilters.email || undefined,
        appliedFilters.status || undefined,
        appliedFilters.ticker || undefined,
      );
      setInvestments(data.investments || []);
      setTotal(data.total || 0);
      setStats({
        total_invested_all: data.total_invested_all || 0,
        total_withdrawn_all: data.total_withdrawn_all || 0,
        active_count: data.active_count || 0,
      });
    } catch (err) {
      console.error('Failed to load investments:', err);
    } finally {
      setLoading(false);
    }
  }, [page, appliedFilters]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const applyFilters = () => {
    setAppliedFilters({ ...filters });
    setPage(1);
  };

  const clearFilters = () => {
    const empty = { email: '', status: '', ticker: '' };
    setFilters(empty);
    setAppliedFilters(empty);
    setPage(1);
  };

  const totalPages = Math.ceil(total / limit);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="h-12 flex items-center justify-between px-4 border-b border-border shrink-0">
        <div className="flex items-center gap-3">
          <DollarSign size={18} className="text-accent-warning" />
          <h1 className="font-display font-bold text-base text-text-primary tracking-[0.3em]">
            INVESTMENT MONITOR
          </h1>
          <span className="px-1.5 py-0.5 bg-accent-warning/10 border border-accent-warning/30 text-accent-warning font-mono text-[9px]">
            ADMIN
          </span>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-1.5 px-3 py-1 border border-border text-text-muted hover:text-accent-mint hover:border-accent-mint/30 transition-all font-mono text-[10px]"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          REFRESH
        </button>
      </div>

      {/* Stats Bar */}
      <div className="flex items-center gap-4 px-4 py-3 border-b border-border bg-bg-card/50 shrink-0">
        <div className="flex items-center gap-6">
          <div>
            <div className="text-[9px] font-mono text-text-muted tracking-wider">TOTAL INVESTED</div>
            <div className="text-base font-mono font-bold text-accent-mint">
              ${stats.total_invested_all.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>
          <div className="h-8 w-px bg-border" />
          <div>
            <div className="text-[9px] font-mono text-text-muted tracking-wider">TOTAL WITHDRAWN</div>
            <div className="text-base font-mono font-bold text-accent-warning">
              ${stats.total_withdrawn_all.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>
          <div className="h-8 w-px bg-border" />
          <div>
            <div className="text-[9px] font-mono text-text-muted tracking-wider">ACTIVE POSITIONS</div>
            <div className="text-base font-mono font-bold text-accent-cyan">{stats.active_count}</div>
          </div>
          <div className="h-8 w-px bg-border" />
          <div>
            <div className="text-[9px] font-mono text-text-muted tracking-wider">TOTAL RECORDS</div>
            <div className="text-base font-mono font-bold text-text-primary">{total}</div>
          </div>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border shrink-0">
        <Filter size={14} className="text-text-muted" />
        <div className="relative">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="User email..."
            value={filters.email}
            onChange={(e) => setFilters(f => ({ ...f, email: e.target.value }))}
            className="bg-bg border border-border text-text-primary font-mono text-[10px] py-1.5 pl-7 pr-3 w-48 focus:outline-none focus:border-accent-mint/40 transition-colors"
          />
        </div>
        <select
          value={filters.status}
          onChange={(e) => setFilters(f => ({ ...f, status: e.target.value }))}
          className="bg-bg border border-border text-text-primary font-mono text-[10px] py-1.5 px-3 focus:outline-none focus:border-accent-mint/40 cursor-pointer"
        >
          <option value="">All Status</option>
          <option value="active">Active</option>
          <option value="withdrawn">Withdrawn</option>
        </select>
        <select
          value={filters.ticker}
          onChange={(e) => setFilters(f => ({ ...f, ticker: e.target.value }))}
          className="bg-bg border border-border text-text-primary font-mono text-[10px] py-1.5 px-3 focus:outline-none focus:border-accent-mint/40 cursor-pointer"
        >
          <option value="">All Tickers</option>
          <option value="AAPL">AAPL</option>
          <option value="MSFT">MSFT</option>
          <option value="GOOG">GOOG</option>
          <option value="NVDA">NVDA</option>
        </select>
        <button
          onClick={applyFilters}
          className="px-3 py-1.5 bg-accent-mint/10 text-accent-mint border border-accent-mint/30 font-mono text-[10px] hover:bg-accent-mint/20 transition-all"
        >
          APPLY
        </button>
        {(appliedFilters.email || appliedFilters.status || appliedFilters.ticker) && (
          <button
            onClick={clearFilters}
            className="px-3 py-1.5 text-text-muted border border-border font-mono text-[10px] hover:text-accent-danger hover:border-accent-danger/30 transition-all"
          >
            CLEAR
          </button>
        )}
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full min-w-[1100px]">
          <thead className="sticky top-0 bg-bg-card z-10">
            <tr className="border-b border-border">
              {['USER', 'TICKER', 'INVESTED', 'BUY PRICE', 'UNITS', 'CURRENT', 'P&L', 'P&L %', 'STATUS', 'DATE'].map((h) => (
                <th key={h} className="text-left text-[9px] font-mono text-text-muted tracking-wider py-2.5 px-3 font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i} className="border-b border-border/30">
                  <td colSpan={10} className="py-4 px-3">
                    <div className="h-5 loading-shimmer w-full" />
                  </td>
                </tr>
              ))
            ) : investments.length === 0 ? (
              <tr>
                <td colSpan={10} className="text-center py-12 text-text-muted font-mono text-sm">
                  No investments found
                </td>
              </tr>
            ) : (
              investments.map((inv) => {
                const pl = inv.profit_loss || 0;
                const plPct = inv.profit_loss_pct || 0;
                const isProfit = pl >= 0;
                const isActive = inv.status === 'active';

                return (
                  <tr
                    key={inv.id}
                    className="border-b border-border/20 hover:bg-bg-hover/30 transition-colors"
                  >
                    <td className="py-2.5 px-3">
                      <div className="font-mono text-[11px] text-text-primary">{inv.user_email}</div>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="font-mono text-[11px] text-accent-cyan font-medium">{inv.ticker}</span>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="font-mono text-[11px] text-text-primary">${inv.invested_amount.toFixed(2)}</span>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="font-mono text-[11px] text-text-primary">${inv.buy_price.toFixed(2)}</span>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="font-mono text-[11px] text-text-primary">{inv.units.toFixed(4)}</span>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="font-mono text-[11px] text-text-primary">
                        ${inv.current_price?.toFixed(2) || '—'}
                      </span>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className={`font-mono text-[11px] flex items-center gap-0.5 ${isProfit ? 'text-accent-mint' : 'text-accent-danger'}`}>
                        {isProfit ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                        {isProfit ? '+' : ''}${pl.toFixed(2)}
                      </span>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className={`font-mono text-[11px] ${isProfit ? 'text-accent-mint' : 'text-accent-danger'}`}>
                        {isProfit ? '+' : ''}{plPct.toFixed(2)}%
                      </span>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className={`px-2 py-0.5 text-[9px] font-mono tracking-wider ${
                        isActive
                          ? 'text-accent-mint bg-accent-mint/10 border border-accent-mint/20'
                          : 'text-text-muted bg-bg border border-border'
                      }`}>
                        {inv.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="font-mono text-[10px] text-text-muted">
                        {inv.created_at ? new Date(inv.created_at).toLocaleDateString('en-US', {
                          month: 'short', day: 'numeric', year: '2-digit'
                        }) : '—'}
                      </div>
                      {inv.withdrawn_at && (
                        <div className="font-mono text-[9px] text-accent-warning">
                          W: {new Date(inv.withdrawn_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-2.5 border-t border-border shrink-0">
          <div className="text-[10px] font-mono text-text-muted">
            Showing {((page - 1) * limit) + 1}–{Math.min(page * limit, total)} of {total}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 text-[10px] font-mono border border-border text-text-muted hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              PREV
            </button>
            <span className="px-3 py-1 text-[10px] font-mono text-accent-mint">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1 text-[10px] font-mono border border-border text-text-muted hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              NEXT
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

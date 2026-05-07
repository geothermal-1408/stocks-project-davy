import { useState, useEffect, useCallback } from 'react';
import { DollarSign, TrendingUp, TrendingDown, ArrowUpRight, ArrowDownRight, Wallet, RefreshCw, LogOut as WithdrawIcon, PieChart, Clock, Zap } from 'lucide-react';
import { buyStock, withdrawInvestment, fetchPortfolio } from '../api/client';
import { useAppStore } from '../store/appStore';
import type { Investment, PortfolioSummary } from '../types';

export default function PortfolioPage() {
  const { selectedTicker } = useAppStore();
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [buyAmount, setBuyAmount] = useState('');
  const [buyLoading, setBuyLoading] = useState(false);
  const [withdrawingId, setWithdrawingId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [activeTab, setActiveTab] = useState<'active' | 'withdrawn' | 'all'>('active');

  const loadPortfolio = useCallback(async () => {
    try {
      const data = await fetchPortfolio();
      setPortfolio(data);
    } catch (err) {
      console.error('Failed to load portfolio:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPortfolio();
    const interval = setInterval(loadPortfolio, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [loadPortfolio]);

  const handleBuy = async () => {
    const amount = parseFloat(buyAmount);
    if (isNaN(amount) || amount <= 0) {
      setMessage({ type: 'error', text: 'Enter a valid amount greater than 0' });
      return;
    }

    setBuyLoading(true);
    setMessage(null);
    try {
      const result = await buyStock(selectedTicker, amount);
      setMessage({
        type: 'success',
        text: `✓ Bought ${result.units?.toFixed(4)} units of ${selectedTicker} at $${result.buy_price?.toFixed(2)}/unit`,
      });
      setBuyAmount('');
      await loadPortfolio();
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Purchase failed' });
    } finally {
      setBuyLoading(false);
    }
  };

  const handleWithdraw = async (investmentId: string) => {
    setWithdrawingId(investmentId);
    setMessage(null);
    try {
      const result = await withdrawInvestment(investmentId);
      const pl = result.profit_loss;
      const plSign = pl >= 0 ? '+' : '';
      setMessage({
        type: pl >= 0 ? 'success' : 'error',
        text: `Withdrawn: $${result.withdraw_amount?.toFixed(2)} (P&L: ${plSign}$${pl?.toFixed(2)})`,
      });
      await loadPortfolio();
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Withdrawal failed' });
    } finally {
      setWithdrawingId(null);
    }
  };

  const filteredInvestments = portfolio?.investments?.filter(inv => {
    if (activeTab === 'active') return inv.status === 'active';
    if (activeTab === 'withdrawn') return inv.status === 'withdrawn';
    return true;
  }) || [];

  const quickAmounts = [100, 500, 1000, 5000];

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="h-12 flex items-center justify-between px-4 border-b border-border shrink-0">
        <div className="flex items-center gap-3">
          <Wallet size={18} className="text-accent-mint" />
          <h1 className="font-display font-bold text-base text-text-primary tracking-[0.3em]">PORTFOLIO</h1>
        </div>
        <button
          onClick={loadPortfolio}
          className="flex items-center gap-1.5 px-3 py-1 border border-border text-text-muted hover:text-accent-mint hover:border-accent-mint/30 transition-all font-mono text-[10px]"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          REFRESH
        </button>
      </div>

      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* Left: Buy Panel + Summary */}
        <div className="w-[380px] border-r border-border flex flex-col overflow-y-auto">
          {/* Portfolio Summary Cards */}
          <div className="p-4 space-y-3 border-b border-border">
            <div className="text-[10px] font-mono text-text-muted tracking-wider mb-2">PORTFOLIO OVERVIEW</div>
            
            {/* Total Value Card */}
            <div className="bg-bg-card border border-border p-4">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <div className="text-[10px] font-mono text-text-muted tracking-wider">TOTAL VALUE</div>
                  <div className="text-2xl font-mono font-bold text-text-primary mt-1">
                    ${(portfolio?.total_current_value || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>
                <div className={`flex items-center gap-1 px-2 py-1 text-xs font-mono ${
                  (portfolio?.total_profit_loss || 0) >= 0
                    ? 'text-accent-mint bg-accent-mint/10 border border-accent-mint/20'
                    : 'text-accent-danger bg-accent-danger/10 border border-accent-danger/20'
                }`}>
                  {(portfolio?.total_profit_loss || 0) >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                  {(portfolio?.total_profit_loss_pct || 0) >= 0 ? '+' : ''}
                  {(portfolio?.total_profit_loss_pct || 0).toFixed(2)}%
                </div>
              </div>
              <div className="flex gap-4 text-[10px] font-mono">
                <div>
                  <span className="text-text-muted">INVESTED</span>
                  <span className="text-text-primary ml-2">${(portfolio?.total_invested || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                </div>
                <div>
                  <span className="text-text-muted">P&L</span>
                  <span className={`ml-2 ${(portfolio?.total_profit_loss || 0) >= 0 ? 'text-accent-mint' : 'text-accent-danger'}`}>
                    {(portfolio?.total_profit_loss || 0) >= 0 ? '+' : ''}${(portfolio?.total_profit_loss || 0).toFixed(2)}
                  </span>
                </div>
              </div>
            </div>

            {/* Stats Row */}
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-bg-card border border-border p-3">
                <div className="text-[10px] font-mono text-text-muted">ACTIVE</div>
                <div className="text-lg font-mono font-bold text-accent-mint">{portfolio?.active_investments || 0}</div>
              </div>
              <div className="bg-bg-card border border-border p-3">
                <div className="text-[10px] font-mono text-text-muted">CLOSED</div>
                <div className="text-lg font-mono font-bold text-text-primary">{portfolio?.withdrawn_investments || 0}</div>
              </div>
            </div>
          </div>

          {/* Buy Panel */}
          <div className="p-4 border-b border-border">
            <div className="flex items-center gap-2 mb-3">
              <Zap size={14} className="text-accent-warning" />
              <span className="text-[10px] font-mono text-text-muted tracking-wider">BUY {selectedTicker} STOCK</span>
            </div>

            <div className="bg-bg-card border border-border p-4 space-y-4">
              {/* Amount Input */}
              <div>
                <label className="text-[10px] font-mono text-text-muted tracking-wider block mb-1.5">INVESTMENT AMOUNT (USD)</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted font-mono text-sm">$</span>
                  <input
                    type="number"
                    value={buyAmount}
                    onChange={(e) => setBuyAmount(e.target.value)}
                    placeholder="0.00"
                    min="1"
                    step="0.01"
                    className="w-full bg-bg border border-border text-text-primary font-mono text-sm py-2.5 pl-8 pr-4 focus:outline-none focus:border-accent-mint/50 transition-colors"
                  />
                </div>
              </div>

              {/* Quick Amount Buttons */}
              <div className="flex gap-2">
                {quickAmounts.map((amt) => (
                  <button
                    key={amt}
                    onClick={() => setBuyAmount(String(amt))}
                    className="flex-1 py-1.5 text-[10px] font-mono bg-bg border border-border text-text-muted hover:text-accent-mint hover:border-accent-mint/30 transition-all"
                  >
                    ${amt.toLocaleString()}
                  </button>
                ))}
              </div>

              {/* Estimated Units */}
              {buyAmount && parseFloat(buyAmount) > 0 && (
                <div className="bg-bg p-3 border border-border/50">
                  <div className="flex justify-between text-[10px] font-mono">
                    <span className="text-text-muted">EST. UNITS</span>
                    <span className="text-accent-cyan">
                      Based on current prediction
                    </span>
                  </div>
                  <div className="text-[10px] font-mono text-text-muted mt-1">
                    Units will be calculated at current ML-predicted price
                  </div>
                </div>
              )}

              {/* Buy Button */}
              <button
                onClick={handleBuy}
                disabled={buyLoading || !buyAmount || parseFloat(buyAmount) <= 0}
                className={`w-full py-3 font-mono text-sm font-bold tracking-wider transition-all ${
                  buyLoading || !buyAmount || parseFloat(buyAmount) <= 0
                    ? 'bg-bg-hover text-text-muted cursor-not-allowed border border-border'
                    : 'bg-accent-mint/10 text-accent-mint border border-accent-mint/40 hover:bg-accent-mint/20 hover:border-accent-mint/60'
                }`}
              >
                {buyLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <RefreshCw size={14} className="animate-spin" />
                    PROCESSING...
                  </span>
                ) : (
                  <span className="flex items-center justify-center gap-2">
                    <DollarSign size={14} />
                    BUY {selectedTicker}
                  </span>
                )}
              </button>
            </div>

            {/* Message */}
            {message && (
              <div className={`mt-3 p-3 border text-[11px] font-mono ${
                message.type === 'success'
                  ? 'border-accent-mint/30 bg-accent-mint/5 text-accent-mint'
                  : 'border-accent-danger/30 bg-accent-danger/5 text-accent-danger'
              }`}>
                {message.text}
              </div>
            )}
          </div>

          {/* Investment Philosophy */}
          <div className="p-4">
            <div className="bg-bg-card border border-border/50 p-3">
              <div className="text-[10px] font-mono text-accent-purple tracking-wider mb-2">HOW IT WORKS</div>
              <ul className="text-[10px] font-mono text-text-muted space-y-1.5 leading-relaxed">
                <li className="flex gap-2"><span className="text-accent-mint">01</span> Enter $ amount to invest</li>
                <li className="flex gap-2"><span className="text-accent-mint">02</span> Units calculated from ML prediction</li>
                <li className="flex gap-2"><span className="text-accent-mint">03</span> P&L updates with each prediction cycle</li>
                <li className="flex gap-2"><span className="text-accent-mint">04</span> Withdraw anytime to realize gains/losses</li>
              </ul>
            </div>
          </div>
        </div>

        {/* Right: Investment List */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Tabs */}
          <div className="flex items-center border-b border-border px-4 shrink-0">
            {(['active', 'withdrawn', 'all'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`py-3 px-4 text-[11px] font-mono tracking-wider border-b-2 transition-all ${
                  activeTab === tab
                    ? 'border-accent-mint text-accent-mint'
                    : 'border-transparent text-text-muted hover:text-text-primary'
                }`}
              >
                {tab.toUpperCase()}
                <span className="ml-2 text-[9px] opacity-60">
                  ({tab === 'active'
                    ? portfolio?.active_investments || 0
                    : tab === 'withdrawn'
                    ? portfolio?.withdrawn_investments || 0
                    : (portfolio?.active_investments || 0) + (portfolio?.withdrawn_investments || 0)
                  })
                </span>
              </button>
            ))}
          </div>

          {/* Investment Cards */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {loading ? (
              <div className="space-y-3">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="h-24 loading-shimmer border border-border" />
                ))}
              </div>
            ) : filteredInvestments.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-text-muted">
                <PieChart size={48} className="mb-4 opacity-20" />
                <p className="font-mono text-sm">
                  {activeTab === 'active'
                    ? 'No active investments'
                    : activeTab === 'withdrawn'
                    ? 'No withdrawn investments'
                    : 'No investments yet'}
                </p>
                <p className="font-mono text-[10px] mt-1 opacity-60">
                  Use the buy panel to start investing
                </p>
              </div>
            ) : (
              filteredInvestments.map((inv) => (
                <InvestmentCard
                  key={inv.id}
                  investment={inv}
                  onWithdraw={handleWithdraw}
                  withdrawing={withdrawingId === inv.id}
                />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}


function InvestmentCard({
  investment: inv,
  onWithdraw,
  withdrawing,
}: {
  investment: Investment;
  onWithdraw: (id: string) => void;
  withdrawing: boolean;
}) {
  const isActive = inv.status === 'active';
  const pl = inv.profit_loss || 0;
  const plPct = inv.profit_loss_pct || 0;
  const isProfit = pl >= 0;

  return (
    <div className={`bg-bg-card border transition-all hover:border-border/80 ${
      isActive ? 'border-border' : 'border-border/40 opacity-75'
    }`}>
      <div className="p-4">
        {/* Header Row */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className={`w-8 h-8 flex items-center justify-center font-mono text-xs font-bold border ${
              isActive
                ? 'border-accent-mint/40 text-accent-mint bg-accent-mint/5'
                : 'border-text-muted/20 text-text-muted bg-bg'
            }`}>
              {inv.ticker.slice(0, 2)}
            </div>
            <div>
              <div className="font-mono text-sm text-text-primary font-medium">{inv.ticker}</div>
              <div className="text-[9px] font-mono text-text-muted flex items-center gap-1">
                <Clock size={8} />
                {inv.created_at ? new Date(inv.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A'}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* P&L Badge */}
            <div className={`flex items-center gap-1 px-2 py-1 text-xs font-mono ${
              isProfit
                ? 'text-accent-mint bg-accent-mint/10 border border-accent-mint/20'
                : 'text-accent-danger bg-accent-danger/10 border border-accent-danger/20'
            }`}>
              {isProfit ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
              {isProfit ? '+' : ''}{plPct.toFixed(2)}%
            </div>

            {/* Status */}
            <span className={`px-2 py-0.5 text-[9px] font-mono tracking-wider ${
              isActive
                ? 'text-accent-mint bg-accent-mint/10 border border-accent-mint/20'
                : 'text-text-muted bg-bg border border-border'
            }`}>
              {inv.status.toUpperCase()}
            </span>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-4 gap-3 mb-3">
          <div>
            <div className="text-[9px] font-mono text-text-muted">INVESTED</div>
            <div className="text-sm font-mono text-text-primary">${inv.invested_amount.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-[9px] font-mono text-text-muted">BUY PRICE</div>
            <div className="text-sm font-mono text-text-primary">${inv.buy_price.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-[9px] font-mono text-text-muted">UNITS</div>
            <div className="text-sm font-mono text-accent-cyan">{inv.units.toFixed(4)}</div>
          </div>
          <div>
            <div className="text-[9px] font-mono text-text-muted">
              {isActive ? 'CURRENT' : 'SELL PRICE'}
            </div>
            <div className="text-sm font-mono text-text-primary">
              ${(isActive ? inv.current_price : inv.withdraw_price)?.toFixed(2) || '—'}
            </div>
          </div>
        </div>

        {/* P&L + Value Row */}
        <div className="flex items-center justify-between pt-3 border-t border-border/40">
          <div className="flex gap-6">
            <div>
              <div className="text-[9px] font-mono text-text-muted">
                {isActive ? 'CURRENT VALUE' : 'WITHDRAWN AMOUNT'}
              </div>
              <div className="text-sm font-mono font-medium text-text-primary">
                ${isActive
                  ? ((inv.current_price || inv.buy_price) * inv.units).toFixed(2)
                  : inv.withdraw_amount?.toFixed(2) || '—'}
              </div>
            </div>
            <div>
              <div className="text-[9px] font-mono text-text-muted">PROFIT/LOSS</div>
              <div className={`text-sm font-mono font-medium ${isProfit ? 'text-accent-mint' : 'text-accent-danger'}`}>
                {isProfit ? '+' : ''}${pl.toFixed(2)}
              </div>
            </div>
            {inv.prediction_direction && (
              <div>
                <div className="text-[9px] font-mono text-text-muted">SIGNAL</div>
                <div className={`text-sm font-mono ${
                  inv.prediction_direction === 'up' ? 'text-accent-mint' : 'text-accent-danger'
                }`}>
                  {inv.prediction_direction === 'up' ? '↑ BULL' : '↓ BEAR'}
                </div>
              </div>
            )}
          </div>

          {/* Withdraw Button */}
          {isActive && (
            <button
              onClick={() => onWithdraw(inv.id)}
              disabled={withdrawing}
              className={`flex items-center gap-1.5 px-4 py-2 text-[10px] font-mono font-bold tracking-wider transition-all ${
                withdrawing
                  ? 'bg-bg text-text-muted border border-border cursor-wait'
                  : 'bg-accent-warning/10 text-accent-warning border border-accent-warning/30 hover:bg-accent-warning/20 hover:border-accent-warning/50'
              }`}
            >
              {withdrawing ? (
                <RefreshCw size={12} className="animate-spin" />
              ) : (
                <WithdrawIcon size={12} />
              )}
              {withdrawing ? 'PROCESSING...' : 'WITHDRAW'}
            </button>
          )}

          {/* Withdrawn timestamp */}
          {!isActive && inv.withdrawn_at && (
            <div className="text-[9px] font-mono text-text-muted">
              Withdrawn {new Date(inv.withdrawn_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

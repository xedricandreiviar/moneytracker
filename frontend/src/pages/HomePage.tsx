/**
 * HomePage — Full financial dashboard showing balance, spending summary,
 * budget progress, streak, daily task, notifications, and quick actions.
 * Integrates StreakBadge, DailyTaskBanner, NotificationBanner, InsightBanner,
 * and CurrencyDisplay components.
 * Requirements: 1.2, 7.1, 7.2, 12.1, 18.1–18.5
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { StreakBadge } from '../components/StreakBadge';
import { DailyTaskBanner } from '../components/DailyTaskBanner';
import { NotificationBanner } from '../components/NotificationBanner';
import { CurrencyDisplay } from '../components/CurrencyDisplay';
import { useLocale } from '../contexts/LocaleContext';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// --- Interfaces ---

interface CategoryBreakdown {
  category_name: string;
  total_spent: number;
  total_received: number;
  budget_limit: number | null;
  weight_percentage: number | null;
}

interface DashboardSummary {
  period_type: string;
  total_income: number;
  total_expenses: number;
  balance: number;
  category_breakdown: CategoryBreakdown[];
}

interface InsightData {
  insight_text: string;
  category_focus: string | null;
}

interface Transaction {
  id: number;
  amount_smallest_unit: number;
  direction: string;
  currency_code: string;
}

interface TransactionListResponse {
  transactions: Transaction[];
  count: number;
}

type PeriodOption = 'daily' | 'weekly' | 'monthly';

// --- Component ---

export default function HomePage() {
  const navigate = useNavigate();
  const { locale } = useLocale();

  const [period, setPeriod] = useState<PeriodOption>('daily');
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);

  const [availableBalance, setAvailableBalance] = useState<number>(0);
  const [balanceLoading, setBalanceLoading] = useState(true);

  const [insight, setInsight] = useState<InsightData | null>(null);
  const [insightReady, setInsightReady] = useState(false);

  const [fabOpen, setFabOpen] = useState(false);
  const fabRef = useRef<HTMLDivElement>(null);

  const currencyCode = locale?.currency_code || 'PHP';

  // Fetch dashboard summary for selected period
  const fetchSummary = useCallback(async (p: PeriodOption) => {
    setSummaryLoading(true);
    try {
      const response = await axios.get<DashboardSummary>(
        `${API_BASE}/api/dashboard/summary?period=${p}`
      );
      setSummary(response.data);
    } catch {
      setSummary(null);
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  // Fetch all transactions to compute available balance
  const fetchAvailableBalance = useCallback(async () => {
    try {
      const response = await axios.get<TransactionListResponse>(
        `${API_BASE}/api/transactions?limit=500`
      );
      const transactions = response.data.transactions || [];
      let totalReceived = 0;
      let totalSpent = 0;
      for (const txn of transactions) {
        if (txn.direction === 'received') {
          totalReceived += txn.amount_smallest_unit;
        } else {
          totalSpent += txn.amount_smallest_unit;
        }
      }
      setAvailableBalance(totalReceived - totalSpent);
    } catch {
      setAvailableBalance(0);
    } finally {
      setBalanceLoading(false);
    }
  }, []);

  // Fetch personalized insight
  const fetchInsight = useCallback(async () => {
    try {
      const response = await axios.get<InsightData>(`${API_BASE}/api/dashboard/insight`);
      setInsight(response.data);
    } catch {
      setInsight(null);
    } finally {
      setInsightReady(true);
    }
  }, []);

  useEffect(() => {
    fetchSummary(period);
  }, [period, fetchSummary]);

  useEffect(() => {
    fetchAvailableBalance();
    fetchInsight();
  }, [fetchAvailableBalance, fetchInsight]);

  // Refresh on page visibility change
  useEffect(() => {
    function handleVisibilityChange() {
      if (document.visibilityState === 'visible') {
        fetchSummary(period);
        fetchAvailableBalance();
        fetchInsight();
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [period, fetchSummary, fetchAvailableBalance, fetchInsight]);

  // Close FAB when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (fabOpen && fabRef.current && !fabRef.current.contains(e.target as Node)) {
        setFabOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [fabOpen]);

  // Period display labels
  const periodLabels: Record<PeriodOption, string> = {
    daily: 'Today',
    weekly: 'This Week',
    monthly: 'This Month',
  };

  // Category budget cards with progress
  const budgetCategories = (summary?.category_breakdown || []).filter(
    (cat) => cat.budget_limit !== null && cat.budget_limit > 0
  );

  return (
    <div style={styles.page}>
      {/* Header bar */}
      <header style={styles.header}>
        <h1 style={styles.appName}>Daily Money Tracker</h1>
        <button
          type="button"
          onClick={() => navigate('/settings')}
          style={styles.settingsButton}
          aria-label="Settings"
        >
          ⚙️
        </button>
      </header>

      {/* Streak badge and daily task */}
      <StreakBadge />
      <DailyTaskBanner />

      {/* Notification banner */}
      <NotificationBanner />

      {/* Available Balance card */}
      <div style={styles.balanceCard} role="region" aria-label="Available balance">
        <span style={styles.balanceLabel}>Available Balance</span>
        {balanceLoading ? (
          <span style={styles.balanceAmount}>...</span>
        ) : (
          <span
            style={{
              ...styles.balanceAmount,
              color: availableBalance >= 0 ? '#111827' : '#dc2626',
            }}
          >
            <CurrencyDisplay amount={Math.abs(availableBalance)} currencyCode={currencyCode} />
            {availableBalance < 0 && <span style={{ fontSize: '0.9rem' }}> (deficit)</span>}
          </span>
        )}
      </div>

      {/* Period selector */}
      <div style={styles.periodSelector} role="group" aria-label="Time period selector">
        {(['daily', 'weekly', 'monthly'] as PeriodOption[]).map((opt) => (
          <button
            key={opt}
            type="button"
            onClick={() => setPeriod(opt)}
            style={{
              ...styles.periodPill,
              ...(period === opt ? styles.periodPillActive : {}),
            }}
            aria-pressed={period === opt}
          >
            {periodLabels[opt]}
          </button>
        ))}
      </div>

      {/* Spending summary for selected period */}
      {!summaryLoading && summary && (
        <div style={styles.spendingSummary} role="region" aria-label="Spending summary">
          <div style={styles.summaryRow}>
            <div style={styles.summaryItem}>
              <span style={styles.summaryLabel}>Total Received</span>
              <span style={{ ...styles.summaryValue, color: '#16a34a' }}>
                <CurrencyDisplay amount={summary.total_income} currencyCode={currencyCode} />
              </span>
            </div>
            <div style={styles.summaryItem}>
              <span style={styles.summaryLabel}>Total Spent</span>
              <span style={{ ...styles.summaryValue, color: '#dc2626' }}>
                <CurrencyDisplay amount={summary.total_expenses} currencyCode={currencyCode} />
              </span>
            </div>
          </div>
          <div style={styles.netRow}>
            <span style={styles.netLabel}>Net ({periodLabels[period]})</span>
            <span
              style={{
                ...styles.netValue,
                color: summary.balance >= 0 ? '#16a34a' : '#dc2626',
              }}
            >
              {summary.balance < 0 ? '-' : '+'}
              <CurrencyDisplay amount={Math.abs(summary.balance)} currencyCode={currencyCode} />
            </span>
          </div>
        </div>
      )}

      {summaryLoading && (
        <div style={styles.loadingPlaceholder}>Loading summary...</div>
      )}

      {/* Category budget cards */}
      {budgetCategories.length > 0 && (
        <section style={styles.budgetSection} aria-label="Category budgets">
          <h2 style={styles.sectionTitle}>Budget Progress</h2>
          <div style={styles.budgetGrid}>
            {budgetCategories.map((cat) => {
              const limit = cat.budget_limit!;
              const spent = cat.total_spent;
              const remaining = limit - spent;
              const pct = limit > 0 ? (spent / limit) * 100 : 0;
              const clampedPct = Math.min(pct, 100);

              let barColor = '#16a34a'; // green
              if (pct >= 100) {
                barColor = '#dc2626'; // red
              } else if (pct >= 80) {
                barColor = '#f59e0b'; // orange
              }

              let statusColor = '#16a34a';
              let statusText = '';
              if (remaining > 0) {
                if (pct >= 80) {
                  statusColor = '#f59e0b';
                }
                statusText = 'remaining';
              } else {
                statusColor = '#dc2626';
                statusText = 'over';
              }

              return (
                <div key={cat.category_name} style={styles.budgetCard} role="article" aria-label={`${cat.category_name} budget`}>
                  <div style={styles.budgetCardHeader}>
                    <span style={styles.budgetCategoryName}>{cat.category_name}</span>
                    <span style={{ ...styles.budgetStatus, color: statusColor }}>
                      <CurrencyDisplay amount={Math.abs(remaining)} currencyCode={currencyCode} />
                      {' '}{statusText}
                    </span>
                  </div>
                  {/* Progress bar */}
                  <div style={styles.progressTrack}>
                    <div
                      style={{
                        ...styles.progressFill,
                        width: `${clampedPct}%`,
                        background: barColor,
                      }}
                      role="progressbar"
                      aria-valuenow={Math.round(pct)}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`${cat.category_name} budget used ${Math.round(pct)}%`}
                    />
                  </div>
                  <div style={styles.budgetFooter}>
                    <span style={styles.budgetSpentText}>
                      <CurrencyDisplay amount={spent} currencyCode={currencyCode} /> spent
                    </span>
                    <span style={styles.budgetLimitText}>
                      of <CurrencyDisplay amount={limit} currencyCode={currencyCode} />
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Personalized insight banner */}
      {insightReady && insight && insight.insight_text && (
        <div
          style={styles.insightBanner}
          role="region"
          aria-label="Personalized insight"
        >
          <div style={styles.insightHeader}>
            <span style={styles.insightIcon} aria-hidden="true">💡</span>
            <span style={styles.insightTitle}>
              {insight.category_focus ? `${insight.category_focus} Tip` : 'Insight'}
            </span>
          </div>
          <p style={styles.insightText}>{insight.insight_text}</p>
        </div>
      )}

      {/* Bottom spacing for FABs */}
      <div style={{ height: '5rem' }} />

      {/* Quick Add floating button — bottom-left */}
      <button
        type="button"
        onClick={() => navigate('/quick-add')}
        style={styles.quickAddFab}
        aria-label="Quick add transaction"
      >
        +
      </button>

      {/* AI FAB — bottom-right */}
      <div ref={fabRef} style={styles.aiFabContainer}>
        {fabOpen && (
          <div style={styles.fabMenu}>
            <button
              type="button"
              onClick={() => { navigate('/ai-chat'); setFabOpen(false); }}
              style={styles.fabMenuItem}
            >
              🤖 AI Chat
            </button>
            <button
              type="button"
              onClick={() => { navigate('/ai-coaching'); setFabOpen(false); }}
              style={styles.fabMenuItem}
            >
              💡 Coaching
            </button>
          </div>
        )}
        <button
          type="button"
          onClick={() => setFabOpen(!fabOpen)}
          style={{
            ...styles.aiFab,
            ...(fabOpen ? styles.aiFabOpen : {}),
          }}
          aria-label={fabOpen ? 'Close AI menu' : 'Open AI menu'}
          aria-expanded={fabOpen}
        >
          ↑
        </button>
      </div>
    </div>
  );
}

// --- Styles ---

const styles: Record<string, React.CSSProperties> = {
  page: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
    paddingBottom: '2rem',
    position: 'relative',
    minHeight: '100vh',
  },

  // Header
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: '0.25rem',
  },
  appName: {
    fontSize: '1.35rem',
    fontWeight: '700',
    margin: 0,
    color: '#111827',
  },
  settingsButton: {
    background: 'none',
    border: 'none',
    fontSize: '1.5rem',
    cursor: 'pointer',
    padding: '0.25rem',
    lineHeight: 1,
  },

  // Balance card
  balanceCard: {
    background: '#fff',
    border: '1px solid #e5e7eb',
    borderRadius: '12px',
    padding: '1.25rem 1rem',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '0.375rem',
  },
  balanceLabel: {
    fontSize: '0.85rem',
    color: '#6b7280',
    fontWeight: '500',
  },
  balanceAmount: {
    fontSize: '1.75rem',
    fontWeight: '800',
    color: '#111827',
  },

  // Period selector
  periodSelector: {
    display: 'flex',
    gap: '0.5rem',
    justifyContent: 'center',
  },
  periodPill: {
    padding: '0.5rem 1rem',
    borderRadius: '20px',
    border: '1px solid #e5e7eb',
    background: '#fff',
    fontSize: '0.8rem',
    fontWeight: '600',
    color: '#6b7280',
    cursor: 'pointer',
    transition: 'all 0.15s',
  },
  periodPillActive: {
    background: '#111827',
    color: '#fff',
    border: '1px solid #111827',
  },

  // Spending summary
  spendingSummary: {
    background: '#fff',
    border: '1px solid #e5e7eb',
    borderRadius: '12px',
    padding: '1rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  summaryRow: {
    display: 'flex',
    justifyContent: 'space-between',
    gap: '0.5rem',
  },
  summaryItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.125rem',
    flex: 1,
  },
  summaryLabel: {
    fontSize: '0.75rem',
    color: '#6b7280',
    fontWeight: '500',
  },
  summaryValue: {
    fontSize: '1.1rem',
    fontWeight: '700',
  },
  netRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderTop: '1px solid #f3f4f6',
    paddingTop: '0.625rem',
  },
  netLabel: {
    fontSize: '0.8rem',
    color: '#374151',
    fontWeight: '600',
  },
  netValue: {
    fontSize: '1.05rem',
    fontWeight: '700',
  },

  // Loading
  loadingPlaceholder: {
    textAlign: 'center',
    color: '#9ca3af',
    fontSize: '0.85rem',
    padding: '1rem 0',
  },

  // Budget section
  budgetSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  sectionTitle: {
    fontSize: '1rem',
    fontWeight: '600',
    margin: 0,
    color: '#111827',
  },
  budgetGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  budgetCard: {
    background: '#fff',
    border: '1px solid #e5e7eb',
    borderRadius: '10px',
    padding: '0.875rem 1rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  budgetCardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  budgetCategoryName: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#374151',
  },
  budgetStatus: {
    fontSize: '0.8rem',
    fontWeight: '600',
  },

  // Progress bar
  progressTrack: {
    height: '8px',
    borderRadius: '4px',
    background: '#e5e7eb',
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: '4px',
    transition: 'width 0.3s ease',
  },
  budgetFooter: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: '0.75rem',
    color: '#6b7280',
  },
  budgetSpentText: {
    fontWeight: '500',
  },
  budgetLimitText: {
    fontWeight: '400',
  },

  // Insight banner
  insightBanner: {
    border: '1px solid #e5e7eb',
    borderRadius: '10px',
    padding: '0.75rem 1rem',
    background: '#fff',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  insightHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.375rem',
  },
  insightIcon: {
    fontSize: '1rem',
    lineHeight: 1,
  },
  insightTitle: {
    fontSize: '0.85rem',
    fontWeight: '600',
    color: '#374151',
  },
  insightText: {
    fontSize: '0.8rem',
    color: '#4b5563',
    margin: 0,
    lineHeight: '1.4',
  },

  // Quick Add FAB (bottom-left)
  quickAddFab: {
    position: 'fixed',
    bottom: '1.5rem',
    left: '1.5rem',
    width: '56px',
    height: '56px',
    borderRadius: '50%',
    background: '#16a34a',
    color: '#fff',
    fontSize: '1.75rem',
    fontWeight: '700',
    border: 'none',
    cursor: 'pointer',
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.2)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    lineHeight: 1,
    zIndex: 1000,
  },

  // AI FAB (bottom-right)
  aiFabContainer: {
    position: 'fixed',
    bottom: '1.5rem',
    right: '1.5rem',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-end',
    gap: '0.5rem',
    zIndex: 1000,
  },
  fabMenu: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
    marginBottom: '0.5rem',
  },
  fabMenuItem: {
    padding: '0.625rem 1rem',
    borderRadius: '24px',
    border: 'none',
    background: '#1f2937',
    color: '#fff',
    fontSize: '0.85rem',
    fontWeight: '600',
    cursor: 'pointer',
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
    whiteSpace: 'nowrap',
  },
  aiFab: {
    width: '56px',
    height: '56px',
    borderRadius: '50%',
    background: '#1f2937',
    color: '#fff',
    fontSize: '1.5rem',
    fontWeight: '700',
    border: 'none',
    cursor: 'pointer',
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.2)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    lineHeight: 1,
    transition: 'transform 0.2s',
  },
  aiFabOpen: {
    transform: 'rotate(180deg)',
  },
};

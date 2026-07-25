/**
 * InsightsPage - Displays weekly/monthly spending summaries and spike alerts.
 * Shows category breakdowns with percentage changes vs prior period.
 * Displays spike alerts with category name, current total, and 4-week average.
 * All amounts formatted using locale settings via CurrencyDisplay.
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.8, 6.4
 */
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useLocale } from '../contexts/LocaleContext';
import { CurrencyDisplay } from '../components/CurrencyDisplay';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

type TabType = 'weekly' | 'monthly';

interface CategoryTotal {
  category_name: string;
  total_spent: number;
  total_received: number;
  percentage_change: number | null;
  is_new: boolean;
}

interface WeeklySummary {
  user_id: number;
  week_start: string;
  week_end: string;
  total_spent: number;
  total_received: number;
  net: number;
  category_totals: CategoryTotal[];
  has_prior_period: boolean;
  generated_at: string | null;
}

interface MonthlySummary {
  user_id: number;
  month: number;
  year: number;
  total_spent: number;
  total_received: number;
  net: number;
  category_totals: CategoryTotal[];
  total_spent_change: number | null;
  total_received_change: number | null;
  total_spent_abs_change: number | null;
  total_received_abs_change: number | null;
  has_prior_period: boolean;
  generated_at: string | null;
}

interface SpendingSpike {
  category_name: string;
  current_total: number;
  rolling_average: number;
  threshold_percentage: number;
}

interface SpikesResponse {
  spikes: SpendingSpike[];
  detected_at: string | null;
}

export default function InsightsPage() {
  const { locale } = useLocale();

  const [activeTab, setActiveTab] = useState<TabType>('weekly');

  // Weekly summary state
  const [weeklySummary, setWeeklySummary] = useState<WeeklySummary | null>(null);
  const [weeklyLoading, setWeeklyLoading] = useState(true);
  const [weeklyError, setWeeklyError] = useState<string | null>(null);

  // Monthly summary state
  const [monthlySummary, setMonthlySummary] = useState<MonthlySummary | null>(null);
  const [monthlyLoading, setMonthlyLoading] = useState(true);
  const [monthlyError, setMonthlyError] = useState<string | null>(null);

  // Spike alerts state
  const [spikes, setSpikes] = useState<SpendingSpike[]>([]);
  const [spikesLoading, setSpikesLoading] = useState(true);
  const [spikesError, setSpikesError] = useState<string | null>(null);

  useEffect(() => {
    fetchWeeklySummary();
    fetchMonthlySummary();
    fetchSpikes();
  }, []);

  const fetchWeeklySummary = useCallback(async () => {
    setWeeklyLoading(true);
    try {
      const response = await axios.get(`${API_BASE}/api/insights/weekly`);
      setWeeklySummary(response.data);
      setWeeklyError(null);
    } catch {
      setWeeklyError('Failed to load weekly summary. Please try again.');
    } finally {
      setWeeklyLoading(false);
    }
  }, []);

  const fetchMonthlySummary = useCallback(async () => {
    setMonthlyLoading(true);
    try {
      const response = await axios.get(`${API_BASE}/api/insights/monthly`);
      setMonthlySummary(response.data);
      setMonthlyError(null);
    } catch {
      setMonthlyError('Failed to load monthly summary. Please try again.');
    } finally {
      setMonthlyLoading(false);
    }
  }, []);

  const fetchSpikes = useCallback(async () => {
    setSpikesLoading(true);
    try {
      const response = await axios.get<SpikesResponse>(`${API_BASE}/api/insights/spikes`);
      setSpikes(response.data.spikes || []);
      setSpikesError(null);
    } catch {
      setSpikesError('Failed to load spike alerts.');
    } finally {
      setSpikesLoading(false);
    }
  }, []);

  if (!locale) {
    return (
      <div className="page page-insights">
        <p>Loading...</p>
      </div>
    );
  }

  const currencyCode = locale.currency_code;

  return (
    <div className="page page-insights" style={styles.page}>
      <h1 style={styles.heading}>Insights</h1>

      {/* Spike alerts section */}
      {!spikesLoading && spikes.length > 0 && (
        <div style={styles.spikesSection}>
          <h2 style={styles.sectionTitle}>⚠️ Spending Spikes</h2>
          {spikes.map((spike) => (
            <div key={spike.category_name} style={styles.spikeCard} role="alert">
              <div style={styles.spikeHeader}>
                <span style={styles.spikeCategoryName}>{spike.category_name}</span>
                <span style={styles.spikeBadge}>Spike</span>
              </div>
              <div style={styles.spikeDetails}>
                <div style={styles.spikeRow}>
                  <span style={styles.spikeLabel}>Current total</span>
                  <span style={styles.spikeValue}>
                    <CurrencyDisplay amount={spike.current_total} currencyCode={currencyCode} />
                  </span>
                </div>
                <div style={styles.spikeRow}>
                  <span style={styles.spikeLabel}>4-week average</span>
                  <span style={styles.spikeValue}>
                    <CurrencyDisplay amount={Math.round(spike.rolling_average)} currencyCode={currencyCode} />
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {spikesError && (
        <div style={styles.errorBanner} role="alert">
          <span>{spikesError}</span>
          <button type="button" onClick={fetchSpikes} style={styles.retryButton} aria-label="Retry loading spikes">
            Retry
          </button>
        </div>
      )}

      {/* Tab toggle for weekly/monthly */}
      <div style={styles.tabToggle} role="tablist" aria-label="Summary period">
        <button
          type="button"
          role="tab"
          onClick={() => setActiveTab('weekly')}
          style={{
            ...styles.tabButton,
            ...(activeTab === 'weekly' ? styles.tabButtonActive : {}),
          }}
          aria-selected={activeTab === 'weekly'}
          aria-controls="panel-weekly"
        >
          Weekly
        </button>
        <button
          type="button"
          role="tab"
          onClick={() => setActiveTab('monthly')}
          style={{
            ...styles.tabButton,
            ...(activeTab === 'monthly' ? styles.tabButtonActive : {}),
          }}
          aria-selected={activeTab === 'monthly'}
          aria-controls="panel-monthly"
        >
          Monthly
        </button>
      </div>

      {/* Weekly panel */}
      {activeTab === 'weekly' && (
        <div id="panel-weekly" role="tabpanel" aria-label="Weekly summary">
          {weeklyLoading ? (
            <p style={styles.loadingText}>Loading weekly summary...</p>
          ) : weeklyError ? (
            <div style={styles.errorBanner} role="alert">
              <span>{weeklyError}</span>
              <button type="button" onClick={fetchWeeklySummary} style={styles.retryButton} aria-label="Retry loading weekly summary">
                Retry
              </button>
            </div>
          ) : weeklySummary ? (
            <WeeklySummaryPanel summary={weeklySummary} currencyCode={currencyCode} />
          ) : (
            <p style={styles.emptyText}>No weekly summary available.</p>
          )}
        </div>
      )}

      {/* Monthly panel */}
      {activeTab === 'monthly' && (
        <div id="panel-monthly" role="tabpanel" aria-label="Monthly summary">
          {monthlyLoading ? (
            <p style={styles.loadingText}>Loading monthly summary...</p>
          ) : monthlyError ? (
            <div style={styles.errorBanner} role="alert">
              <span>{monthlyError}</span>
              <button type="button" onClick={fetchMonthlySummary} style={styles.retryButton} aria-label="Retry loading monthly summary">
                Retry
              </button>
            </div>
          ) : monthlySummary ? (
            <MonthlySummaryPanel summary={monthlySummary} currencyCode={currencyCode} />
          ) : (
            <p style={styles.emptyText}>No monthly summary available.</p>
          )}
        </div>
      )}
    </div>
  );
}

/** Renders the weekly summary card with totals and category breakdown */
function WeeklySummaryPanel({ summary, currencyCode }: { summary: WeeklySummary; currencyCode: string }) {
  return (
    <div style={styles.summaryCard}>
      <div style={styles.summaryHeader}>
        <span style={styles.periodLabel}>
          {formatDateLabel(summary.week_start)} — {formatDateLabel(summary.week_end)}
        </span>
        {!summary.has_prior_period && (
          <span style={styles.noPriorBadge}>First week</span>
        )}
      </div>

      {/* Overall totals */}
      <div style={styles.totalsGrid}>
        <div style={styles.totalItem}>
          <span style={styles.totalLabel}>Spent</span>
          <span style={{ ...styles.totalValue, color: '#dc2626' }}>
            <CurrencyDisplay amount={summary.total_spent} currencyCode={currencyCode} />
          </span>
        </div>
        <div style={styles.totalItem}>
          <span style={styles.totalLabel}>Received</span>
          <span style={{ ...styles.totalValue, color: '#16a34a' }}>
            <CurrencyDisplay amount={summary.total_received} currencyCode={currencyCode} />
          </span>
        </div>
        <div style={styles.totalItem}>
          <span style={styles.totalLabel}>Net</span>
          <span style={{ ...styles.totalValue, color: summary.net >= 0 ? '#16a34a' : '#dc2626' }}>
            {summary.net < 0 ? '-' : ''}
            <CurrencyDisplay amount={Math.abs(summary.net)} currencyCode={currencyCode} />
          </span>
        </div>
      </div>

      {/* Category breakdown */}
      {summary.category_totals.length > 0 && (
        <CategoryBreakdown
          categories={summary.category_totals}
          currencyCode={currencyCode}
          hasPriorPeriod={summary.has_prior_period}
        />
      )}
    </div>
  );
}

/** Renders the monthly summary card with totals, comparison, and category breakdown */
function MonthlySummaryPanel({ summary, currencyCode }: { summary: MonthlySummary; currencyCode: string }) {
  const monthName = getMonthName(summary.month);

  return (
    <div style={styles.summaryCard}>
      <div style={styles.summaryHeader}>
        <span style={styles.periodLabel}>
          {monthName} {summary.year}
        </span>
        {!summary.has_prior_period && (
          <span style={styles.noPriorBadge}>First month</span>
        )}
      </div>

      {/* Overall totals */}
      <div style={styles.totalsGrid}>
        <div style={styles.totalItem}>
          <span style={styles.totalLabel}>Spent</span>
          <span style={{ ...styles.totalValue, color: '#dc2626' }}>
            <CurrencyDisplay amount={summary.total_spent} currencyCode={currencyCode} />
          </span>
          {summary.has_prior_period && summary.total_spent_change !== null && (
            <PercentageChangeIndicator change={summary.total_spent_change} />
          )}
        </div>
        <div style={styles.totalItem}>
          <span style={styles.totalLabel}>Received</span>
          <span style={{ ...styles.totalValue, color: '#16a34a' }}>
            <CurrencyDisplay amount={summary.total_received} currencyCode={currencyCode} />
          </span>
          {summary.has_prior_period && summary.total_received_change !== null && (
            <PercentageChangeIndicator change={summary.total_received_change} />
          )}
        </div>
        <div style={styles.totalItem}>
          <span style={styles.totalLabel}>Net</span>
          <span style={{ ...styles.totalValue, color: summary.net >= 0 ? '#16a34a' : '#dc2626' }}>
            {summary.net < 0 ? '-' : ''}
            <CurrencyDisplay amount={Math.abs(summary.net)} currencyCode={currencyCode} />
          </span>
        </div>
      </div>

      {/* Category breakdown */}
      {summary.category_totals.length > 0 && (
        <CategoryBreakdown
          categories={summary.category_totals}
          currencyCode={currencyCode}
          hasPriorPeriod={summary.has_prior_period}
        />
      )}
    </div>
  );
}

/** Renders the category breakdown table with percentage change indicators */
function CategoryBreakdown({
  categories,
  currencyCode,
  hasPriorPeriod,
}: {
  categories: CategoryTotal[];
  currencyCode: string;
  hasPriorPeriod: boolean;
}) {
  return (
    <div style={styles.categorySection}>
      <h3 style={styles.categoryTitle}>By Category</h3>
      <div style={styles.categoryList}>
        {categories.map((cat) => (
          <div key={cat.category_name} style={styles.categoryRow}>
            <div style={styles.categoryNameCol}>
              <span style={styles.categoryName}>{cat.category_name}</span>
              {hasPriorPeriod && (
                <span style={styles.changeIndicator}>
                  {cat.is_new ? (
                    <span style={styles.newBadge}>new</span>
                  ) : cat.percentage_change !== null ? (
                    <PercentageChangeIndicator change={cat.percentage_change} />
                  ) : null}
                </span>
              )}
            </div>
            <div style={styles.categoryAmountCol}>
              <CurrencyDisplay amount={cat.total_spent} currencyCode={currencyCode} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Shows a percentage change value with color and arrow indicator */
function PercentageChangeIndicator({ change }: { change: number }) {
  const isPositive = change > 0;
  const isNegative = change < 0;
  const arrow = isPositive ? '↑' : isNegative ? '↓' : '';
  const color = isPositive ? '#dc2626' : isNegative ? '#16a34a' : '#6b7280';

  return (
    <span style={{ ...styles.percentChange, color }} aria-label={`${change > 0 ? '+' : ''}${change.toFixed(1)}%`}>
      {arrow} {Math.abs(change).toFixed(1)}%
    </span>
  );
}

// --- Helpers ---

function formatDateLabel(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function getMonthName(month: number): string {
  const date = new Date(2024, month - 1, 1);
  return date.toLocaleDateString(undefined, { month: 'long' });
}

// --- Styles ---

const styles: Record<string, React.CSSProperties> = {
  page: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
    paddingBottom: '2rem',
  },
  heading: {
    fontSize: '1.5rem',
    fontWeight: '700',
    margin: 0,
  },
  sectionTitle: {
    fontSize: '1rem',
    fontWeight: '600',
    margin: '0 0 0.5rem 0',
    color: '#111827',
  },
  loadingText: {
    textAlign: 'center' as const,
    color: '#6b7280',
    padding: '2rem 1rem',
  },
  emptyText: {
    textAlign: 'center' as const,
    color: '#9ca3af',
    padding: '2rem 1rem',
  },
  errorBanner: {
    padding: '0.75rem 1rem',
    borderRadius: '8px',
    background: '#fef2f2',
    color: '#dc2626',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '0.5rem',
    border: '1px solid #fecaca',
  },
  retryButton: {
    padding: '0.375rem 0.75rem',
    fontSize: '0.85rem',
    fontWeight: '600',
    borderRadius: '6px',
    background: '#dc2626',
    color: '#fff',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
    border: 'none',
  },

  // Tab toggle
  tabToggle: {
    display: 'flex',
    gap: '0',
    borderRadius: '8px',
    overflow: 'hidden',
    border: '2px solid #e0e0e0',
  },
  tabButton: {
    flex: 1,
    padding: '0.75rem',
    fontSize: '0.9rem',
    fontWeight: '600',
    background: '#fff',
    color: '#6b7280',
    border: 'none',
    cursor: 'pointer',
    transition: 'background 0.2s, color 0.2s',
  },
  tabButtonActive: {
    background: '#eff6ff',
    color: '#2563eb',
  },

  // Summary card
  summaryCard: {
    border: '1px solid #e5e7eb',
    borderRadius: '12px',
    padding: '1rem',
    background: '#fafafa',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  summaryHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  periodLabel: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#374151',
  },
  noPriorBadge: {
    fontSize: '0.7rem',
    fontWeight: '500',
    color: '#6b7280',
    background: '#f3f4f6',
    padding: '0.125rem 0.5rem',
    borderRadius: '4px',
  },

  // Totals grid
  totalsGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr 1fr',
    gap: '0.5rem',
  },
  totalItem: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '0.125rem',
  },
  totalLabel: {
    fontSize: '0.75rem',
    fontWeight: '500',
    color: '#6b7280',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.03em',
  },
  totalValue: {
    fontSize: '1rem',
    fontWeight: '700',
  },

  // Category breakdown
  categorySection: {
    borderTop: '1px solid #e5e7eb',
    paddingTop: '0.75rem',
  },
  categoryTitle: {
    fontSize: '0.85rem',
    fontWeight: '600',
    color: '#374151',
    margin: '0 0 0.5rem 0',
  },
  categoryList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  categoryRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '0.375rem 0',
  },
  categoryNameCol: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    flex: 1,
    minWidth: 0,
  },
  categoryName: {
    fontSize: '0.9rem',
    fontWeight: '500',
    color: '#111827',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  changeIndicator: {
    flexShrink: 0,
  },
  categoryAmountCol: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#374151',
    flexShrink: 0,
    marginLeft: '0.5rem',
  },
  percentChange: {
    fontSize: '0.75rem',
    fontWeight: '600',
  },
  newBadge: {
    fontSize: '0.7rem',
    fontWeight: '600',
    color: '#2563eb',
    background: '#dbeafe',
    padding: '0.0625rem 0.375rem',
    borderRadius: '4px',
  },

  // Spikes section
  spikesSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  spikeCard: {
    border: '1px solid #fed7aa',
    borderRadius: '10px',
    padding: '0.75rem 1rem',
    background: '#fffbeb',
  },
  spikeHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '0.5rem',
  },
  spikeCategoryName: {
    fontSize: '0.95rem',
    fontWeight: '600',
    color: '#92400e',
  },
  spikeBadge: {
    fontSize: '0.7rem',
    fontWeight: '700',
    color: '#dc2626',
    background: '#fef2f2',
    padding: '0.125rem 0.5rem',
    borderRadius: '4px',
    textTransform: 'uppercase' as const,
  },
  spikeDetails: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  spikeRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  spikeLabel: {
    fontSize: '0.8rem',
    color: '#78350f',
  },
  spikeValue: {
    fontSize: '0.85rem',
    fontWeight: '600',
    color: '#92400e',
  },
};

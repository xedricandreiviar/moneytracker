/**
 * HomePage — Main dashboard showing daily task status, streak, notifications,
 * personalized insight, budget summaries, and quick navigation.
 * Integrates StreakBadge, DailyTaskBanner, NotificationBanner, InsightBanner, and BudgetCard components.
 * Requirements: 1.2, 7.1, 7.2, 12.1, 18.4, 18.5
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { StreakBadge } from '../components/StreakBadge';
import { DailyTaskBanner } from '../components/DailyTaskBanner';
import { NotificationBanner } from '../components/NotificationBanner';
import { CurrencyDisplay } from '../components/CurrencyDisplay';
import { useLocale } from '../contexts/LocaleContext';
import { type BudgetData } from '../components/BudgetCard';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface InsightData {
  insight_text: string;
  category_focus: string | null;
}

export default function HomePage() {
  const navigate = useNavigate();
  const { locale } = useLocale();

  const [budgets, setBudgets] = useState<BudgetData[]>([]);
  const [budgetsLoading, setBudgetsLoading] = useState(true);

  const [insight, setInsight] = useState<InsightData | null>(null);
  const [insightReady, setInsightReady] = useState(false);

  const fetchInsight = useCallback(async () => {
    try {
      const response = await axios.get<InsightData>(`${API_BASE}/api/dashboard/insight`);
      setInsight(response.data);
    } catch {
      // Hide banner if insight unavailable (error, 400, or network issue)
      setInsight(null);
    } finally {
      setInsightReady(true);
    }
  }, []);

  const fetchBudgets = useCallback(async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/budgets`);
      setBudgets(response.data.budgets || []);
    } catch {
      // Silently fail on home — user can navigate to Budgets page for full view
      setBudgets([]);
    } finally {
      setBudgetsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBudgets();
    fetchInsight();
  }, [fetchBudgets, fetchInsight]);

  // Refresh budgets and insight when page gains focus (covers returning from QuickAdd)
  useEffect(() => {
    function handleVisibilityChange() {
      if (document.visibilityState === 'visible') {
        fetchBudgets();
        fetchInsight();
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [fetchBudgets, fetchInsight]);

  return (
    <div className="page page-home" style={styles.page}>
      <h1 style={styles.heading}>Daily Money Tracker</h1>

      {/* Streak indicator */}
      <StreakBadge />

      {/* Daily task status and "no transactions" action */}
      <DailyTaskBanner />

      {/* Unread notifications banner (Req 12.1) */}
      <NotificationBanner />

      {/* Personalized insight banner (Req 18.4, 18.5) */}
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

      {/* Budget summaries (Req 7.1, 7.2) */}
      {locale && !budgetsLoading && budgets.length > 0 && (
        <section style={styles.budgetSection} aria-label="Budget summaries">
          <div style={styles.sectionHeader}>
            <h2 style={styles.sectionTitle}>Budgets</h2>
            <button
              type="button"
              onClick={() => navigate('/budgets')}
              style={styles.seeAllButton}
              aria-label="See all budgets"
            >
              See all →
            </button>
          </div>
          <div style={styles.budgetGrid}>
            {budgets.map((budget) => {
              const isOffTrack = budget.projection?.status === 'off_track';
              const remaining = budget.projection?.remaining ?? budget.limit_smallest_unit;
              const categoryLabel = budget.category_id
                ? `Category #${budget.category_id}`
                : 'Overall';

              return (
                <div
                  key={budget.id}
                  style={styles.budgetSummaryCard}
                  role="article"
                  aria-label={`${categoryLabel} budget summary`}
                >
                  <div style={styles.budgetCardHeader}>
                    <span style={styles.budgetCategoryLabel}>{categoryLabel}</span>
                    <span
                      style={{
                        ...styles.budgetStatusBadge,
                        ...(isOffTrack ? styles.statusOffTrack : styles.statusOnTrack),
                      }}
                    >
                      {isOffTrack ? 'Off Track' : 'On Track'}
                    </span>
                  </div>
                  <div style={styles.budgetMoneyLeft}>
                    <span style={styles.budgetMoneyLabel}>Left</span>
                    <span
                      style={{
                        ...styles.budgetMoneyAmount,
                        color: remaining < 0 ? '#dc2626' : '#16a34a',
                      }}
                    >
                      <CurrencyDisplay
                        amount={Math.abs(remaining)}
                        currencyCode={budget.currency_code}
                      />
                      {remaining < 0 && <span> over</span>}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Quick navigation */}
      <section style={styles.navSection} aria-label="Quick navigation">
        <div style={styles.navGrid}>
          <NavButton
            label="Quick Add"
            icon="💰"
            onClick={() => navigate('/quick-add')}
          />
          <NavButton
            label="Budgets"
            icon="📊"
            onClick={() => navigate('/budgets')}
          />
          <NavButton
            label="Insights"
            icon="📈"
            onClick={() => navigate('/insights')}
          />
          <NavButton
            label="AI Chat"
            icon="🤖"
            onClick={() => navigate('/ai-chat')}
          />
          <NavButton
            label="Coaching"
            icon="💡"
            onClick={() => navigate('/ai-coaching')}
          />
          <NavButton
            label="Settings"
            icon="⚙️"
            onClick={() => navigate('/settings')}
          />
        </div>
      </section>
    </div>
  );
}

interface NavButtonProps {
  label: string;
  icon: string;
  onClick: () => void;
}

function NavButton({ label, icon, onClick }: NavButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={styles.navButton}
      aria-label={`Navigate to ${label}`}
    >
      <span style={styles.navIcon}>{icon}</span>
      <span style={styles.navLabel}>{label}</span>
    </button>
  );
}

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
    marginBottom: '0.25rem',
  },

  // Personalized insight banner (Req 18.4, 18.5)
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

  // Budget summaries
  budgetSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  sectionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sectionTitle: {
    fontSize: '1rem',
    fontWeight: '600',
    margin: 0,
    color: '#111827',
  },
  seeAllButton: {
    fontSize: '0.8rem',
    fontWeight: '500',
    color: '#2563eb',
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    padding: '0.25rem 0',
  },
  budgetGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  budgetSummaryCard: {
    border: '1px solid #e5e7eb',
    borderRadius: '10px',
    padding: '0.75rem 1rem',
    background: '#fff',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.375rem',
  },
  budgetCardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  budgetCategoryLabel: {
    fontSize: '0.85rem',
    fontWeight: '600',
    color: '#374151',
  },
  budgetStatusBadge: {
    fontSize: '0.7rem',
    fontWeight: '600',
    padding: '0.125rem 0.5rem',
    borderRadius: '4px',
  },
  statusOnTrack: {
    background: '#f0fdf4',
    color: '#16a34a',
    border: '1px solid #bbf7d0',
  },
  statusOffTrack: {
    background: '#fef2f2',
    color: '#dc2626',
    border: '1px solid #fecaca',
  },
  budgetMoneyLeft: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'baseline',
  },
  budgetMoneyLabel: {
    fontSize: '0.75rem',
    color: '#6b7280',
  },
  budgetMoneyAmount: {
    fontSize: '1.05rem',
    fontWeight: '700',
  },

  // Quick navigation
  navSection: {
    paddingTop: '0.5rem',
  },
  navGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: '0.75rem',
  },
  navButton: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.25rem',
    padding: '0.875rem 0.5rem',
    borderRadius: '12px',
    border: '1px solid #e5e7eb',
    background: '#fff',
    cursor: 'pointer',
    transition: 'background 0.15s',
  },
  navIcon: {
    fontSize: '1.5rem',
  },
  navLabel: {
    fontSize: '0.75rem',
    fontWeight: '500',
    color: '#374151',
  },
};

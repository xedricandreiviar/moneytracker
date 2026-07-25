/**
 * BudgetCard - Displays budget status for a single budget.
 * Shows money left indicator, on/off track status, and projected overage amount.
 * Uses CurrencyDisplay for locale-aware formatting.
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
 */
import { CurrencyDisplay } from './CurrencyDisplay';

export interface BudgetProjection {
  remaining: number;
  projected_spend: number;
  status: string;
  overage: number;
}

export interface BudgetPeriod {
  period_start: string;
  period_end: string;
  spent_smallest_unit: number;
  status: string;
}

export interface BudgetData {
  id: number;
  user_id: number;
  category_id: number | null;
  period_type: string;
  limit_smallest_unit: number;
  currency_code: string;
  is_active: boolean;
  created_at_utc: string;
  current_period: BudgetPeriod | null;
  projection: BudgetProjection | null;
}

interface BudgetCardProps {
  budget: BudgetData;
  onDelete?: (budgetId: number) => void;
}

export function BudgetCard({ budget, onDelete }: BudgetCardProps) {
  const { projection, current_period, currency_code, limit_smallest_unit } = budget;

  const isOffTrack = projection?.status === 'off_track';
  const remaining = projection?.remaining ?? limit_smallest_unit;
  const overage = projection?.overage ?? 0;

  // Calculate progress percentage
  const spent = current_period?.spent_smallest_unit ?? 0;
  const progressPct = limit_smallest_unit > 0
    ? Math.min((spent / limit_smallest_unit) * 100, 100)
    : 0;

  const categoryLabel = budget.category_id ? `Category #${budget.category_id}` : 'Overall';
  const periodLabel = budget.period_type === 'weekly' ? 'Weekly' : 'Monthly';

  return (
    <div style={styles.card} role="article" aria-label={`${categoryLabel} ${periodLabel} budget`}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.categoryLabel}>{categoryLabel}</span>
          <span style={styles.periodBadge}>{periodLabel}</span>
        </div>
        {onDelete && (
          <button
            type="button"
            onClick={() => onDelete(budget.id)}
            style={styles.deleteButton}
            aria-label={`Delete ${categoryLabel} budget`}
          >
            ×
          </button>
        )}
      </div>

      {/* Status indicator */}
      <div style={{
        ...styles.statusBadge,
        ...(isOffTrack ? styles.statusOffTrack : styles.statusOnTrack),
      }}>
        {isOffTrack ? '⚠ Off Track' : '✓ On Track'}
      </div>

      {/* Money left */}
      <div style={styles.moneyLeft}>
        <span style={styles.moneyLeftLabel}>Remaining</span>
        <span style={{
          ...styles.moneyLeftAmount,
          color: remaining < 0 ? '#dc2626' : '#16a34a',
        }}>
          <CurrencyDisplay amount={Math.abs(remaining)} currencyCode={currency_code} />
          {remaining < 0 && <span> over</span>}
        </span>
      </div>

      {/* Progress bar */}
      <div style={styles.progressContainer}>
        <div
          style={{
            ...styles.progressBar,
            width: `${progressPct}%`,
            background: isOffTrack ? '#dc2626' : progressPct >= 80 ? '#f59e0b' : '#16a34a',
          }}
          role="progressbar"
          aria-valuenow={progressPct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Budget used ${Math.round(progressPct)}%`}
        />
      </div>

      {/* Spent / Limit */}
      <div style={styles.spentRow}>
        <span style={styles.spentLabel}>
          <CurrencyDisplay amount={spent} currencyCode={currency_code} /> spent
        </span>
        <span style={styles.limitLabel}>
          of <CurrencyDisplay amount={limit_smallest_unit} currencyCode={currency_code} />
        </span>
      </div>

      {/* Projected overage */}
      {isOffTrack && overage > 0 && (
        <div style={styles.overageRow} role="alert">
          <span style={styles.overageLabel}>Projected overage:</span>
          <span style={styles.overageAmount}>
            <CurrencyDisplay amount={overage} currencyCode={currency_code} />
          </span>
        </div>
      )}

      {/* Period dates */}
      {current_period && (
        <div style={styles.periodDates}>
          {current_period.period_start} → {current_period.period_end}
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    border: '1px solid #e5e7eb',
    borderRadius: '12px',
    padding: '1rem',
    background: '#fff',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  categoryLabel: {
    fontSize: '1rem',
    fontWeight: '600',
    color: '#111827',
  },
  periodBadge: {
    fontSize: '0.7rem',
    fontWeight: '500',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.05em',
    color: '#6b7280',
    background: '#f3f4f6',
    padding: '0.125rem 0.5rem',
    borderRadius: '4px',
  },
  deleteButton: {
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    border: 'none',
    background: '#f3f4f6',
    color: '#6b7280',
    fontSize: '1.2rem',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    lineHeight: 1,
  },
  statusBadge: {
    fontSize: '0.85rem',
    fontWeight: '600',
    padding: '0.375rem 0.75rem',
    borderRadius: '6px',
    textAlign: 'center' as const,
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
  moneyLeft: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'baseline',
  },
  moneyLeftLabel: {
    fontSize: '0.85rem',
    color: '#6b7280',
  },
  moneyLeftAmount: {
    fontSize: '1.25rem',
    fontWeight: '700',
  },
  progressContainer: {
    height: '6px',
    borderRadius: '3px',
    background: '#f3f4f6',
    overflow: 'hidden',
  },
  progressBar: {
    height: '100%',
    borderRadius: '3px',
    transition: 'width 0.3s ease',
  },
  spentRow: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: '0.8rem',
    color: '#6b7280',
  },
  spentLabel: {
    fontWeight: '500',
  },
  limitLabel: {
    fontWeight: '400',
  },
  overageRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    background: '#fef2f2',
    padding: '0.5rem 0.75rem',
    borderRadius: '6px',
    border: '1px solid #fecaca',
  },
  overageLabel: {
    fontSize: '0.8rem',
    color: '#dc2626',
    fontWeight: '500',
  },
  overageAmount: {
    fontSize: '0.9rem',
    fontWeight: '700',
    color: '#dc2626',
  },
  periodDates: {
    fontSize: '0.75rem',
    color: '#9ca3af',
    textAlign: 'center' as const,
  },
};

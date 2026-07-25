/**
 * BudgetsPage - Lists active budgets and provides a form to create new ones.
 * Displays BudgetCards with money left, on/off track status, and projected overage.
 * Refreshes budget data within 2 seconds after transaction save (via polling on focus).
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.8, 8.9
 */
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useLocale } from '../contexts/LocaleContext';
import { AmountInput } from '../components/AmountInput';
import { BudgetCard, type BudgetData } from '../components/BudgetCard';
import { parseAmountInput } from '../utils/locale';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

type PeriodType = 'weekly' | 'monthly';

interface FieldError {
  field: string;
  message: string;
}

export default function BudgetsPage() {
  const { locale } = useLocale();

  // Budget list state
  const [budgets, setBudgets] = useState<BudgetData[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  // Create budget form state
  const [showForm, setShowForm] = useState(false);
  const [limitValue, setLimitValue] = useState('');
  const [periodType, setPeriodType] = useState<PeriodType>('monthly');
  const [categoryId, setCategoryId] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldError[]>([]);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [showSuccess, setShowSuccess] = useState(false);

  // Fetch budgets on mount and on window focus (real-time refresh within 2s)
  useEffect(() => {
    fetchBudgets();
  }, []);

  useEffect(() => {
    function handleFocus() {
      fetchBudgets();
    }

    // Refresh on visibility change (covers tab switch and app resume)
    function handleVisibilityChange() {
      if (document.visibilityState === 'visible') {
        fetchBudgets();
      }
    }

    window.addEventListener('focus', handleFocus);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('focus', handleFocus);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  // Poll every 2 seconds for real-time updates after transactions
  useEffect(() => {
    const interval = setInterval(() => {
      fetchBudgets();
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  const fetchBudgets = useCallback(async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/budgets`);
      setBudgets(response.data.budgets || []);
      setListError(null);
    } catch {
      setListError('Failed to load budgets. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  function resetForm() {
    setLimitValue('');
    setPeriodType('monthly');
    setCategoryId('');
    setFieldErrors([]);
    setGeneralError(null);
  }

  function getFieldError(fieldName: string): string | undefined {
    return fieldErrors.find((e) => e.field === fieldName)?.message;
  }

  async function handleCreate() {
    if (!locale) return;

    setFieldErrors([]);
    setGeneralError(null);

    // Client-side validation
    const parsedLimit = parseAmountInput(limitValue, locale);
    if (parsedLimit === null || parsedLimit <= 0) {
      setFieldErrors([{
        field: 'limit_smallest_unit',
        message: 'Enter a valid positive spending limit',
      }]);
      return;
    }

    setIsSubmitting(true);

    try {
      const payload: Record<string, unknown> = {
        period_type: periodType,
        limit_smallest_unit: parsedLimit,
        currency_code: locale.currency_code,
      };

      const parsedCategoryId = categoryId.trim() ? parseInt(categoryId, 10) : null;
      if (parsedCategoryId !== null && !isNaN(parsedCategoryId)) {
        payload.category_id = parsedCategoryId;
      }

      await axios.post(`${API_BASE}/api/budgets`, payload);

      // Show success and reset form
      setShowSuccess(true);
      resetForm();
      setShowForm(false);

      setTimeout(() => setShowSuccess(false), 2000);

      // Refresh the budget list
      fetchBudgets();
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 422) {
          const detail = error.response.data?.detail;
          if (Array.isArray(detail)) {
            setFieldErrors(detail as FieldError[]);
          } else {
            setGeneralError('Validation failed. Please check your input.');
          }
        } else if (error.response?.status === 409) {
          const detail = error.response.data?.detail;
          setGeneralError(
            typeof detail === 'string'
              ? detail
              : 'An active budget already exists for this category and period.'
          );
        } else {
          setGeneralError('Something went wrong. Please try again.');
        }
      } else {
        setGeneralError('Network error. Please check your connection.');
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete(budgetId: number) {
    try {
      await axios.delete(`${API_BASE}/api/budgets/${budgetId}`);
      fetchBudgets();
    } catch {
      setListError('Failed to delete budget. Please try again.');
    }
  }

  if (!locale) {
    return (
      <div className="page page-budgets">
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div className="page page-budgets" style={styles.page}>
      <div style={styles.headerRow}>
        <h1 style={styles.heading}>Budgets</h1>
        {!showForm && (
          <button
            type="button"
            onClick={() => setShowForm(true)}
            style={styles.addButton}
            aria-label="Create new budget"
          >
            + New
          </button>
        )}
      </div>

      {/* Success message */}
      {showSuccess && (
        <div style={styles.successBanner} role="status" aria-live="polite">
          ✓ Budget created
        </div>
      )}

      {/* Create budget form */}
      {showForm && (
        <div style={styles.formCard}>
          <h2 style={styles.formTitle}>Create Budget</h2>

          {generalError && (
            <div style={styles.errorBanner} role="alert">
              {generalError}
            </div>
          )}

          {/* Limit amount */}
          <div style={styles.fieldGroup}>
            <label style={styles.label}>Spending Limit</label>
            <AmountInput
              locale={locale}
              value={limitValue}
              onChange={setLimitValue}
              error={getFieldError('limit_smallest_unit')}
              placeholder="Budget limit"
              disabled={isSubmitting}
            />
          </div>

          {/* Period type */}
          <div style={styles.fieldGroup}>
            <label style={styles.label}>Period</label>
            <div style={styles.periodToggle} role="radiogroup" aria-label="Budget period type">
              <button
                type="button"
                onClick={() => setPeriodType('weekly')}
                style={{
                  ...styles.periodButton,
                  ...(periodType === 'weekly' ? styles.periodButtonActive : {}),
                }}
                aria-pressed={periodType === 'weekly'}
                disabled={isSubmitting}
              >
                Weekly
              </button>
              <button
                type="button"
                onClick={() => setPeriodType('monthly')}
                style={{
                  ...styles.periodButton,
                  ...(periodType === 'monthly' ? styles.periodButtonActive : {}),
                }}
                aria-pressed={periodType === 'monthly'}
                disabled={isSubmitting}
              >
                Monthly
              </button>
            </div>
          </div>

          {/* Category (optional) */}
          <div style={styles.fieldGroup}>
            <label htmlFor="budget-category" style={styles.label}>
              Category ID
              <span style={styles.optionalBadge}>Optional</span>
            </label>
            <input
              id="budget-category"
              type="text"
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              placeholder="Leave empty for overall budget"
              style={{
                ...styles.input,
                ...(getFieldError('category_id') ? styles.inputError : {}),
              }}
              disabled={isSubmitting}
              aria-invalid={!!getFieldError('category_id')}
            />
            {getFieldError('category_id') && (
              <p style={styles.fieldErrorText} role="alert">
                {getFieldError('category_id')}
              </p>
            )}
          </div>

          {/* Form actions */}
          <div style={styles.formActions}>
            <button
              type="button"
              onClick={() => {
                resetForm();
                setShowForm(false);
              }}
              style={styles.cancelButton}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleCreate}
              disabled={isSubmitting || !limitValue}
              style={{
                ...styles.createButton,
                ...(isSubmitting || !limitValue ? styles.createButtonDisabled : {}),
              }}
            >
              {isSubmitting ? 'Creating...' : 'Create Budget'}
            </button>
          </div>
        </div>
      )}

      {/* List error */}
      {listError && (
        <div style={styles.errorBanner} role="alert">
          <span>{listError}</span>
          <button
            type="button"
            onClick={fetchBudgets}
            style={styles.retryButton}
            aria-label="Retry loading budgets"
          >
            Retry
          </button>
        </div>
      )}

      {/* Budget list */}
      {loading ? (
        <p style={styles.emptyState}>Loading budgets...</p>
      ) : budgets.length === 0 ? (
        <div style={styles.emptyState}>
          <p style={styles.emptyTitle}>No active budgets</p>
          <p style={styles.emptySubtitle}>Create a budget to start tracking your spending limits.</p>
        </div>
      ) : (
        <div style={styles.budgetList}>
          {budgets.map((budget) => (
            <BudgetCard
              key={budget.id}
              budget={budget}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
    paddingBottom: '2rem',
  },
  headerRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  heading: {
    fontSize: '1.5rem',
    fontWeight: '700',
    margin: 0,
  },
  addButton: {
    padding: '0.5rem 1rem',
    fontSize: '0.85rem',
    fontWeight: '600',
    borderRadius: '8px',
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    cursor: 'pointer',
  },
  successBanner: {
    padding: '0.75rem 1rem',
    borderRadius: '8px',
    background: '#f0fdf4',
    color: '#16a34a',
    fontWeight: '600',
    textAlign: 'center' as const,
    border: '1px solid #bbf7d0',
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
  formCard: {
    border: '1px solid #e5e7eb',
    borderRadius: '12px',
    padding: '1rem',
    background: '#fafafa',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  formTitle: {
    fontSize: '1.1rem',
    fontWeight: '600',
    margin: 0,
    color: '#111827',
  },
  fieldGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  label: {
    fontSize: '0.85rem',
    fontWeight: '600',
    color: '#374151',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  optionalBadge: {
    fontSize: '0.7rem',
    fontWeight: '400',
    color: '#9ca3af',
    fontStyle: 'italic',
  },
  input: {
    width: '100%',
    padding: '0.625rem 0.75rem',
    fontSize: '0.95rem',
    borderRadius: '8px',
    border: '2px solid #e0e0e0',
    background: '#fff',
    outline: 'none',
    transition: 'border-color 0.2s',
    boxSizing: 'border-box' as const,
  },
  inputError: {
    borderColor: '#dc2626',
    background: '#fef2f2',
  },
  fieldErrorText: {
    fontSize: '0.8rem',
    color: '#dc2626',
    marginTop: '0.125rem',
  },
  periodToggle: {
    display: 'flex',
    gap: '0',
    borderRadius: '8px',
    overflow: 'hidden',
    border: '2px solid #e0e0e0',
  },
  periodButton: {
    flex: 1,
    padding: '0.625rem',
    fontSize: '0.9rem',
    fontWeight: '600',
    background: '#fff',
    color: '#6b7280',
    border: 'none',
    cursor: 'pointer',
    transition: 'background 0.2s, color 0.2s',
  },
  periodButtonActive: {
    background: '#eff6ff',
    color: '#2563eb',
  },
  formActions: {
    display: 'flex',
    gap: '0.75rem',
    marginTop: '0.25rem',
  },
  cancelButton: {
    flex: 1,
    padding: '0.75rem',
    fontSize: '0.9rem',
    fontWeight: '600',
    borderRadius: '8px',
    border: '2px solid #e0e0e0',
    background: '#fff',
    color: '#6b7280',
    cursor: 'pointer',
  },
  createButton: {
    flex: 1,
    padding: '0.75rem',
    fontSize: '0.9rem',
    fontWeight: '600',
    borderRadius: '8px',
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    cursor: 'pointer',
    transition: 'background 0.2s',
  },
  createButtonDisabled: {
    background: '#93c5fd',
    cursor: 'not-allowed',
  },
  budgetList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  emptyState: {
    textAlign: 'center' as const,
    padding: '2rem 1rem',
    color: '#6b7280',
  },
  emptyTitle: {
    fontSize: '1rem',
    fontWeight: '600',
    color: '#374151',
    margin: '0 0 0.25rem 0',
  },
  emptySubtitle: {
    fontSize: '0.85rem',
    color: '#9ca3af',
    margin: 0,
  },
};

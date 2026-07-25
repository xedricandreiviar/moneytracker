/**
 * AICoachingPage - Displays AI coaching suggestions and budget recommendations.
 *
 * Features:
 * - Coaching Suggestions: Lists pending proactive suggestions with accept/dismiss actions (single tap)
 * - Budget Recommendation: "Get AI Recommendation" button with loading state (up to 15s)
 * - Shows reasoning with referenced data points
 * - Shows "more data needed" with days remaining when < 14 days history
 * - Error states: timeout (retry), rate limit (wait)
 *
 * Requirements: 9.2, 9.3, 10.2, 10.3
 */
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useLocale } from '../contexts/LocaleContext';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// --- Types ---

interface CoachingSuggestion {
  id: number;
  budget_id: number;
  suggestion_text: string;
  deviation_percentage: number;
  status: string;
  period_start: string;
  period_end: string;
  created_at_utc: string;
}

interface RecommendationResult {
  success: boolean;
  message: string;
  error_type: string | null;
  data: Record<string, unknown> | null;
}

export default function AICoachingPage() {
  const { locale } = useLocale();

  // Coaching suggestions state
  const [suggestions, setSuggestions] = useState<CoachingSuggestion[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(true);
  const [suggestionsError, setSuggestionsError] = useState<string | null>(null);
  const [dismissingIds, setDismissingIds] = useState<Set<number>>(new Set());

  // Budget recommendation state
  const [recommendationLoading, setRecommendationLoading] = useState(false);
  const [recommendationResult, setRecommendationResult] = useState<RecommendationResult | null>(null);
  const [recommendationError, setRecommendationError] = useState<string | null>(null);

  // Fetch coaching suggestions on mount
  useEffect(() => {
    fetchSuggestions();
  }, []);

  const fetchSuggestions = useCallback(async () => {
    setSuggestionsLoading(true);
    setSuggestionsError(null);
    try {
      const response = await axios.get(`${API_BASE}/api/ai/coaching`);
      setSuggestions(response.data.suggestions || []);
    } catch {
      setSuggestionsError('Failed to load coaching suggestions.');
    } finally {
      setSuggestionsLoading(false);
    }
  }, []);

  async function handleDismiss(suggestionId: number) {
    setDismissingIds((prev) => new Set(prev).add(suggestionId));
    try {
      await axios.post(`${API_BASE}/api/ai/coaching/${suggestionId}/dismiss`);
      // Remove from local state after successful dismiss
      setSuggestions((prev) => prev.filter((s) => s.id !== suggestionId));
    } catch {
      setSuggestionsError('Failed to dismiss suggestion. Please try again.');
    } finally {
      setDismissingIds((prev) => {
        const next = new Set(prev);
        next.delete(suggestionId);
        return next;
      });
    }
  }

  function handleAccept(suggestionId: number) {
    // Accept removes the suggestion from view (single tap action)
    // In a full implementation, this would apply the suggested budget adjustment
    setSuggestions((prev) => prev.filter((s) => s.id !== suggestionId));
  }

  async function handleGetRecommendation() {
    setRecommendationLoading(true);
    setRecommendationResult(null);
    setRecommendationError(null);

    try {
      const response = await axios.post(`${API_BASE}/api/ai/recommend-budget`, {}, {
        timeout: 15000, // 15s timeout as per requirement 9.5
      });
      setRecommendationResult(response.data);
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 503) {
          setRecommendationError('timeout');
        } else if (error.response?.status === 429) {
          const retryAfter = error.response.data?.retry_after;
          setRecommendationError(
            retryAfter
              ? `rate_limit:${retryAfter}`
              : 'rate_limit'
          );
        } else if (error.response?.data) {
          // The API returned a 200 with success=false (insufficient_data etc.)
          setRecommendationResult(error.response.data);
        } else {
          setRecommendationError('timeout');
        }
      } else if (error instanceof Error && error.message?.includes('timeout')) {
        setRecommendationError('timeout');
      } else {
        setRecommendationError('timeout');
      }
    } finally {
      setRecommendationLoading(false);
    }
  }

  if (!locale) {
    return (
      <div className="page page-ai-coaching">
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div className="page page-ai-coaching" style={styles.page}>
      <h1 style={styles.heading}>AI Budget Coach</h1>

      {/* --- Coaching Suggestions Section --- */}
      <section style={styles.section} aria-labelledby="coaching-heading">
        <h2 id="coaching-heading" style={styles.sectionHeading}>
          Coaching Suggestions
        </h2>
        <p style={styles.sectionDesc}>
          Proactive tips based on your spending patterns.
        </p>

        {suggestionsLoading && (
          <p style={styles.loadingText}>Loading suggestions...</p>
        )}

        {suggestionsError && (
          <div style={styles.errorBanner} role="alert">
            <span>{suggestionsError}</span>
            <button
              type="button"
              onClick={fetchSuggestions}
              style={styles.retryButtonSmall}
              aria-label="Retry loading suggestions"
            >
              Retry
            </button>
          </div>
        )}

        {!suggestionsLoading && !suggestionsError && suggestions.length === 0 && (
          <div style={styles.emptyState}>
            <p style={styles.emptyTitle}>No suggestions right now</p>
            <p style={styles.emptySubtitle}>
              Coaching suggestions appear when your spending deviates from budget targets.
            </p>
          </div>
        )}

        {suggestions.length > 0 && (
          <div style={styles.suggestionList}>
            {suggestions.map((suggestion) => (
              <div
                key={suggestion.id}
                style={styles.suggestionCard}
                role="article"
                aria-label={`Coaching suggestion: ${suggestion.suggestion_text}`}
              >
                {/* Deviation badge */}
                <div style={styles.deviationBadge}>
                  <span style={styles.deviationText}>
                    {suggestion.deviation_percentage > 0 ? '+' : ''}
                    {suggestion.deviation_percentage.toFixed(1)}% deviation
                  </span>
                </div>

                {/* Suggestion text with reasoning */}
                <p style={styles.suggestionText}>{suggestion.suggestion_text}</p>

                {/* Period info */}
                <p style={styles.periodInfo}>
                  Period: {suggestion.period_start} → {suggestion.period_end}
                </p>

                {/* Action buttons */}
                <div style={styles.actionRow}>
                  <button
                    type="button"
                    onClick={() => handleAccept(suggestion.id)}
                    style={styles.acceptButton}
                    aria-label="Accept suggestion"
                    disabled={dismissingIds.has(suggestion.id)}
                  >
                    ✓ Accept
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDismiss(suggestion.id)}
                    style={styles.dismissButton}
                    aria-label="Dismiss suggestion"
                    disabled={dismissingIds.has(suggestion.id)}
                  >
                    {dismissingIds.has(suggestion.id) ? 'Dismissing...' : '✕ Dismiss'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* --- Budget Recommendation Section --- */}
      <section style={styles.section} aria-labelledby="recommendation-heading">
        <h2 id="recommendation-heading" style={styles.sectionHeading}>
          Budget Recommendation
        </h2>
        <p style={styles.sectionDesc}>
          Get AI-powered budget suggestions based on your spending history.
        </p>

        {/* Request button */}
        <button
          type="button"
          onClick={handleGetRecommendation}
          disabled={recommendationLoading}
          style={{
            ...styles.recommendButton,
            ...(recommendationLoading ? styles.recommendButtonDisabled : {}),
          }}
          aria-label="Get AI budget recommendation"
        >
          {recommendationLoading ? 'Analyzing your spending...' : 'Get AI Recommendation'}
        </button>

        {/* Loading state with progress indicator */}
        {recommendationLoading && (
          <div style={styles.loadingCard} role="status" aria-live="polite">
            <div style={styles.loadingSpinner} />
            <p style={styles.loadingLabel}>
              Analyzing your transaction history...
            </p>
            <p style={styles.loadingHint}>This may take up to 15 seconds.</p>
          </div>
        )}

        {/* Recommendation result */}
        {recommendationResult && !recommendationLoading && (
          <RecommendationDisplay result={recommendationResult} />
        )}

        {/* Error states */}
        {recommendationError && !recommendationLoading && (
          <RecommendationError
            errorType={recommendationError}
            onRetry={handleGetRecommendation}
          />
        )}
      </section>
    </div>
  );
}

// --- Sub-components ---

function RecommendationDisplay({ result }: { result: RecommendationResult }) {
  // Successful recommendation with reasoning
  if (result.success) {
    return (
      <div style={styles.resultCard} role="region" aria-label="Budget recommendation">
        <div style={styles.resultHeader}>
          <span style={styles.resultIcon}>💡</span>
          <span style={styles.resultTitle}>Recommendation</span>
        </div>
        <div style={styles.resultBody}>
          <p style={styles.resultMessage}>{result.message}</p>
          {result.data && (
            <RecommendationData data={result.data} />
          )}
        </div>
      </div>
    );
  }

  // Insufficient data — show days remaining
  if (result.error_type === 'insufficient_data') {
    const daysOfHistory = (result.data?.days_of_history as number) ?? 0;
    const daysNeeded = (result.data?.days_needed as number) ?? 14;
    const daysRemaining = Math.max(0, daysNeeded - daysOfHistory);

    return (
      <div style={styles.insufficientCard} role="status" aria-live="polite">
        <div style={styles.insufficientHeader}>
          <span style={styles.insufficientIcon}>📊</span>
          <span style={styles.insufficientTitle}>More Data Needed</span>
        </div>
        <p style={styles.insufficientMessage}>{result.message}</p>
        <div style={styles.daysCounter}>
          <span style={styles.daysNumber}>{daysRemaining}</span>
          <span style={styles.daysLabel}>
            more day{daysRemaining !== 1 ? 's' : ''} of logging needed
          </span>
        </div>
        <p style={styles.insufficientHint}>
          You have {daysOfHistory} day{daysOfHistory !== 1 ? 's' : ''} of history.
          At least {daysNeeded} days are required for reliable recommendations.
        </p>
      </div>
    );
  }

  // Generic error in result
  return (
    <div style={styles.errorBanner} role="alert">
      <span>{result.message || 'Something went wrong.'}</span>
    </div>
  );
}

function RecommendationData({ data }: { data: Record<string, unknown> }) {
  // Display any referenced data points from the recommendation
  const entries = Object.entries(data).filter(
    ([key]) => key !== 'days_of_history' && key !== 'days_needed'
  );

  if (entries.length === 0) return null;

  return (
    <div style={styles.dataPoints}>
      <p style={styles.dataPointsLabel}>Referenced data:</p>
      <ul style={styles.dataPointsList}>
        {entries.map(([key, value]) => (
          <li key={key} style={styles.dataPointItem}>
            <span style={styles.dataPointKey}>
              {key.replace(/_/g, ' ')}:
            </span>{' '}
            <span style={styles.dataPointValue}>
              {typeof value === 'object' ? JSON.stringify(value) : String(value)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RecommendationError({
  errorType,
  onRetry,
}: {
  errorType: string;
  onRetry: () => void;
}) {
  // Timeout error
  if (errorType === 'timeout') {
    return (
      <div style={styles.errorCard} role="alert">
        <div style={styles.errorHeader}>
          <span style={styles.errorIcon}>⏱</span>
          <span style={styles.errorTitle}>Assistant Unavailable</span>
        </div>
        <p style={styles.errorMessage}>
          The AI assistant is temporarily unavailable. Please try again later.
        </p>
        <button
          type="button"
          onClick={onRetry}
          style={styles.retryButton}
          aria-label="Retry recommendation"
        >
          Try Again
        </button>
      </div>
    );
  }

  // Rate limit error
  if (errorType.startsWith('rate_limit')) {
    const retryAfter = errorType.includes(':')
      ? parseInt(errorType.split(':')[1], 10)
      : null;

    return (
      <div style={styles.errorCard} role="alert">
        <div style={styles.errorHeader}>
          <span style={styles.errorIcon}>🚦</span>
          <span style={styles.errorTitle}>Too Many Requests</span>
        </div>
        <p style={styles.errorMessage}>
          You've made too many requests.
          {retryAfter
            ? ` Please wait ${retryAfter} second${retryAfter !== 1 ? 's' : ''} before trying again.`
            : ' Please wait a moment before trying again.'}
        </p>
      </div>
    );
  }

  // Generic error
  return (
    <div style={styles.errorCard} role="alert">
      <p style={styles.errorMessage}>Something went wrong. Please try again.</p>
      <button
        type="button"
        onClick={onRetry}
        style={styles.retryButton}
        aria-label="Retry recommendation"
      >
        Try Again
      </button>
    </div>
  );
}

// --- Styles ---

const styles: Record<string, React.CSSProperties> = {
  page: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1.5rem',
    paddingBottom: '2rem',
  },
  heading: {
    fontSize: '1.5rem',
    fontWeight: '700',
    margin: 0,
  },
  section: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  sectionHeading: {
    fontSize: '1.1rem',
    fontWeight: '600',
    margin: 0,
    color: '#111827',
  },
  sectionDesc: {
    fontSize: '0.85rem',
    color: '#6b7280',
    margin: 0,
  },
  loadingText: {
    fontSize: '0.9rem',
    color: '#6b7280',
    textAlign: 'center' as const,
    padding: '1rem',
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
    fontSize: '0.85rem',
  },
  retryButtonSmall: {
    padding: '0.25rem 0.625rem',
    fontSize: '0.8rem',
    fontWeight: '600',
    borderRadius: '6px',
    background: '#dc2626',
    color: '#fff',
    cursor: 'pointer',
    border: 'none',
    whiteSpace: 'nowrap' as const,
  },
  emptyState: {
    textAlign: 'center' as const,
    padding: '1.5rem 1rem',
    background: '#f9fafb',
    borderRadius: '12px',
    border: '1px solid #e5e7eb',
  },
  emptyTitle: {
    fontSize: '0.95rem',
    fontWeight: '600',
    color: '#374151',
    margin: '0 0 0.25rem 0',
  },
  emptySubtitle: {
    fontSize: '0.8rem',
    color: '#9ca3af',
    margin: 0,
  },
  suggestionList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  suggestionCard: {
    border: '1px solid #e5e7eb',
    borderRadius: '12px',
    padding: '1rem',
    background: '#fff',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  deviationBadge: {
    alignSelf: 'flex-start',
    padding: '0.25rem 0.625rem',
    borderRadius: '6px',
    background: '#fef3c7',
    border: '1px solid #fde68a',
  },
  deviationText: {
    fontSize: '0.75rem',
    fontWeight: '600',
    color: '#d97706',
  },
  suggestionText: {
    fontSize: '0.9rem',
    color: '#1f2937',
    lineHeight: '1.5',
    margin: 0,
  },
  periodInfo: {
    fontSize: '0.75rem',
    color: '#9ca3af',
    margin: 0,
  },
  actionRow: {
    display: 'flex',
    gap: '0.5rem',
    marginTop: '0.25rem',
  },
  acceptButton: {
    flex: 1,
    padding: '0.625rem',
    fontSize: '0.85rem',
    fontWeight: '600',
    borderRadius: '8px',
    border: 'none',
    background: '#16a34a',
    color: '#fff',
    cursor: 'pointer',
  },
  dismissButton: {
    flex: 1,
    padding: '0.625rem',
    fontSize: '0.85rem',
    fontWeight: '600',
    borderRadius: '8px',
    border: '2px solid #e5e7eb',
    background: '#fff',
    color: '#6b7280',
    cursor: 'pointer',
  },
  recommendButton: {
    padding: '0.875rem 1.5rem',
    fontSize: '0.95rem',
    fontWeight: '600',
    borderRadius: '10px',
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    cursor: 'pointer',
    transition: 'background 0.2s',
  },
  recommendButtonDisabled: {
    background: '#93c5fd',
    cursor: 'not-allowed',
  },
  loadingCard: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '1.5rem',
    background: '#eff6ff',
    borderRadius: '12px',
    border: '1px solid #bfdbfe',
  },
  loadingSpinner: {
    width: '32px',
    height: '32px',
    border: '3px solid #bfdbfe',
    borderTopColor: '#2563eb',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  loadingLabel: {
    fontSize: '0.9rem',
    fontWeight: '500',
    color: '#1e40af',
    margin: 0,
    textAlign: 'center' as const,
  },
  loadingHint: {
    fontSize: '0.8rem',
    color: '#6b7280',
    margin: 0,
  },
  resultCard: {
    border: '1px solid #bbf7d0',
    borderRadius: '12px',
    background: '#f0fdf4',
    padding: '1rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  resultHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  resultIcon: {
    fontSize: '1.25rem',
  },
  resultTitle: {
    fontSize: '1rem',
    fontWeight: '600',
    color: '#16a34a',
  },
  resultBody: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  resultMessage: {
    fontSize: '0.9rem',
    color: '#1f2937',
    lineHeight: '1.6',
    margin: 0,
    whiteSpace: 'pre-wrap' as const,
  },
  dataPoints: {
    marginTop: '0.5rem',
    padding: '0.75rem',
    background: '#ecfdf5',
    borderRadius: '8px',
    border: '1px solid #a7f3d0',
  },
  dataPointsLabel: {
    fontSize: '0.8rem',
    fontWeight: '600',
    color: '#065f46',
    margin: '0 0 0.5rem 0',
  },
  dataPointsList: {
    listStyle: 'none',
    margin: 0,
    padding: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: '0.375rem',
  },
  dataPointItem: {
    fontSize: '0.8rem',
    color: '#374151',
  },
  dataPointKey: {
    fontWeight: '600',
    textTransform: 'capitalize' as const,
  },
  dataPointValue: {
    fontWeight: '400',
  },
  insufficientCard: {
    border: '1px solid #e5e7eb',
    borderRadius: '12px',
    background: '#f9fafb',
    padding: '1.25rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
    textAlign: 'center' as const,
  },
  insufficientHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.5rem',
  },
  insufficientIcon: {
    fontSize: '1.5rem',
  },
  insufficientTitle: {
    fontSize: '1rem',
    fontWeight: '600',
    color: '#374151',
  },
  insufficientMessage: {
    fontSize: '0.85rem',
    color: '#6b7280',
    margin: 0,
    lineHeight: '1.5',
  },
  daysCounter: {
    display: 'flex',
    alignItems: 'baseline',
    justifyContent: 'center',
    gap: '0.5rem',
    padding: '0.75rem',
    background: '#fff',
    borderRadius: '8px',
    border: '1px solid #e5e7eb',
  },
  daysNumber: {
    fontSize: '2rem',
    fontWeight: '700',
    color: '#2563eb',
  },
  daysLabel: {
    fontSize: '0.85rem',
    color: '#6b7280',
  },
  insufficientHint: {
    fontSize: '0.8rem',
    color: '#9ca3af',
    margin: 0,
  },
  errorCard: {
    border: '1px solid #fecaca',
    borderRadius: '12px',
    background: '#fef2f2',
    padding: '1.25rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
    alignItems: 'center',
  },
  errorHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  errorIcon: {
    fontSize: '1.25rem',
  },
  errorTitle: {
    fontSize: '1rem',
    fontWeight: '600',
    color: '#dc2626',
  },
  errorMessage: {
    fontSize: '0.85rem',
    color: '#6b7280',
    margin: 0,
    textAlign: 'center' as const,
    lineHeight: '1.5',
  },
  retryButton: {
    padding: '0.625rem 1.25rem',
    fontSize: '0.85rem',
    fontWeight: '600',
    borderRadius: '8px',
    border: 'none',
    background: '#dc2626',
    color: '#fff',
    cursor: 'pointer',
  },
};

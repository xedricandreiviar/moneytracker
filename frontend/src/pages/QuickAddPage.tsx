/**
 * QuickAddPage - Streamlined transaction entry interface.
 * Single-screen layout with amount, direction toggle, and save button visible without scrolling.
 * Supports optional category, note, payment method, and tags.
 * Includes category suggestion with zero-tap accept and single-tap override.
 * Offline support: saves to IndexedDB when offline and syncs on connectivity return.
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8, 4.1, 4.2, 4.3, 4.4, 13.1, 13.2
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { useLocale } from '../contexts/LocaleContext';
import { AmountInput } from '../components/AmountInput';
import { parseAmountInput } from '../utils/locale';
import { isIndexedDBAvailable, savePendingTransaction } from '../services/offlineStore';
import { isOnline, registerBackgroundSync, syncPendingTransactions } from '../services/syncService';
import { OfflineBanner } from '../components/OfflineBanner';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

type Direction = 'spent' | 'received';

interface FieldError {
  field: string;
  message: string;
}

export default function QuickAddPage() {
  const { locale } = useLocale();

  // Core fields
  const [amount, setAmount] = useState('');
  const [direction, setDirection] = useState<Direction>('spent');

  // Optional fields
  const [category, setCategory] = useState('');
  const [note, setNote] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('');
  const [tagsInput, setTagsInput] = useState('');
  const [tags, setTags] = useState<string[]>([]);

  // Frequent categories
  const [frequentCategories, setFrequentCategories] = useState<string[]>([]);

  // Category suggestion state
  const [suggestedCategory, setSuggestedCategory] = useState<string | null>(null);
  const [isSuggestionApplied, setIsSuggestionApplied] = useState(false);
  const [userOverrodeCategory, setUserOverrodeCategory] = useState(false);
  const suggestionDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // UI state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldError[]>([]);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [showSuccess, setShowSuccess] = useState(false);

  // Offline state
  const [showOfflineSaved, setShowOfflineSaved] = useState(false);
  const [showSyncComplete, setShowSyncComplete] = useState(false);
  const [syncedCount, setSyncedCount] = useState(0);
  const [indexedDBUnavailable, setIndexedDBUnavailable] = useState(false);

  // Check IndexedDB availability on mount
  useEffect(() => {
    setIndexedDBUnavailable(!isIndexedDBAvailable());
  }, []);

  // Set up online event listener to sync when connectivity returns
  useEffect(() => {
    function handleOnline() {
      syncPendingTransactions().then((count) => {
        if (count > 0) {
          setSyncedCount(count);
          setShowSyncComplete(true);
          setTimeout(() => setShowSyncComplete(false), 3000);
        }
      });
    }

    window.addEventListener('online', handleOnline);
    return () => window.removeEventListener('online', handleOnline);
  }, []);

  // Fetch frequent categories on mount
  useEffect(() => {
    fetchFrequentCategories();
  }, []);

  // Fetch category suggestion when note or amount changes
  useEffect(() => {
    if (userOverrodeCategory) return;

    if (suggestionDebounceRef.current) {
      clearTimeout(suggestionDebounceRef.current);
    }

    suggestionDebounceRef.current = setTimeout(() => {
      fetchCategorySuggestion();
    }, 500);

    return () => {
      if (suggestionDebounceRef.current) {
        clearTimeout(suggestionDebounceRef.current);
      }
    };
  }, [note, amount]);

  async function fetchCategorySuggestion() {
    if (!locale) return;

    const parsedAmount = amount ? parseAmountInput(amount, locale) : null;
    const trimmedNote = note.trim() || null;

    // Need at least one of note or amount to suggest
    if (!trimmedNote && !parsedAmount) {
      setSuggestedCategory(null);
      setIsSuggestionApplied(false);
      return;
    }

    try {
      const payload: Record<string, unknown> = {};
      if (trimmedNote) payload.note = trimmedNote;
      if (parsedAmount) payload.amount = parsedAmount;

      const response = await axios.post(
        `${API_BASE}/api/transactions/suggest-category`,
        payload,
      );

      const suggested = response.data.suggested_category;
      if (suggested && !userOverrodeCategory) {
        setSuggestedCategory(suggested);
        setCategory(suggested);
        setIsSuggestionApplied(true);
      } else if (!suggested) {
        setSuggestedCategory(null);
        if (isSuggestionApplied) {
          setCategory('');
          setIsSuggestionApplied(false);
        }
      }
    } catch {
      // Non-critical — silently ignore suggestion failures
    }
  }

  async function fetchFrequentCategories() {
    try {
      const response = await axios.get(`${API_BASE}/api/transactions/frequent-categories`);
      setFrequentCategories(response.data.categories || []);
    } catch {
      // Non-critical — silently ignore
    }
  }

  function resetForm() {
    setAmount('');
    setDirection('spent');
    setCategory('');
    setNote('');
    setPaymentMethod('');
    setTagsInput('');
    setTags([]);
    setFieldErrors([]);
    setGeneralError(null);
    setSuggestedCategory(null);
    setIsSuggestionApplied(false);
    setUserOverrodeCategory(false);
  }

  function getFieldError(fieldName: string): string | undefined {
    return fieldErrors.find((e) => e.field === fieldName)?.message;
  }

  /**
   * Handle manual category selection (override).
   * If the user selects a different category than the suggestion, record the override.
   */
  function handleCategoryOverride(newCategory: string) {
    setCategory(newCategory);

    if (suggestedCategory && newCategory !== suggestedCategory && newCategory.trim()) {
      setUserOverrodeCategory(true);
      setIsSuggestionApplied(false);
      // Record override in the background for future suggestion priority
      recordOverride(newCategory);
    }
  }

  async function recordOverride(chosenCategory: string) {
    if (!locale) return;

    try {
      const payload: Record<string, unknown> = {
        category_name: chosenCategory,
      };
      const trimmedNote = note.trim() || null;
      const parsedAmount = amount ? parseAmountInput(amount, locale) : null;

      if (trimmedNote) payload.note = trimmedNote;
      if (parsedAmount) payload.amount = parsedAmount;

      await axios.post(`${API_BASE}/api/transactions/record-override`, payload);
    } catch {
      // Non-critical — silently ignore override recording failures
    }
  }

  const handleTagAdd = useCallback(() => {
    const trimmed = tagsInput.trim();
    if (!trimmed) return;
    if (tags.length >= 10) return;
    if (tags.includes(trimmed)) {
      setTagsInput('');
      return;
    }
    setTags((prev) => [...prev, trimmed]);
    setTagsInput('');
  }, [tagsInput, tags]);

  function handleTagRemove(tag: string) {
    setTags((prev) => prev.filter((t) => t !== tag));
  }

  function handleTagKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      handleTagAdd();
    }
  }

  async function handleSave() {
    if (!locale) return;

    // Client-side validation
    setFieldErrors([]);
    setGeneralError(null);

    const parsedAmount = parseAmountInput(amount, locale);
    if (parsedAmount === null) {
      setFieldErrors([{ field: 'amount', message: 'Enter a valid positive amount' }]);
      return;
    }

    if (note.length > 200) {
      setFieldErrors([{ field: 'note', message: 'Note must be 200 characters or fewer' }]);
      return;
    }

    if (tags.length > 10) {
      setFieldErrors([{ field: 'tags', message: 'Maximum 10 tags allowed' }]);
      return;
    }

    setIsSubmitting(true);

    const payload: Record<string, unknown> = {
      amount_smallest_unit: parsedAmount,
      direction,
      currency_code: locale.currency_code,
    };

    if (category.trim()) payload.category_name = category.trim();
    if (note.trim()) payload.note = note.trim();
    if (paymentMethod.trim()) payload.payment_method = paymentMethod.trim();
    if (tags.length > 0) payload.tags = tags;

    // If offline: save to IndexedDB and register background sync
    if (!isOnline()) {
      // If IndexedDB is unavailable, we cannot save offline — require connectivity
      if (indexedDBUnavailable) {
        setGeneralError('You are offline and offline saving is unavailable. Please connect to save.');
        setIsSubmitting(false);
        return;
      }

      const id = await savePendingTransaction(payload);
      if (id !== null) {
        setShowOfflineSaved(true);
        setTimeout(() => setShowOfflineSaved(false), 4000);
        resetForm();
        // Register background sync for when connectivity returns
        await registerBackgroundSync();
      } else {
        setGeneralError('Failed to save offline. Please try again when connected.');
      }
      setIsSubmitting(false);
      return;
    }

    // Online: POST directly to API (existing behavior)
    try {
      await axios.post(`${API_BASE}/api/transactions`, payload);

      // Show success confirmation
      setShowSuccess(true);
      resetForm();

      // Hide success after 2 seconds
      setTimeout(() => {
        setShowSuccess(false);
      }, 2000);

      // Refresh frequent categories
      fetchFrequentCategories();
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 422) {
          // Field-level validation errors from backend
          const detail = error.response.data?.detail;
          if (Array.isArray(detail)) {
            setFieldErrors(detail as FieldError[]);
          } else {
            setGeneralError('Validation failed. Please check your input.');
          }
        } else if (error.response?.status === 503 || !error.response) {
          // Server unavailable or no response (might be network issue)
          // Try to save offline if IndexedDB is available
          if (!indexedDBUnavailable) {
            const id = await savePendingTransaction(payload);
            if (id !== null) {
              setShowOfflineSaved(true);
              setTimeout(() => setShowOfflineSaved(false), 4000);
              resetForm();
              await registerBackgroundSync();
              setIsSubmitting(false);
              return;
            }
          }
          setGeneralError('Service is temporarily unavailable. Please try again.');
        } else {
          setGeneralError('Something went wrong. Please try again.');
        }
      } else {
        // Network error — attempt offline save
        if (!indexedDBUnavailable) {
          const id = await savePendingTransaction(payload);
          if (id !== null) {
            setShowOfflineSaved(true);
            setTimeout(() => setShowOfflineSaved(false), 4000);
            resetForm();
            await registerBackgroundSync();
            setIsSubmitting(false);
            return;
          }
        }
        setGeneralError('Network error. Please check your connection and try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  if (!locale) {
    return (
      <div className="page page-quick-add">
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div className="page page-quick-add" style={styles.page}>
      <h1 style={styles.heading}>Quick Add</h1>

      {/* Success confirmation */}
      {showSuccess && (
        <div style={styles.successBanner} role="status" aria-live="polite">
          ✓ Transaction saved
        </div>
      )}

      {/* Offline saved indicator */}
      {showOfflineSaved && (
        <div style={styles.offlineSavedBanner} role="status" aria-live="polite">
          📱 Saved offline, will sync when connected
        </div>
      )}

      {/* Sync complete indicator */}
      {showSyncComplete && (
        <div style={styles.syncCompleteBanner} role="status" aria-live="polite">
          ✓ {syncedCount} offline transaction{syncedCount !== 1 ? 's' : ''} synced
        </div>
      )}

      {/* IndexedDB unavailable banner */}
      <OfflineBanner visible={indexedDBUnavailable && !isOnline()} />

      {/* General error with retry */}
      {generalError && (
        <div style={styles.errorBanner} role="alert">
          <span>{generalError}</span>
          <button
            type="button"
            onClick={handleSave}
            style={styles.retryButton}
            aria-label="Retry saving transaction"
          >
            Retry
          </button>
        </div>
      )}

      {/* Core fields — always visible without scrolling */}
      <div style={styles.coreSection}>
        {/* Amount input */}
        <div style={styles.fieldGroup}>
          <AmountInput
            locale={locale}
            value={amount}
            onChange={setAmount}
            error={getFieldError('amount') || getFieldError('amount_smallest_unit')}
            disabled={isSubmitting}
          />
        </div>

        {/* Direction toggle */}
        <div style={styles.directionToggle} role="radiogroup" aria-label="Transaction direction">
          <button
            type="button"
            onClick={() => setDirection('spent')}
            style={{
              ...styles.directionButton,
              ...(direction === 'spent' ? styles.directionButtonActiveSpent : {}),
            }}
            aria-pressed={direction === 'spent'}
            disabled={isSubmitting}
          >
            Spent
          </button>
          <button
            type="button"
            onClick={() => setDirection('received')}
            style={{
              ...styles.directionButton,
              ...(direction === 'received' ? styles.directionButtonActiveReceived : {}),
            }}
            aria-pressed={direction === 'received'}
            disabled={isSubmitting}
          >
            Received
          </button>
        </div>

        {/* Save button */}
        <button
          type="button"
          onClick={handleSave}
          disabled={isSubmitting || !amount}
          style={{
            ...styles.saveButton,
            ...(isSubmitting || !amount ? styles.saveButtonDisabled : {}),
          }}
          aria-label="Save transaction"
        >
          {isSubmitting ? 'Saving...' : 'Save'}
        </button>
      </div>

      {/* Suggested category indicator */}
      {suggestedCategory && isSuggestionApplied && (
        <div style={styles.suggestionBanner} role="status" aria-live="polite">
          <span style={styles.suggestionText}>
            Suggested: <strong>{suggestedCategory}</strong>
          </span>
        </div>
      )}

      {/* Frequent category shortcuts */}
      {frequentCategories.length > 0 && (
        <div style={styles.frequentSection}>
          <span style={styles.frequentLabel}>Quick categories</span>
          <div style={styles.frequentButtons}>
            {frequentCategories.slice(0, 5).map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => handleCategoryOverride(cat)}
                style={{
                  ...styles.frequentButton,
                  ...(category === cat ? styles.frequentButtonActive : {}),
                }}
                disabled={isSubmitting}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Optional fields */}
      <div style={styles.optionalSection}>
        {/* Category */}
        <div style={styles.fieldGroup}>
          <label htmlFor="qa-category" style={styles.label}>
            Category
            {isSuggestionApplied && (
              <span style={styles.suggestedBadge}>Suggested</span>
            )}
          </label>
          <input
            id="qa-category"
            type="text"
            value={category}
            onChange={(e) => handleCategoryOverride(e.target.value)}
            placeholder="e.g. Food, Transport"
            style={{
              ...styles.input,
              ...(getFieldError('category_name') ? styles.inputError : {}),
              ...(isSuggestionApplied ? styles.inputSuggested : {}),
            }}
            disabled={isSubmitting}
            maxLength={100}
            aria-invalid={!!getFieldError('category_name')}
          />
          {getFieldError('category_name') && (
            <p style={styles.fieldErrorText} role="alert">
              {getFieldError('category_name')}
            </p>
          )}
        </div>

        {/* Note */}
        <div style={styles.fieldGroup}>
          <label htmlFor="qa-note" style={styles.label}>
            Note
            <span style={styles.charCounter}>
              {note.length}/200
            </span>
          </label>
          <input
            id="qa-note"
            type="text"
            value={note}
            onChange={(e) => {
              if (e.target.value.length <= 200) setNote(e.target.value);
            }}
            placeholder="Optional note"
            style={{
              ...styles.input,
              ...(getFieldError('note') ? styles.inputError : {}),
            }}
            disabled={isSubmitting}
            maxLength={200}
            aria-invalid={!!getFieldError('note')}
          />
          {getFieldError('note') && (
            <p style={styles.fieldErrorText} role="alert">
              {getFieldError('note')}
            </p>
          )}
        </div>

        {/* Payment method */}
        <div style={styles.fieldGroup}>
          <label htmlFor="qa-payment" style={styles.label}>
            Payment method
          </label>
          <input
            id="qa-payment"
            type="text"
            value={paymentMethod}
            onChange={(e) => setPaymentMethod(e.target.value)}
            placeholder="e.g. Cash, Card"
            style={{
              ...styles.input,
              ...(getFieldError('payment_method') ? styles.inputError : {}),
            }}
            disabled={isSubmitting}
            maxLength={50}
            aria-invalid={!!getFieldError('payment_method')}
          />
          {getFieldError('payment_method') && (
            <p style={styles.fieldErrorText} role="alert">
              {getFieldError('payment_method')}
            </p>
          )}
        </div>

        {/* Tags */}
        <div style={styles.fieldGroup}>
          <label htmlFor="qa-tags" style={styles.label}>
            Tags
            <span style={styles.charCounter}>
              {tags.length}/10
            </span>
          </label>
          <div style={styles.tagsInputRow}>
            <input
              id="qa-tags"
              type="text"
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              onKeyDown={handleTagKeyDown}
              onBlur={handleTagAdd}
              placeholder={tags.length >= 10 ? 'Max tags reached' : 'Add tag, press Enter'}
              style={{
                ...styles.input,
                ...(getFieldError('tags') ? styles.inputError : {}),
              }}
              disabled={isSubmitting || tags.length >= 10}
              aria-invalid={!!getFieldError('tags')}
            />
          </div>
          {tags.length > 0 && (
            <div style={styles.tagsList}>
              {tags.map((tag) => (
                <span key={tag} style={styles.tag}>
                  {tag}
                  <button
                    type="button"
                    onClick={() => handleTagRemove(tag)}
                    style={styles.tagRemove}
                    aria-label={`Remove tag ${tag}`}
                    disabled={isSubmitting}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
          {getFieldError('tags') && (
            <p style={styles.fieldErrorText} role="alert">
              {getFieldError('tags')}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// Inline styles following the project pattern (see OnboardingPage)
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
  coreSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  fieldGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  directionToggle: {
    display: 'flex',
    gap: '0',
    borderRadius: '8px',
    overflow: 'hidden',
    border: '2px solid #e0e0e0',
  },
  directionButton: {
    flex: 1,
    padding: '0.75rem',
    fontSize: '0.95rem',
    fontWeight: '600',
    background: '#fff',
    color: '#6b7280',
    border: 'none',
    cursor: 'pointer',
    transition: 'background 0.2s, color 0.2s',
  },
  directionButtonActiveSpent: {
    background: '#fef2f2',
    color: '#dc2626',
    borderColor: '#dc2626',
  },
  directionButtonActiveReceived: {
    background: '#f0fdf4',
    color: '#16a34a',
    borderColor: '#16a34a',
  },
  saveButton: {
    width: '100%',
    padding: '0.875rem',
    fontSize: '1rem',
    fontWeight: '600',
    borderRadius: '8px',
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    cursor: 'pointer',
    transition: 'background 0.2s',
  },
  saveButtonDisabled: {
    background: '#93c5fd',
    cursor: 'not-allowed',
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
  offlineSavedBanner: {
    padding: '0.75rem 1rem',
    borderRadius: '8px',
    background: '#eff6ff',
    color: '#1d4ed8',
    fontWeight: '600',
    textAlign: 'center' as const,
    border: '1px solid #bfdbfe',
  },
  syncCompleteBanner: {
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
  },
  suggestionBanner: {
    padding: '0.5rem 0.75rem',
    borderRadius: '8px',
    background: '#eff6ff',
    border: '1px solid #bfdbfe',
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  suggestionText: {
    fontSize: '0.85rem',
    color: '#1d4ed8',
  },
  suggestedBadge: {
    fontSize: '0.7rem',
    fontWeight: '500',
    color: '#1d4ed8',
    background: '#dbeafe',
    padding: '0.125rem 0.375rem',
    borderRadius: '4px',
  },
  frequentSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  frequentLabel: {
    fontSize: '0.8rem',
    fontWeight: '600',
    color: '#6b7280',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.05em',
  },
  frequentButtons: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: '0.5rem',
  },
  frequentButton: {
    padding: '0.5rem 0.75rem',
    fontSize: '0.85rem',
    borderRadius: '16px',
    border: '1px solid #e0e0e0',
    background: '#fff',
    color: '#374151',
    cursor: 'pointer',
    transition: 'background 0.2s, border-color 0.2s',
  },
  frequentButtonActive: {
    background: '#eff6ff',
    borderColor: '#2563eb',
    color: '#2563eb',
    fontWeight: '600',
  },
  optionalSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
    paddingTop: '0.5rem',
    borderTop: '1px solid #f3f4f6',
  },
  label: {
    fontSize: '0.85rem',
    fontWeight: '600',
    color: '#374151',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  charCounter: {
    fontSize: '0.75rem',
    fontWeight: '400',
    color: '#9ca3af',
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
  },
  inputError: {
    borderColor: '#dc2626',
    background: '#fef2f2',
  },
  inputSuggested: {
    borderColor: '#3b82f6',
    background: '#eff6ff',
  },
  fieldErrorText: {
    fontSize: '0.8rem',
    color: '#dc2626',
    marginTop: '0.125rem',
  },
  tagsInputRow: {
    display: 'flex',
    gap: '0.5rem',
  },
  tagsList: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: '0.375rem',
    marginTop: '0.25rem',
  },
  tag: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '0.25rem',
    padding: '0.25rem 0.5rem',
    fontSize: '0.8rem',
    borderRadius: '12px',
    background: '#eff6ff',
    color: '#2563eb',
    fontWeight: '500',
  },
  tagRemove: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '16px',
    height: '16px',
    fontSize: '0.9rem',
    borderRadius: '50%',
    background: 'transparent',
    color: '#2563eb',
    cursor: 'pointer',
    lineHeight: 1,
    padding: 0,
    border: 'none',
  },
};

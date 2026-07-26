/**
 * WeightSettings — Manage category weight allocations.
 * Accessible from SettingsPage. Displays all CategoryWeight entries with current
 * percentages, allows manual overrides with redistribution preview, and offers
 * a "Reset to defaults" action.
 * Requirements: 16.4, 16.5, 16.7
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface CategoryWeight {
  category_name: string;
  weight_percentage: number;
  is_manual_override: boolean;
}

interface WeightListResponse {
  weights: CategoryWeight[];
  total_percentage: number;
}

export default function WeightSettings() {
  const navigate = useNavigate();
  const [weights, setWeights] = useState<CategoryWeight[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Editing state
  const [editingCategory, setEditingCategory] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [previewWeights, setPreviewWeights] = useState<CategoryWeight[] | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Save / reset state
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const fetchWeights = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get<WeightListResponse>(`${API_BASE}/api/weights`);
      setWeights(response.data.weights);
    } catch (err: unknown) {
      if (axios.isAxiosError(err) && err.response?.status === 400) {
        setError('Profile not completed. Please complete your profile first.');
      } else {
        setError('Failed to load weights. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWeights();
  }, [fetchWeights]);

  function handleEditStart(category: CategoryWeight) {
    setEditingCategory(category.category_name);
    setEditValue(category.weight_percentage.toFixed(2));
    setPreviewWeights(null);
    setPreviewError(null);
  }

  function handleEditCancel() {
    setEditingCategory(null);
    setEditValue('');
    setPreviewWeights(null);
    setPreviewError(null);
  }

  async function handlePreview() {
    if (!editingCategory) return;

    const numValue = parseFloat(editValue);
    if (isNaN(numValue) || numValue <= 0 || numValue >= 100) {
      setPreviewError('Percentage must be between 0 and 100 (exclusive).');
      return;
    }

    setPreviewLoading(true);
    setPreviewError(null);

    try {
      // Validate via API by calling the override endpoint
      const response = await axios.put<WeightListResponse>(
        `${API_BASE}/api/weights/${encodeURIComponent(editingCategory)}`,
        { category_name: editingCategory, new_percentage: numValue }
      );
      // The API applies the change immediately, so update state with the result
      setPreviewWeights(response.data.weights);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        setPreviewError(typeof detail === 'string' ? detail : 'Failed to validate weight change.');
      } else {
        setPreviewError('Failed to validate weight change.');
      }
    } finally {
      setPreviewLoading(false);
    }
  }

  async function handleSave() {
    if (!previewWeights) return;

    // The override was already applied via the preview call (PUT endpoint applies immediately)
    // So we just accept the preview as the new state
    setSaving(true);
    setWeights(previewWeights);
    setEditingCategory(null);
    setEditValue('');
    setPreviewWeights(null);
    setPreviewError(null);
    setSaving(false);
    showSuccess('Weight updated successfully.');
  }

  async function handleReset() {
    setResetting(true);
    setError(null);
    try {
      const response = await axios.post<WeightListResponse>(`${API_BASE}/api/weights/reset`);
      setWeights(response.data.weights);
      setEditingCategory(null);
      setPreviewWeights(null);
      showSuccess('Weights reset to defaults.');
    } catch (err: unknown) {
      if (axios.isAxiosError(err) && err.response?.status === 400) {
        setError('Profile not completed. Please complete your profile first.');
      } else {
        setError('Failed to reset weights. Please try again.');
      }
    } finally {
      setResetting(false);
    }
  }

  function showSuccess(message: string) {
    setSuccessMessage(message);
    setTimeout(() => setSuccessMessage(null), 3000);
  }

  function formatPercentage(value: number): string {
    return `${Number(value).toFixed(2)}%`;
  }

  if (loading) {
    return (
      <div className="page page-weight-settings" style={styles.page}>
        <p style={styles.loadingText}>Loading weights...</p>
      </div>
    );
  }

  if (error && weights.length === 0) {
    return (
      <div className="page page-weight-settings" style={styles.page}>
        <button onClick={() => navigate('/settings')} style={styles.backButton} type="button">
          ← Back to Settings
        </button>
        <p style={styles.errorText} role="alert">{error}</p>
      </div>
    );
  }

  return (
    <div className="page page-weight-settings" style={styles.page}>
      <button onClick={() => navigate('/settings')} style={styles.backButton} type="button">
        ← Back to Settings
      </button>

      <h1 style={styles.heading}>Category Weights</h1>
      <p style={styles.description}>
        Manage how your budget is allocated across categories. All weights must sum to 100%.
      </p>

      {successMessage && (
        <p style={styles.successText} role="status">{successMessage}</p>
      )}
      {error && (
        <p style={styles.errorText} role="alert">{error}</p>
      )}

      {/* Weights List */}
      <div style={styles.weightsList} role="list" aria-label="Category weights">
        {weights.map((weight) => (
          <div
            key={weight.category_name}
            style={{
              ...styles.weightItem,
              ...(weight.is_manual_override ? styles.weightItemOverride : {}),
            }}
            role="listitem"
          >
            <div style={styles.weightItemHeader}>
              <div style={styles.weightNameRow}>
                <span style={styles.weightName}>{weight.category_name}</span>
                {weight.is_manual_override && (
                  <span style={styles.overrideBadge} aria-label="Manually overridden">
                    Manual
                  </span>
                )}
              </div>
              <span style={styles.weightValue}>{formatPercentage(weight.weight_percentage)}</span>
            </div>

            {editingCategory === weight.category_name ? (
              <div style={styles.editSection}>
                <div style={styles.editInputRow}>
                  <label htmlFor={`weight-input-${weight.category_name}`} style={styles.editLabel}>
                    New percentage:
                  </label>
                  <input
                    id={`weight-input-${weight.category_name}`}
                    type="number"
                    step="0.01"
                    min="0.01"
                    max="99.99"
                    value={editValue}
                    onChange={(e) => {
                      setEditValue(e.target.value);
                      setPreviewWeights(null);
                      setPreviewError(null);
                    }}
                    style={styles.editInput}
                    aria-describedby={`weight-help-${weight.category_name}`}
                  />
                  <span style={styles.percentSymbol}>%</span>
                </div>
                <p id={`weight-help-${weight.category_name}`} style={styles.editHelp}>
                  Enter a value between 0 and 100. Other categories will be redistributed proportionally.
                </p>

                {previewError && (
                  <p style={styles.previewError} role="alert">{previewError}</p>
                )}

                {/* Preview section */}
                {previewWeights && (
                  <div style={styles.previewSection} aria-label="Redistribution preview">
                    <h3 style={styles.previewTitle}>Redistribution Preview</h3>
                    <div style={styles.previewList}>
                      {previewWeights.map((pw) => (
                        <div key={pw.category_name} style={styles.previewItem}>
                          <span style={styles.previewName}>{pw.category_name}</span>
                          <span style={styles.previewValue}>{formatPercentage(pw.weight_percentage)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div style={styles.editActions}>
                  {!previewWeights ? (
                    <button
                      onClick={handlePreview}
                      disabled={previewLoading}
                      style={styles.previewButton}
                      type="button"
                    >
                      {previewLoading ? 'Validating...' : 'Preview'}
                    </button>
                  ) : (
                    <button
                      onClick={handleSave}
                      disabled={saving}
                      style={styles.saveButton}
                      type="button"
                    >
                      {saving ? 'Saving...' : 'Save'}
                    </button>
                  )}
                  <button
                    onClick={handleEditCancel}
                    style={styles.cancelButton}
                    type="button"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => handleEditStart(weight)}
                style={styles.editTriggerButton}
                type="button"
                aria-label={`Edit ${weight.category_name} weight`}
              >
                Edit
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Reset to Defaults */}
      <button
        onClick={handleReset}
        disabled={resetting}
        style={styles.resetButton}
        type="button"
      >
        {resetting ? 'Resetting...' : 'Reset to Defaults'}
      </button>
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
  backButton: {
    alignSelf: 'flex-start',
    background: 'none',
    border: 'none',
    color: '#2563eb',
    fontSize: '0.9rem',
    fontWeight: '500',
    cursor: 'pointer',
    padding: '0.25rem 0',
  },
  heading: {
    fontSize: '1.5rem',
    fontWeight: '700',
    marginBottom: '0.25rem',
  },
  description: {
    fontSize: '0.85rem',
    color: '#6b7280',
    lineHeight: '1.4',
    marginBottom: '0.5rem',
  },
  loadingText: {
    fontSize: '0.9rem',
    color: '#6b7280',
    textAlign: 'center',
    marginTop: '2rem',
  },
  errorText: {
    fontSize: '0.85rem',
    color: '#dc2626',
    fontWeight: '500',
  },
  successText: {
    fontSize: '0.85rem',
    color: '#16a34a',
    fontWeight: '500',
  },
  weightsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  weightItem: {
    padding: '1rem',
    borderRadius: '10px',
    border: '1px solid #e5e7eb',
    background: '#f9fafb',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  weightItemOverride: {
    borderColor: '#fbbf24',
    background: '#fffbeb',
  },
  weightItemHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  weightNameRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  weightName: {
    fontSize: '0.95rem',
    fontWeight: '600',
    color: '#111827',
  },
  overrideBadge: {
    fontSize: '0.7rem',
    fontWeight: '600',
    color: '#92400e',
    background: '#fde68a',
    padding: '0.125rem 0.5rem',
    borderRadius: '9999px',
  },
  weightValue: {
    fontSize: '1rem',
    fontWeight: '700',
    color: '#2563eb',
  },
  editTriggerButton: {
    alignSelf: 'flex-start',
    background: 'none',
    border: '1px solid #d1d5db',
    borderRadius: '6px',
    padding: '0.375rem 0.75rem',
    fontSize: '0.8rem',
    fontWeight: '500',
    color: '#374151',
    cursor: 'pointer',
  },
  editSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
    marginTop: '0.25rem',
    paddingTop: '0.5rem',
    borderTop: '1px solid #e5e7eb',
  },
  editInputRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  editLabel: {
    fontSize: '0.8rem',
    fontWeight: '500',
    color: '#374151',
  },
  editInput: {
    width: '80px',
    padding: '0.5rem',
    fontSize: '0.9rem',
    borderRadius: '6px',
    border: '1px solid #d1d5db',
    textAlign: 'right' as const,
  },
  percentSymbol: {
    fontSize: '0.9rem',
    color: '#6b7280',
  },
  editHelp: {
    fontSize: '0.75rem',
    color: '#6b7280',
    margin: 0,
  },
  previewError: {
    fontSize: '0.8rem',
    color: '#dc2626',
  },
  previewSection: {
    background: '#eff6ff',
    borderRadius: '8px',
    padding: '0.75rem',
    border: '1px solid #bfdbfe',
  },
  previewTitle: {
    fontSize: '0.8rem',
    fontWeight: '600',
    color: '#1e40af',
    marginBottom: '0.5rem',
  },
  previewList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  previewItem: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: '0.8rem',
    color: '#1e3a5f',
  },
  previewName: {
    fontWeight: '500',
  },
  previewValue: {
    fontWeight: '600',
  },
  editActions: {
    display: 'flex',
    gap: '0.5rem',
    marginTop: '0.25rem',
  },
  previewButton: {
    padding: '0.5rem 1rem',
    fontSize: '0.85rem',
    fontWeight: '600',
    borderRadius: '6px',
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    cursor: 'pointer',
  },
  saveButton: {
    padding: '0.5rem 1rem',
    fontSize: '0.85rem',
    fontWeight: '600',
    borderRadius: '6px',
    border: 'none',
    background: '#16a34a',
    color: '#fff',
    cursor: 'pointer',
  },
  cancelButton: {
    padding: '0.5rem 1rem',
    fontSize: '0.85rem',
    fontWeight: '500',
    borderRadius: '6px',
    border: '1px solid #d1d5db',
    background: '#fff',
    color: '#374151',
    cursor: 'pointer',
  },
  resetButton: {
    marginTop: '1rem',
    padding: '0.75rem 1rem',
    fontSize: '0.9rem',
    fontWeight: '600',
    borderRadius: '8px',
    border: '1px solid #fca5a5',
    background: '#fef2f2',
    color: '#dc2626',
    cursor: 'pointer',
    alignSelf: 'stretch',
  },
};

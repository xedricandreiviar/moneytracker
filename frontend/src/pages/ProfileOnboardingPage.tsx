/**
 * ProfileOnboardingPage - Two-step onboarding:
 * Step 1: Lifestyle profile (employment, commute, vehicle)
 * Step 2: Initial balance ("How much money do you have right now?")
 * Displayed after locale onboarding completes, gates main dashboard access
 * until profile_completed is true.
 * Requirements: 15.1, 15.2, 15.3
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useLocale } from '../contexts/LocaleContext';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

type EmploymentStatus = 'student' | 'working' | 'both';
type CommuteMethod = 'public_transit' | 'own_vehicle' | 'walking_biking' | 'none_remote';
type VehicleType = 'motorcycle' | 'car';

interface EmploymentOption {
  value: EmploymentStatus;
  label: string;
}

interface CommuteOption {
  value: CommuteMethod;
  label: string;
}

interface VehicleOption {
  value: VehicleType;
  label: string;
}

const EMPLOYMENT_OPTIONS: EmploymentOption[] = [
  { value: 'student', label: 'Student' },
  { value: 'working', label: 'Working' },
  { value: 'both', label: 'Both' },
];

const COMMUTE_OPTIONS: CommuteOption[] = [
  { value: 'public_transit', label: 'Public Transit' },
  { value: 'own_vehicle', label: 'Own Vehicle' },
  { value: 'walking_biking', label: 'Walking/Biking' },
  { value: 'none_remote', label: 'None/Remote' },
];

const VEHICLE_OPTIONS: VehicleOption[] = [
  { value: 'motorcycle', label: 'Motorcycle' },
  { value: 'car', label: 'Car' },
];

export default function ProfileOnboardingPage() {
  const navigate = useNavigate();
  const { locale } = useLocale();
  const [step, setStep] = useState<'profile' | 'balance'>('profile');
  const [employmentStatus, setEmploymentStatus] = useState<EmploymentStatus | null>(null);
  const [commuteMethod, setCommuteMethod] = useState<CommuteMethod | null>(null);
  const [vehicleType, setVehicleType] = useState<VehicleType | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Balance step state
  const [balanceInput, setBalanceInput] = useState('');
  const [balanceError, setBalanceError] = useState<string | null>(null);

  const showVehicleType = commuteMethod === 'own_vehicle';
  const isFormValid =
    employmentStatus !== null &&
    commuteMethod !== null &&
    (!showVehicleType || vehicleType !== null);

  const currencySymbol = locale?.symbol || '₱';
  const decimalPrecision = locale?.decimal_precision ?? 2;

  function handleCommuteChange(method: CommuteMethod) {
    setCommuteMethod(method);
    if (method !== 'own_vehicle') {
      setVehicleType(null);
    }
  }

  async function handleProfileSubmit() {
    if (!isFormValid) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await axios.put(`${API_BASE}/api/profile`, {
        employment_status: employmentStatus,
        commute_method: commuteMethod,
        vehicle_type: showVehicleType ? vehicleType : null,
      });
      // Move to balance step
      setStep('balance');
    } catch {
      setError('Failed to save your profile. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleBalanceSubmit() {
    const trimmed = balanceInput.trim();
    if (!trimmed) {
      setBalanceError('Please enter an amount');
      return;
    }

    const parsed = parseFloat(trimmed.replace(/,/g, ''));
    if (isNaN(parsed) || parsed < 0) {
      setBalanceError('Please enter a valid positive number');
      return;
    }

    // Convert to smallest currency unit
    const multiplier = Math.pow(10, decimalPrecision);
    const amountSmallestUnit = Math.round(parsed * multiplier);

    setIsSubmitting(true);
    setBalanceError(null);

    try {
      // Log initial balance as a "received" transaction
      await axios.post(`${API_BASE}/api/transactions`, {
        amount_smallest_unit: amountSmallestUnit,
        direction: 'received',
        currency_code: locale?.currency_code || 'PHP',
        note: 'Initial balance',
      });
      navigate('/', { replace: true });
    } catch {
      setBalanceError('Failed to save. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleSkipBalance() {
    navigate('/', { replace: true });
  }

  if (step === 'balance') {
    return (
      <div className="page page-profile-onboarding" style={styles.container}>
        <div style={styles.content}>
          <h1 style={styles.title}>How much money do you have right now?</h1>
          <p style={styles.subtitle}>
            This sets your starting balance so we can track your spending accurately.
          </p>

          <div style={styles.balanceInputWrapper}>
            <span style={styles.currencySymbol}>{currencySymbol}</span>
            <input
              type="text"
              inputMode="decimal"
              value={balanceInput}
              onChange={(e) => {
                setBalanceInput(e.target.value);
                setBalanceError(null);
              }}
              placeholder="0.00"
              style={styles.balanceInput}
              aria-label="Initial balance amount"
              autoFocus
            />
          </div>

          {balanceError && (
            <p style={styles.error} role="alert">
              {balanceError}
            </p>
          )}

          <button
            onClick={handleBalanceSubmit}
            disabled={isSubmitting || !balanceInput.trim()}
            style={{
              ...styles.continueButton,
              ...(isSubmitting || !balanceInput.trim() ? styles.continueButtonDisabled : {}),
            }}
            type="button"
          >
            {isSubmitting ? 'Saving...' : 'Continue'}
          </button>

          <button
            onClick={handleSkipBalance}
            style={styles.skipButton}
            type="button"
          >
            Skip for now
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page page-profile-onboarding" style={styles.container}>
      <div style={styles.content}>
        <h1 style={styles.title}>Tell Us About Yourself</h1>
        <p style={styles.subtitle}>
          This helps us personalize your budget categories and spending recommendations.
        </p>

        {/* Employment Status */}
        <fieldset style={styles.fieldset}>
          <legend style={styles.legend}>Employment Status</legend>
          <div style={styles.radioGroup} role="radiogroup" aria-label="Employment status">
            {EMPLOYMENT_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => setEmploymentStatus(option.value)}
                style={{
                  ...styles.radioButton,
                  ...(employmentStatus === option.value ? styles.radioButtonSelected : {}),
                }}
                aria-pressed={employmentStatus === option.value}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
        </fieldset>

        {/* Commute Method */}
        <fieldset style={styles.fieldset}>
          <legend style={styles.legend}>Commute Method</legend>
          <div style={styles.radioGroup} role="radiogroup" aria-label="Commute method">
            {COMMUTE_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => handleCommuteChange(option.value)}
                style={{
                  ...styles.radioButton,
                  ...(commuteMethod === option.value ? styles.radioButtonSelected : {}),
                }}
                aria-pressed={commuteMethod === option.value}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
        </fieldset>

        {/* Vehicle Type - Conditional */}
        {showVehicleType && (
          <fieldset style={styles.fieldset}>
            <legend style={styles.legend}>Vehicle Type</legend>
            <div style={styles.radioGroup} role="radiogroup" aria-label="Vehicle type">
              {VEHICLE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setVehicleType(option.value)}
                  style={{
                    ...styles.radioButton,
                    ...(vehicleType === option.value ? styles.radioButtonSelected : {}),
                  }}
                  aria-pressed={vehicleType === option.value}
                  type="button"
                >
                  {option.label}
                </button>
              ))}
            </div>
          </fieldset>
        )}

        {error && (
          <p style={styles.error} role="alert">
            {error}
          </p>
        )}

        <button
          onClick={handleProfileSubmit}
          disabled={!isFormValid || isSubmitting}
          style={{
            ...styles.continueButton,
            ...(!isFormValid || isSubmitting ? styles.continueButtonDisabled : {}),
          }}
          type="button"
        >
          {isSubmitting ? 'Saving...' : 'Continue'}
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
    padding: '1rem',
  },
  content: {
    width: '100%',
    maxWidth: '400px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },
  title: {
    fontSize: '1.5rem',
    fontWeight: '700',
    marginBottom: '0.5rem',
    textAlign: 'center',
  },
  subtitle: {
    fontSize: '0.95rem',
    color: '#666',
    textAlign: 'center',
    marginBottom: '1.5rem',
  },
  fieldset: {
    width: '100%',
    border: 'none',
    padding: 0,
    margin: '0 0 1.25rem 0',
  },
  legend: {
    fontSize: '0.9rem',
    fontWeight: '600',
    marginBottom: '0.5rem',
    color: '#333',
  },
  radioGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  radioButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '0.75rem 1rem',
    border: '2px solid #e0e0e0',
    borderRadius: '8px',
    background: '#fff',
    cursor: 'pointer',
    width: '100%',
    fontSize: '0.95rem',
    fontWeight: '500',
    transition: 'border-color 0.2s, background 0.2s',
  },
  radioButtonSelected: {
    borderColor: '#2563eb',
    background: '#eff6ff',
  },
  error: {
    color: '#dc2626',
    fontSize: '0.875rem',
    marginTop: '0.75rem',
  },
  continueButton: {
    marginTop: '1.5rem',
    width: '100%',
    padding: '0.875rem',
    fontSize: '1rem',
    fontWeight: '600',
    borderRadius: '8px',
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    cursor: 'pointer',
  },
  continueButtonDisabled: {
    background: '#93c5fd',
    cursor: 'not-allowed',
  },
  balanceInputWrapper: {
    display: 'flex',
    alignItems: 'center',
    width: '100%',
    border: '2px solid #e0e0e0',
    borderRadius: '8px',
    padding: '0.75rem 1rem',
    background: '#fff',
    marginTop: '1rem',
  },
  currencySymbol: {
    fontSize: '1.5rem',
    fontWeight: '700',
    color: '#374151',
    marginRight: '0.5rem',
  },
  balanceInput: {
    flex: 1,
    border: 'none',
    outline: 'none',
    fontSize: '1.5rem',
    fontWeight: '700',
    color: '#111827',
    background: 'transparent',
  },
  skipButton: {
    marginTop: '0.75rem',
    background: 'none',
    border: 'none',
    color: '#6b7280',
    fontSize: '0.9rem',
    cursor: 'pointer',
    padding: '0.5rem 1rem',
    textDecoration: 'underline',
  },
};

/**
 * OnboardingPage - Prompts the user to select their country.
 * Blocks access to the main interface until a country is selected (Req 14.1, 14.10).
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLocale } from '../contexts/LocaleContext';

interface CountryOption {
  code: string;
  name: string;
  flag: string;
  currency: string;
}

const SUPPORTED_COUNTRIES: CountryOption[] = [
  { code: 'US', name: 'United States', flag: '🇺🇸', currency: 'USD' },
  { code: 'GB', name: 'United Kingdom', flag: '🇬🇧', currency: 'GBP' },
  { code: 'JP', name: 'Japan', flag: '🇯🇵', currency: 'JPY' },
  { code: 'IN', name: 'India', flag: '🇮🇳', currency: 'INR' },
  { code: 'DE', name: 'Germany', flag: '🇩🇪', currency: 'EUR' },
  { code: 'FR', name: 'France', flag: '🇫🇷', currency: 'EUR' },
  { code: 'BR', name: 'Brazil', flag: '🇧🇷', currency: 'BRL' },
  { code: 'AU', name: 'Australia', flag: '🇦🇺', currency: 'AUD' },
  { code: 'CA', name: 'Canada', flag: '🇨🇦', currency: 'CAD' },
  { code: 'KR', name: 'South Korea', flag: '🇰🇷', currency: 'KRW' },
  { code: 'PH', name: 'Philippines', flag: '🇵🇭', currency: 'PHP' },
];

export default function OnboardingPage() {
  const { setLocale } = useLocale();
  const navigate = useNavigate();
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleContinue() {
    if (!selectedCountry) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await setLocale(selectedCountry);
      navigate('/', { replace: true });
    } catch {
      setError('Failed to save your selection. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="page page-onboarding" style={styles.container}>
      <div style={styles.content}>
        <h1 style={styles.title}>Welcome to Daily Money Tracker</h1>
        <p style={styles.subtitle}>
          Select your country to personalize currency, date format, and other settings.
        </p>

        <div style={styles.countryList} role="radiogroup" aria-label="Select your country">
          {SUPPORTED_COUNTRIES.map((country) => (
            <button
              key={country.code}
              onClick={() => setSelectedCountry(country.code)}
              style={{
                ...styles.countryButton,
                ...(selectedCountry === country.code ? styles.countryButtonSelected : {}),
              }}
              aria-pressed={selectedCountry === country.code}
              type="button"
            >
              <span style={styles.flag}>{country.flag}</span>
              <span style={styles.countryName}>{country.name}</span>
              <span style={styles.currencyCode}>{country.currency}</span>
            </button>
          ))}
        </div>

        {error && (
          <p style={styles.error} role="alert">
            {error}
          </p>
        )}

        <button
          onClick={handleContinue}
          disabled={!selectedCountry || isSubmitting}
          style={{
            ...styles.continueButton,
            ...(!selectedCountry || isSubmitting ? styles.continueButtonDisabled : {}),
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
  countryList: {
    width: '100%',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
    maxHeight: '400px',
    overflowY: 'auto',
  },
  countryButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '0.75rem 1rem',
    border: '2px solid #e0e0e0',
    borderRadius: '8px',
    background: '#fff',
    cursor: 'pointer',
    width: '100%',
    textAlign: 'left',
    fontSize: '0.95rem',
    transition: 'border-color 0.2s, background 0.2s',
  },
  countryButtonSelected: {
    borderColor: '#2563eb',
    background: '#eff6ff',
  },
  flag: {
    fontSize: '1.5rem',
  },
  countryName: {
    flex: 1,
    fontWeight: '500',
  },
  currencyCode: {
    fontSize: '0.85rem',
    color: '#888',
    fontWeight: '400',
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
};

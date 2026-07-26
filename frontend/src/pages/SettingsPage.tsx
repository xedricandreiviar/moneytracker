/**
 * SettingsPage — User preferences including country selection and notification toggles.
 * Allows changing country which updates all locale-derived settings immediately (Req 14.7).
 * Existing transactions retain their original currency_code for display (Req 14.8).
 * Allows toggling push notifications independently of in-app notifications.
 * Defaults both to enabled on first use (Req 12.4).
 * Displays guidance when push permission is denied (Req 12.5).
 * Requirements: 12.3, 12.4, 12.5, 14.7, 14.8, 15.5
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useLocale } from '../contexts/LocaleContext';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

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

type PushPermissionState = 'default' | 'granted' | 'denied' | 'unsupported';

function getStorageItem(key: string): string | null {
  try {
    return window.localStorage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function setStorageItem(key: string, value: string): void {
  try {
    window.localStorage?.setItem(key, value);
  } catch {
    // Storage unavailable — preferences won't persist
  }
}

export default function SettingsPage() {
  const { locale, setLocale } = useLocale();
  const navigate = useNavigate();

  // Country change state
  const [selectedCountry, setSelectedCountry] = useState<string>(locale?.country_code ?? '');
  const [countryChanging, setCountryChanging] = useState(false);
  const [countryError, setCountryError] = useState<string | null>(null);
  const [countrySuccess, setCountrySuccess] = useState<string | null>(null);

  // Sync selected country when locale changes (e.g. initial load)
  useEffect(() => {
    if (locale?.country_code) {
      setSelectedCountry(locale.country_code);
    }
  }, [locale?.country_code]);

  async function handleCountryChange(newCountryCode: string) {
    if (newCountryCode === locale?.country_code) return;

    setSelectedCountry(newCountryCode);
    setCountryChanging(true);
    setCountryError(null);
    setCountrySuccess(null);

    try {
      await setLocale(newCountryCode);
      const countryName = SUPPORTED_COUNTRIES.find(c => c.code === newCountryCode)?.name ?? newCountryCode;
      setCountrySuccess(`Country updated to ${countryName}. New transactions will use the updated currency.`);
      // Clear success message after a few seconds
      setTimeout(() => setCountrySuccess(null), 4000);
    } catch {
      setCountryError('Failed to update country. Please try again.');
      // Revert selection on failure
      setSelectedCountry(locale?.country_code ?? '');
    } finally {
      setCountryChanging(false);
    }
  }

  // Notification preferences stored in localStorage (default both enabled per Req 12.4)
  const [inAppEnabled, setInAppEnabled] = useState<boolean>(() => {
    return getStorageItem('notif_inapp_enabled') !== 'false';
  });
  const [pushEnabled, setPushEnabled] = useState<boolean>(() => {
    return getStorageItem('notif_push_enabled') !== 'false';
  });
  const [pushPermission, setPushPermission] = useState<PushPermissionState>('default');
  const [registering, setRegistering] = useState(false);

  // Check current push permission state on mount
  useEffect(() => {
    if (!('Notification' in window) || !('serviceWorker' in navigator)) {
      setPushPermission('unsupported');
      return;
    }
    setPushPermission(Notification.permission as PushPermissionState);
  }, []);

  function handleInAppToggle() {
    const newValue = !inAppEnabled;
    setInAppEnabled(newValue);
    setStorageItem('notif_inapp_enabled', String(newValue));
  }

  async function handlePushToggle() {
    const newValue = !pushEnabled;

    if (newValue) {
      // Enabling push — request permission and register subscription
      if (pushPermission === 'unsupported') {
        return;
      }

      if (pushPermission === 'denied') {
        // Can't re-request if already denied — just show guidance
        return;
      }

      try {
        const permission = await Notification.requestPermission();
        setPushPermission(permission as PushPermissionState);

        if (permission === 'granted') {
          setPushEnabled(true);
          setStorageItem('notif_push_enabled', 'true');
          await registerPushSubscription();
        } else if (permission === 'denied') {
          // Permission denied — fall back to in-app only
          setPushEnabled(false);
          setStorageItem('notif_push_enabled', 'false');
        }
      } catch {
        // Permission request failed — keep current state
      }
    } else {
      // Disabling push
      setPushEnabled(false);
      setStorageItem('notif_push_enabled', 'false');
    }
  }

  async function registerPushSubscription() {
    setRegistering(true);
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: import.meta.env.VITE_VAPID_PUBLIC_KEY,
      });

      const subJson = subscription.toJSON();
      if (subJson.endpoint && subJson.keys) {
        await axios.post(`${API_BASE}/api/notifications/push-subscription`, {
          endpoint: subJson.endpoint,
          keys: {
            p256dh: subJson.keys.p256dh,
            auth: subJson.keys.auth,
          },
        });
      }
    } catch {
      // Registration failed — push won't work but in-app still available
    } finally {
      setRegistering(false);
    }
  }

  return (
    <div className="page page-settings" style={styles.page}>
      <h1 style={styles.heading}>Settings</h1>

      {/* Country / Locale Section (Req 14.7) */}
      <section style={styles.section} aria-labelledby="country-heading">
        <h2 id="country-heading" style={styles.sectionHeading}>Country</h2>
        <p style={styles.countryDescription}>
          Changing your country updates the currency, date format, and week start day for new transactions.
          Existing transactions will continue to display in their original currency.
        </p>

        <div style={styles.selectWrapper}>
          <label htmlFor="country-select" style={styles.selectLabel}>
            Your country
          </label>
          <select
            id="country-select"
            value={selectedCountry}
            onChange={(e) => handleCountryChange(e.target.value)}
            disabled={countryChanging}
            style={styles.select}
            aria-describedby="country-help"
          >
            <option value="" disabled>Select a country</option>
            {SUPPORTED_COUNTRIES.map((country) => (
              <option key={country.code} value={country.code}>
                {country.flag} {country.name} ({country.currency})
              </option>
            ))}
          </select>
        </div>

        {countryChanging && (
          <p style={styles.countryUpdating} aria-live="polite">Updating locale settings...</p>
        )}
        {countryError && (
          <p style={styles.countryError} role="alert">{countryError}</p>
        )}
        {countrySuccess && (
          <p style={styles.countrySuccessMsg} role="status">{countrySuccess}</p>
        )}
      </section>

      {/* Notification Preferences Section */}
      <section style={styles.section} aria-labelledby="notif-heading">
        <h2 id="notif-heading" style={styles.sectionHeading}>Notifications</h2>

        {/* In-App Notifications Toggle */}
        <div style={styles.toggleRow}>
          <div style={styles.toggleInfo}>
            <span style={styles.toggleLabel}>In-app notifications</span>
            <span style={styles.toggleDescription}>
              Show notification banners inside the app
            </span>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={inAppEnabled}
            onClick={handleInAppToggle}
            style={{
              ...styles.toggleButton,
              ...(inAppEnabled ? styles.toggleButtonOn : styles.toggleButtonOff),
            }}
            aria-label="Toggle in-app notifications"
          >
            <span
              style={{
                ...styles.toggleKnob,
                ...(inAppEnabled ? styles.toggleKnobOn : styles.toggleKnobOff),
              }}
            />
          </button>
        </div>

        {/* Push Notifications Toggle */}
        <div style={styles.toggleRow}>
          <div style={styles.toggleInfo}>
            <span style={styles.toggleLabel}>Push notifications</span>
            <span style={styles.toggleDescription}>
              Receive alerts even when the app is closed
            </span>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={pushEnabled}
            onClick={handlePushToggle}
            disabled={pushPermission === 'unsupported' || registering}
            style={{
              ...styles.toggleButton,
              ...(pushEnabled && pushPermission === 'granted'
                ? styles.toggleButtonOn
                : styles.toggleButtonOff),
              ...(pushPermission === 'unsupported' ? styles.toggleButtonDisabled : {}),
            }}
            aria-label="Toggle push notifications"
          >
            <span
              style={{
                ...styles.toggleKnob,
                ...(pushEnabled && pushPermission === 'granted'
                  ? styles.toggleKnobOn
                  : styles.toggleKnobOff),
              }}
            />
          </button>
        </div>

        {/* Push permission denied guidance (Req 12.5) */}
        {pushPermission === 'denied' && (
          <div style={styles.guidanceBox} role="alert">
            <span style={styles.guidanceIcon} aria-hidden="true">ℹ️</span>
            <div style={styles.guidanceContent}>
              <span style={styles.guidanceTitle}>Push notifications blocked</span>
              <span style={styles.guidanceText}>
                Your browser has blocked push notifications for this app.
                To re-enable them, open your browser settings, find this site
                in the notifications or permissions section, and change the
                setting from "Block" to "Allow". Then return here and toggle
                push notifications on.
              </span>
            </div>
          </div>
        )}

        {/* Push unsupported message */}
        {pushPermission === 'unsupported' && (
          <div style={styles.guidanceBox} role="note">
            <span style={styles.guidanceIcon} aria-hidden="true">⚠️</span>
            <div style={styles.guidanceContent}>
              <span style={styles.guidanceText}>
                Push notifications are not supported in this browser.
                In-app notifications will still work.
              </span>
            </div>
          </div>
        )}

        {registering && (
          <p style={styles.registeringText}>Registering push subscription...</p>
        )}
      </section>

      {/* Lifestyle Profile Section (Req 15.5) */}
      <section style={styles.section} aria-labelledby="profile-heading">
        <h2 id="profile-heading" style={styles.sectionHeading}>Lifestyle Profile</h2>
        <p style={styles.countryDescription}>
          Your lifestyle details are used to personalize budget category weights.
        </p>
        <button
          type="button"
          onClick={() => navigate('/settings/profile')}
          style={styles.profileLink}
          aria-label="Edit lifestyle profile"
        >
          <span style={styles.profileLinkText}>Edit Lifestyle Profile</span>
          <span style={styles.profileLinkArrow} aria-hidden="true">→</span>
        </button>
      </section>

      {/* Category Weights Section (Req 16.4, 16.5, 16.7) */}
      <section style={styles.section} aria-labelledby="weights-heading">
        <h2 id="weights-heading" style={styles.sectionHeading}>Category Weights</h2>
        <p style={styles.countryDescription}>
          View and adjust how your budget is allocated across spending categories.
        </p>
        <button
          type="button"
          onClick={() => navigate('/settings/weights')}
          style={styles.profileLink}
          aria-label="Manage category weights"
        >
          <span style={styles.profileLinkText}>Manage Category Weights</span>
          <span style={styles.profileLinkArrow} aria-hidden="true">→</span>
        </button>
      </section>
    </div>
  );
}

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
    marginBottom: '0.25rem',
  },
  section: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  sectionHeading: {
    fontSize: '1rem',
    fontWeight: '600',
    color: '#374151',
    marginBottom: '0.25rem',
  },
  countryDescription: {
    fontSize: '0.8rem',
    color: '#6b7280',
    lineHeight: '1.4',
    marginBottom: '0.25rem',
  },
  selectWrapper: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.375rem',
  },
  selectLabel: {
    fontSize: '0.8rem',
    fontWeight: '500',
    color: '#374151',
  },
  select: {
    width: '100%',
    padding: '0.75rem 1rem',
    fontSize: '0.9rem',
    borderRadius: '10px',
    border: '1px solid #e5e7eb',
    background: '#f9fafb',
    color: '#111827',
    cursor: 'pointer',
    appearance: 'none' as const,
    WebkitAppearance: 'none' as const,
    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%236b7280' d='M6 8L1 3h10z'/%3E%3C/svg%3E")`,
    backgroundRepeat: 'no-repeat',
    backgroundPosition: 'right 1rem center',
    paddingRight: '2.5rem',
  },
  countryUpdating: {
    fontSize: '0.8rem',
    color: '#6b7280',
    fontStyle: 'italic',
  },
  countryError: {
    fontSize: '0.8rem',
    color: '#dc2626',
    fontWeight: '500',
  },
  countrySuccessMsg: {
    fontSize: '0.8rem',
    color: '#16a34a',
    fontWeight: '500',
  },
  toggleRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '1rem',
    padding: '0.75rem 1rem',
    borderRadius: '10px',
    background: '#f9fafb',
    border: '1px solid #e5e7eb',
  },
  toggleInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.125rem',
  },
  toggleLabel: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#111827',
  },
  toggleDescription: {
    fontSize: '0.75rem',
    color: '#6b7280',
  },
  toggleButton: {
    position: 'relative' as const,
    width: '44px',
    height: '24px',
    borderRadius: '12px',
    border: 'none',
    cursor: 'pointer',
    transition: 'background 0.2s',
    flexShrink: 0,
    padding: 0,
  },
  toggleButtonOn: {
    background: '#2563eb',
  },
  toggleButtonOff: {
    background: '#d1d5db',
  },
  toggleButtonDisabled: {
    background: '#e5e7eb',
    cursor: 'not-allowed',
    opacity: 0.6,
  },
  toggleKnob: {
    position: 'absolute' as const,
    top: '2px',
    width: '20px',
    height: '20px',
    borderRadius: '50%',
    background: '#ffffff',
    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
    transition: 'left 0.2s',
  },
  toggleKnobOn: {
    left: '22px',
  },
  toggleKnobOff: {
    left: '2px',
  },
  guidanceBox: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '0.5rem',
    padding: '0.75rem 1rem',
    borderRadius: '10px',
    background: '#fef3c7',
    border: '1px solid #fde68a',
  },
  guidanceIcon: {
    fontSize: '1rem',
    lineHeight: 1,
    marginTop: '0.1rem',
  },
  guidanceContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  guidanceTitle: {
    fontSize: '0.85rem',
    fontWeight: '600',
    color: '#92400e',
  },
  guidanceText: {
    fontSize: '0.78rem',
    color: '#78350f',
    lineHeight: '1.4',
  },
  registeringText: {
    fontSize: '0.8rem',
    color: '#6b7280',
    fontStyle: 'italic',
  },
  profileLink: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0.875rem 1rem',
    borderRadius: '10px',
    background: '#f9fafb',
    border: '1px solid #e5e7eb',
    cursor: 'pointer',
    width: '100%',
    textAlign: 'left' as const,
  },
  profileLinkText: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#111827',
  },
  profileLinkArrow: {
    fontSize: '1rem',
    color: '#6b7280',
  },
};

/**
 * LocaleContext provides locale configuration state throughout the app.
 * Handles fetching locale from the backend and tracking onboarding status.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import axios from 'axios';
import { type LocaleConfig } from '../types/locale';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface LocaleState {
  /** The user's locale config, or null if onboarding is incomplete */
  locale: (LocaleConfig & { country_code: string }) | null;
  /** Whether we're still loading the locale from the backend */
  loading: boolean;
  /** Whether onboarding is complete (locale is set) */
  isOnboarded: boolean;
  /** Update locale after country selection */
  setLocale: (countryCode: string) => Promise<void>;
}

const LocaleContext = createContext<LocaleState | undefined>(undefined);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<(LocaleConfig & { country_code: string }) | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchLocale();
  }, []);

  async function fetchLocale() {
    try {
      const response = await axios.get(`${API_BASE}/api/settings/locale`);
      setLocaleState(response.data);
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        // Locale not set — onboarding required
        setLocaleState(null);
      } else {
        // Network or other error — treat as not onboarded for safety
        setLocaleState(null);
      }
    } finally {
      setLoading(false);
    }
  }

  async function setLocale(countryCode: string) {
    const response = await axios.put(`${API_BASE}/api/settings/locale`, {
      country_code: countryCode,
    });
    setLocaleState(response.data.locale);
  }

  return (
    <LocaleContext.Provider
      value={{
        locale,
        loading,
        isOnboarded: locale !== null,
        setLocale,
      }}
    >
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale(): LocaleState {
  const context = useContext(LocaleContext);
  if (!context) {
    throw new Error('useLocale must be used within a LocaleProvider');
  }
  return context;
}

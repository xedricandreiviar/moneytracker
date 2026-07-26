import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { LocaleProvider } from '../contexts/LocaleContext';

// Mock axios to control locale and profile API responses
vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
    isAxiosError: (error: unknown) =>
      error !== null && typeof error === 'object' && 'response' in (error as object),
  },
}));

import axios from 'axios';
const mockedAxios = vi.mocked(axios);

function renderWithProviders(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <LocaleProvider>
        <App />
      </LocaleProvider>
    </MemoryRouter>,
  );
}

const LOCALE_RESPONSE = {
  country_code: 'US',
  currency_code: 'USD',
  currency_symbol: '$',
  decimal_precision: 2,
  decimal_separator: '.',
  thousands_separator: ',',
  date_format: 'MM/DD/YYYY',
  week_start_day: 0,
};

const PROFILE_RESPONSE = {
  employment_status: 'working',
  commute_method: 'public_transit',
  vehicle_type: null,
  profile_completed: true,
};

describe('App setup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('when locale and profile are configured (fully onboarded)', () => {
    beforeEach(() => {
      // Mock both locale and profile endpoints
      mockedAxios.get.mockImplementation((url: string) => {
        if (url.includes('/api/settings/locale')) {
          return Promise.resolve({ data: LOCALE_RESPONSE });
        }
        if (url.includes('/api/profile')) {
          return Promise.resolve({ data: PROFILE_RESPONSE });
        }
        // Default: return empty for budgets, notifications, etc.
        if (url.includes('/api/budgets')) {
          return Promise.resolve({ data: { budgets: [] } });
        }
        if (url.includes('/api/daily-task')) {
          return Promise.resolve({ data: { status: 'completed' } });
        }
        if (url.includes('/api/streak')) {
          return Promise.resolve({ data: { current_streak: 0 } });
        }
        if (url.includes('/api/notifications')) {
          return Promise.resolve({ data: [] });
        }
        if (url.includes('/api/dashboard/insight')) {
          return Promise.resolve({ data: { insight_text: '', category_focus: null } });
        }
        return Promise.resolve({ data: {} });
      });
    });

    it('renders the home page at root route', async () => {
      renderWithProviders('/');
      expect(await screen.findByText('Daily Money Tracker')).toBeInTheDocument();
    });

    it('renders the quick add page', async () => {
      renderWithProviders('/quick-add');
      expect(await screen.findByText('Quick Add')).toBeInTheDocument();
    });

    it('renders the budgets page', async () => {
      renderWithProviders('/budgets');
      expect(await screen.findByText('Budgets')).toBeInTheDocument();
    });

    it('renders the insights page', async () => {
      renderWithProviders('/insights');
      expect(await screen.findByText('Insights')).toBeInTheDocument();
    });

    it('renders the AI chat page', async () => {
      renderWithProviders('/ai-chat');
      expect(await screen.findByText('AI Assistant')).toBeInTheDocument();
    });

    it('renders the settings page', async () => {
      renderWithProviders('/settings');
      expect(await screen.findByText('Settings')).toBeInTheDocument();
    });

    it('redirects unknown routes to home', async () => {
      renderWithProviders('/unknown-route');
      expect(await screen.findByText('Daily Money Tracker')).toBeInTheDocument();
    });
  });

  describe('when locale is not configured (onboarding required)', () => {
    beforeEach(() => {
      // Simulate a 404 response for locale and profile
      mockedAxios.get.mockImplementation((url: string) => {
        if (url.includes('/api/settings/locale')) {
          return Promise.reject({ response: { status: 404 } });
        }
        if (url.includes('/api/profile')) {
          return Promise.reject({ response: { status: 404 } });
        }
        return Promise.resolve({ data: {} });
      });
    });

    it('renders the onboarding page at /onboarding', async () => {
      renderWithProviders('/onboarding');
      expect(
        await screen.findByText('Welcome to Daily Money Tracker'),
      ).toBeInTheDocument();
    });

    it('redirects root to onboarding when locale is not set', async () => {
      renderWithProviders('/');
      expect(
        await screen.findByText('Welcome to Daily Money Tracker'),
      ).toBeInTheDocument();
    });

    it('redirects protected routes to onboarding', async () => {
      renderWithProviders('/budgets');
      expect(
        await screen.findByText('Welcome to Daily Money Tracker'),
      ).toBeInTheDocument();
    });
  });

  describe('when locale is set but profile is not completed', () => {
    beforeEach(() => {
      // Locale is configured but profile returns 404 (not completed)
      mockedAxios.get.mockImplementation((url: string) => {
        if (url.includes('/api/settings/locale')) {
          return Promise.resolve({ data: LOCALE_RESPONSE });
        }
        if (url.includes('/api/profile')) {
          return Promise.reject({ response: { status: 404 } });
        }
        return Promise.resolve({ data: {} });
      });
    });

    it('redirects root to profile onboarding', async () => {
      renderWithProviders('/');
      expect(
        await screen.findByText('Tell Us About Yourself'),
      ).toBeInTheDocument();
    });

    it('redirects protected routes to profile onboarding', async () => {
      renderWithProviders('/budgets');
      expect(
        await screen.findByText('Tell Us About Yourself'),
      ).toBeInTheDocument();
    });

    it('allows access to locale onboarding page', async () => {
      renderWithProviders('/onboarding');
      expect(
        await screen.findByText('Welcome to Daily Money Tracker'),
      ).toBeInTheDocument();
    });

    it('allows access to profile onboarding page', async () => {
      renderWithProviders('/profile-onboarding');
      expect(
        await screen.findByText('Tell Us About Yourself'),
      ).toBeInTheDocument();
    });
  });
});

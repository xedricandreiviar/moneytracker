import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { LocaleProvider } from '../contexts/LocaleContext';

// Mock axios to control locale API responses
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

describe('App setup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('when locale is configured (onboarded)', () => {
    beforeEach(() => {
      // Simulate a user who has already onboarded
      mockedAxios.get.mockResolvedValue({
        data: {
          country_code: 'US',
          currency_code: 'USD',
          currency_symbol: '$',
          decimal_precision: 2,
          decimal_separator: '.',
          thousands_separator: ',',
          date_format: 'MM/DD/YYYY',
          week_start_day: 0,
        },
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
      // Simulate a 404 response - locale not configured
      const error = { response: { status: 404 } };
      mockedAxios.get.mockRejectedValue(error);
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
});

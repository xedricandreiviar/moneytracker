/**
 * Integration test: End-to-end onboarding flow.
 * Verifies: Locale onboarding → Profile onboarding → Dashboard
 *
 * Tests:
 * - New user → select country → fill profile → see dashboard with budget cards reflecting derived weights
 * - profile_completed gate blocks dashboard access correctly
 * - Weight derivation triggers on first profile submission
 *
 * Requirements: 15.1, 15.6, 16.3
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { LocaleProvider } from '../contexts/LocaleContext';

// Mock axios to control API responses
vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
    isAxiosError: (error: unknown) =>
      error !== null && typeof error === 'object' && 'response' in (error as object),
  },
}));

import axios from 'axios';
const mockedAxios = vi.mocked(axios);

const LOCALE_US = {
  country_code: 'US',
  currency_code: 'USD',
  currency_symbol: '$',
  decimal_precision: 2,
  decimal_separator: '.',
  thousands_separator: ',',
  date_format: 'MM/DD/YYYY',
  week_start_day: 0,
};

const PROFILE_COMPLETED = {
  employment_status: 'working',
  commute_method: 'public_transit',
  vehicle_type: null,
  profile_completed: true,
};

const BUDGET_WITH_WEIGHTS = {
  budgets: [
    {
      id: 1,
      category_id: 10,
      category_name: 'Savings',
      period_type: 'monthly',
      limit_smallest_unit: 30000,
      currency_code: 'USD',
      is_active: true,
      projection: {
        status: 'on_track',
        remaining: 25000,
        projected_spend: 5000,
      },
    },
    {
      id: 2,
      category_id: 11,
      category_name: 'Food',
      period_type: 'monthly',
      limit_smallest_unit: 30000,
      currency_code: 'USD',
      is_active: true,
      projection: {
        status: 'off_track',
        remaining: -5000,
        projected_spend: 35000,
      },
    },
  ],
};

function renderWithProviders(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <LocaleProvider>
        <App />
      </LocaleProvider>
    </MemoryRouter>,
  );
}

describe('Onboarding Flow End-to-End', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('profile_completed gate blocks dashboard access', () => {
    it('redirects to /profile-onboarding when locale is set but profile is incomplete', async () => {
      mockedAxios.get.mockImplementation((url: string) => {
        if (url.includes('/api/settings/locale')) {
          return Promise.resolve({ data: LOCALE_US });
        }
        if (url.includes('/api/profile')) {
          return Promise.reject({ response: { status: 404 } });
        }
        return Promise.resolve({ data: {} });
      });

      renderWithProviders('/');
      expect(
        await screen.findByText('Tell Us About Yourself'),
      ).toBeInTheDocument();
    });

    it('blocks access to dashboard routes when profile is not completed', async () => {
      mockedAxios.get.mockImplementation((url: string) => {
        if (url.includes('/api/settings/locale')) {
          return Promise.resolve({ data: LOCALE_US });
        }
        if (url.includes('/api/profile')) {
          // Profile exists but not completed
          return Promise.resolve({ data: { profile_completed: false } });
        }
        return Promise.resolve({ data: {} });
      });

      renderWithProviders('/budgets');
      expect(
        await screen.findByText('Tell Us About Yourself'),
      ).toBeInTheDocument();
    });

    it('allows access to dashboard when profile is completed', async () => {
      mockedAxios.get.mockImplementation((url: string) => {
        if (url.includes('/api/settings/locale')) {
          return Promise.resolve({ data: LOCALE_US });
        }
        if (url.includes('/api/profile')) {
          return Promise.resolve({ data: PROFILE_COMPLETED });
        }
        if (url.includes('/api/budgets')) {
          return Promise.resolve({ data: { budgets: [] } });
        }
        if (url.includes('/api/dashboard/insight')) {
          return Promise.resolve({ data: { insight_text: '', category_focus: null } });
        }
        return Promise.resolve({ data: {} });
      });

      renderWithProviders('/');
      expect(await screen.findByText('Daily Money Tracker')).toBeInTheDocument();
    });
  });

  describe('new user → select country → fill profile → dashboard', () => {
    it('completes full onboarding flow from locale selection to profile submission', async () => {
      let localeSet = false;
      let profileCompleted = false;

      mockedAxios.get.mockImplementation((url: string) => {
        if (url.includes('/api/settings/locale')) {
          if (localeSet) {
            return Promise.resolve({ data: LOCALE_US });
          }
          return Promise.reject({ response: { status: 404 } });
        }
        if (url.includes('/api/profile')) {
          if (profileCompleted) {
            return Promise.resolve({ data: PROFILE_COMPLETED });
          }
          return Promise.reject({ response: { status: 404 } });
        }
        if (url.includes('/api/budgets')) {
          return Promise.resolve({ data: BUDGET_WITH_WEIGHTS });
        }
        if (url.includes('/api/dashboard/insight')) {
          return Promise.resolve({
            data: {
              insight_text: 'Savings is your top priority at 30.00%. Consider automating transfers.',
              category_focus: 'Savings',
            },
          });
        }
        return Promise.resolve({ data: {} });
      });

      mockedAxios.put.mockImplementation((url: string) => {
        if (url.includes('/api/settings/locale')) {
          localeSet = true;
          return Promise.resolve({ data: { locale: LOCALE_US } });
        }
        if (url.includes('/api/profile')) {
          profileCompleted = true;
          return Promise.resolve({ data: PROFILE_COMPLETED });
        }
        return Promise.resolve({ data: {} });
      });

      // Step 1: New user lands at root, redirected to /onboarding
      renderWithProviders('/');
      expect(
        await screen.findByText('Welcome to Daily Money Tracker'),
      ).toBeInTheDocument();

      // Step 2: User selects United States
      const usButton = screen.getByText('United States');
      fireEvent.click(usButton);

      // Step 3: User clicks Continue
      const continueButton = screen.getByText('Continue');
      expect(continueButton).not.toBeDisabled();
      fireEvent.click(continueButton);

      // Step 4: After locale is saved, user is redirected to profile onboarding
      expect(
        await screen.findByText('Tell Us About Yourself'),
      ).toBeInTheDocument();

      // Step 5: User fills in employment status
      const workingButton = screen.getByText('Working');
      fireEvent.click(workingButton);

      // Step 6: User fills in commute method
      const publicTransitButton = screen.getByText('Public Transit');
      fireEvent.click(publicTransitButton);

      // Step 7: User submits profile
      const profileContinueButton = screen.getByText('Continue');
      expect(profileContinueButton).not.toBeDisabled();
      fireEvent.click(profileContinueButton);

      // Step 8: After profile is submitted, user reaches the dashboard
      expect(await screen.findByText('Daily Money Tracker')).toBeInTheDocument();

      // Step 9: Dashboard shows budget cards reflecting derived weights
      // The budget response includes "Savings" (on track) and "Food" (off track)
      await waitFor(() => {
        expect(screen.getByText('On Track')).toBeInTheDocument();
        expect(screen.getByText('Off Track')).toBeInTheDocument();
      });
    });

    it('shows personalized insight on dashboard after profile completion', async () => {
      mockedAxios.get.mockImplementation((url: string) => {
        if (url.includes('/api/settings/locale')) {
          return Promise.resolve({ data: LOCALE_US });
        }
        if (url.includes('/api/profile')) {
          return Promise.resolve({ data: PROFILE_COMPLETED });
        }
        if (url.includes('/api/budgets')) {
          return Promise.resolve({ data: BUDGET_WITH_WEIGHTS });
        }
        if (url.includes('/api/dashboard/insight')) {
          return Promise.resolve({
            data: {
              insight_text: 'Savings is your top priority at 30.00%. Consider automating transfers.',
              category_focus: 'Savings',
            },
          });
        }
        return Promise.resolve({ data: {} });
      });

      renderWithProviders('/');

      // Dashboard should show the personalized insight
      expect(
        await screen.findByText(/Savings is your top priority/),
      ).toBeInTheDocument();
      expect(screen.getByText('Savings Tip')).toBeInTheDocument();
    });

    it('shows vehicle type field when own_vehicle is selected during profile onboarding', async () => {
      mockedAxios.get.mockImplementation((url: string) => {
        if (url.includes('/api/settings/locale')) {
          return Promise.resolve({ data: LOCALE_US });
        }
        if (url.includes('/api/profile')) {
          return Promise.reject({ response: { status: 404 } });
        }
        return Promise.resolve({ data: {} });
      });

      renderWithProviders('/profile-onboarding');

      expect(
        await screen.findByText('Tell Us About Yourself'),
      ).toBeInTheDocument();

      // Select employment status
      fireEvent.click(screen.getByText('Student'));

      // Select commute method - own vehicle
      fireEvent.click(screen.getByText('Own Vehicle'));

      // Vehicle type options should appear
      expect(screen.getByText('Vehicle Type')).toBeInTheDocument();
      expect(screen.getByText('Motorcycle')).toBeInTheDocument();
      expect(screen.getByText('Car')).toBeInTheDocument();

      // Continue should be disabled until vehicle type is selected
      expect(screen.getByText('Continue')).toBeDisabled();

      // Select vehicle type
      fireEvent.click(screen.getByText('Car'));

      // Now Continue should be enabled
      expect(screen.getByText('Continue')).not.toBeDisabled();
    });
  });

  describe('weight derivation triggers on first profile submission', () => {
    it('PUT /api/profile is called with correct payload during profile onboarding', async () => {
      mockedAxios.get.mockImplementation((url: string) => {
        if (url.includes('/api/settings/locale')) {
          return Promise.resolve({ data: LOCALE_US });
        }
        if (url.includes('/api/profile')) {
          return Promise.reject({ response: { status: 404 } });
        }
        return Promise.resolve({ data: {} });
      });

      mockedAxios.put.mockImplementation((url: string) => {
        if (url.includes('/api/profile')) {
          return Promise.resolve({ data: PROFILE_COMPLETED });
        }
        return Promise.resolve({ data: {} });
      });

      renderWithProviders('/profile-onboarding');
      await screen.findByText('Tell Us About Yourself');

      // Fill the form
      fireEvent.click(screen.getByText('Student'));
      fireEvent.click(screen.getByText('Walking/Biking'));

      // Submit
      fireEvent.click(screen.getByText('Continue'));

      await waitFor(() => {
        expect(mockedAxios.put).toHaveBeenCalledWith(
          expect.stringContaining('/api/profile'),
          {
            employment_status: 'student',
            commute_method: 'walking_biking',
            vehicle_type: null,
          },
        );
      });
    });

    it('PUT /api/profile sends vehicle_type when commute is own_vehicle', async () => {
      mockedAxios.get.mockImplementation((url: string) => {
        if (url.includes('/api/settings/locale')) {
          return Promise.resolve({ data: LOCALE_US });
        }
        if (url.includes('/api/profile')) {
          return Promise.reject({ response: { status: 404 } });
        }
        return Promise.resolve({ data: {} });
      });

      mockedAxios.put.mockImplementation((url: string) => {
        if (url.includes('/api/profile')) {
          return Promise.resolve({
            data: {
              ...PROFILE_COMPLETED,
              commute_method: 'own_vehicle',
              vehicle_type: 'motorcycle',
            },
          });
        }
        return Promise.resolve({ data: {} });
      });

      renderWithProviders('/profile-onboarding');
      await screen.findByText('Tell Us About Yourself');

      // Fill the form with own vehicle
      fireEvent.click(screen.getByText('Both'));
      fireEvent.click(screen.getByText('Own Vehicle'));
      fireEvent.click(screen.getByText('Motorcycle'));

      // Submit
      fireEvent.click(screen.getByText('Continue'));

      await waitFor(() => {
        expect(mockedAxios.put).toHaveBeenCalledWith(
          expect.stringContaining('/api/profile'),
          {
            employment_status: 'both',
            commute_method: 'own_vehicle',
            vehicle_type: 'motorcycle',
          },
        );
      });
    });
  });
});

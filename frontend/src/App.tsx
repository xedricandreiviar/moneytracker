import { Routes, Route, Navigate } from 'react-router-dom';
import {
  HomePage,
  QuickAddPage,
  BudgetsPage,
  InsightsPage,
  AIChatPage,
  AICoachingPage,
  SettingsPage,
  WeightSettings,
  OnboardingPage,
  ProfileOnboardingPage,
  ProfileSettings,
} from './pages';
import { ErrorBoundary } from './components/ErrorBoundary';
import { useLocale } from './contexts/LocaleContext';
import { useProfileStatus } from './hooks/useProfileStatus';
import './App.css';

/**
 * ProtectedRoute blocks access to the main interface until onboarding
 * is complete (country selected) and profile is completed.
 * Redirects to /onboarding if locale is not set.
 * Redirects to /profile-onboarding if locale is set but profile is incomplete.
 * Requirement 14.10: Block access until country is selected.
 * Requirement 15.1: Block dashboard until profile_completed.
 */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isOnboarded, loading } = useLocale();
  const { profileCompleted, loading: profileLoading } = useProfileStatus();

  if (loading || profileLoading) {
    return (
      <div className="app-loading" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <p>Loading...</p>
      </div>
    );
  }

  if (!isOnboarded) {
    return <Navigate to="/onboarding" replace />;
  }

  if (!profileCompleted) {
    return <Navigate to="/profile-onboarding" replace />;
  }

  return <>{children}</>;
}

function App() {
  return (
    <ErrorBoundary>
      <div className="app-container">
        <Routes>
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/profile-onboarding" element={<ProfileOnboardingPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <HomePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/quick-add"
          element={
            <ProtectedRoute>
              <QuickAddPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/budgets"
          element={
            <ProtectedRoute>
              <BudgetsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/insights"
          element={
            <ProtectedRoute>
              <InsightsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/ai-chat"
          element={
            <ProtectedRoute>
              <AIChatPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/ai-coaching"
          element={
            <ProtectedRoute>
              <AICoachingPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings/profile"
          element={
            <ProtectedRoute>
              <ProfileSettings />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings/weights"
          element={
            <ProtectedRoute>
              <WeightSettings />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <SettingsPage />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </ErrorBoundary>
  );
}

export default App;

import { Routes, Route, Navigate } from 'react-router-dom';
import {
  HomePage,
  QuickAddPage,
  BudgetsPage,
  InsightsPage,
  AIChatPage,
  AICoachingPage,
  SettingsPage,
  OnboardingPage,
} from './pages';
import { ErrorBoundary } from './components/ErrorBoundary';
import { useLocale } from './contexts/LocaleContext';
import './App.css';

/**
 * ProtectedRoute blocks access to the main interface until onboarding
 * is complete (country selected). Redirects to /onboarding if locale is not set.
 * Requirement 14.10: Block access until country is selected.
 */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isOnboarded, loading } = useLocale();

  if (loading) {
    return (
      <div className="app-loading" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <p>Loading...</p>
      </div>
    );
  }

  if (!isOnboarded) {
    return <Navigate to="/onboarding" replace />;
  }

  return <>{children}</>;
}

function App() {
  return (
    <ErrorBoundary>
      <div className="app-container">
        <Routes>
        <Route path="/onboarding" element={<OnboardingPage />} />
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

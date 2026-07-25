import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { LocaleProvider } from './contexts/LocaleContext';
import './index.css';
import App from './App.tsx';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <LocaleProvider>
        <App />
      </LocaleProvider>
    </BrowserRouter>
  </StrictMode>,
);

/**
 * Service worker registration with graceful degradation.
 * If registration fails, the app continues working normally without offline support.
 * vite-plugin-pwa with registerType: 'autoUpdate' handles most of this automatically,
 * but we add explicit error handling for diagnostics.
 * Requirement 13.2: Graceful degradation when service worker registration fails.
 */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js', { scope: '/' })
      .then((registration) => {
        console.info('[SW] Service worker registered successfully:', registration.scope);
      })
      .catch((error) => {
        // App continues without offline support — non-blocking
        console.warn(
          '[SW] Service worker registration failed. App will continue without offline support.',
          error,
        );
      });
  });
}

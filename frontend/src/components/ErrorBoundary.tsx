import { Component, type ReactNode, type ErrorInfo } from 'react';

/**
 * Global ErrorBoundary - catches unhandled React errors and shows a friendly
 * fallback UI with a reload button, preventing the entire app from crashing.
 * Requirement 13.2: Graceful degradation and error handling.
 */

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Log the error for diagnostics
    console.error('[ErrorBoundary] Uncaught error:', error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={styles.container} role="alert" aria-live="assertive">
          <div style={styles.card}>
            <div style={styles.icon} aria-hidden="true">⚠️</div>
            <h1 style={styles.heading}>Something went wrong</h1>
            <p style={styles.message}>
              An unexpected error occurred. Please reload the page to continue.
            </p>
            <button
              type="button"
              onClick={this.handleReload}
              style={styles.reloadButton}
              aria-label="Reload the page"
            >
              Reload
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
    padding: '1rem',
    background: '#f9fafb',
  },
  card: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '1rem',
    padding: '2rem',
    maxWidth: '360px',
    width: '100%',
    borderRadius: '12px',
    background: '#fff',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    textAlign: 'center' as const,
  },
  icon: {
    fontSize: '2.5rem',
  },
  heading: {
    fontSize: '1.25rem',
    fontWeight: '700',
    color: '#111827',
    margin: 0,
  },
  message: {
    fontSize: '0.95rem',
    color: '#6b7280',
    lineHeight: 1.5,
    margin: 0,
  },
  reloadButton: {
    padding: '0.75rem 1.5rem',
    fontSize: '1rem',
    fontWeight: '600',
    borderRadius: '8px',
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    cursor: 'pointer',
    transition: 'background 0.2s',
  },
};

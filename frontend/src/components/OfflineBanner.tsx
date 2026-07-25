/**
 * OfflineBanner - Displayed when IndexedDB is unavailable.
 * Informs the user that offline saving is not possible and connectivity is required.
 * Requirements: 13.2
 */

interface OfflineBannerProps {
  /** Whether IndexedDB is unavailable (show the banner) */
  visible: boolean;
}

export function OfflineBanner({ visible }: OfflineBannerProps) {
  if (!visible) return null;

  return (
    <div
      role="alert"
      aria-live="polite"
      style={styles.banner}
    >
      <span style={styles.icon} aria-hidden="true">⚠️</span>
      <span style={styles.text}>
        Offline saving unavailable — please connect to save transactions
      </span>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  banner: {
    padding: '0.75rem 1rem',
    borderRadius: '8px',
    background: '#fffbeb',
    border: '1px solid #fde68a',
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  icon: {
    fontSize: '1rem',
    flexShrink: 0,
  },
  text: {
    fontSize: '0.85rem',
    color: '#92400e',
    fontWeight: '500',
  },
};

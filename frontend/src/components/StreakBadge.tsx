/**
 * StreakBadge — Displays the user's current streak count with a visual indicator.
 * Shows a flame icon and count of consecutive days the user has completed their daily task.
 * Requirements: 1.6, 2.2
 */
import { useState, useEffect } from 'react';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface StreakData {
  current_streak: number;
  grace_period_active: boolean;
  grace_remaining_hours: number;
  grace_remaining_minutes: number;
}

export function StreakBadge() {
  const [streak, setStreak] = useState<StreakData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStreak();
  }, []);

  async function fetchStreak() {
    try {
      const response = await axios.get<StreakData>(`${API_BASE}/api/streak`);
      const data = response.data;
      // Validate that we got actual streak data
      if (data && typeof data.current_streak === 'number') {
        setStreak(data);
      }
    } catch {
      // Non-critical — silently ignore
    } finally {
      setLoading(false);
    }
  }

  if (loading || !streak) {
    return null;
  }

  const hasStreak = streak.current_streak > 0;
  const isAtRisk = streak.grace_period_active;

  return (
    <div
      style={{
        ...styles.container,
        ...(isAtRisk ? styles.containerAtRisk : {}),
      }}
      role="status"
      aria-label={`Current streak: ${streak.current_streak} day${streak.current_streak !== 1 ? 's' : ''}`}
    >
      <span style={styles.icon} aria-hidden="true">
        {hasStreak ? '🔥' : '💤'}
      </span>
      <div style={styles.info}>
        <span style={styles.count}>{streak.current_streak}</span>
        <span style={styles.label}>
          {streak.current_streak === 1 ? 'day streak' : 'day streak'}
        </span>
      </div>
      {isAtRisk && (
        <span style={styles.atRiskBadge} aria-label="Streak at risk">
          ⚠️ At risk
        </span>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '0.75rem 1rem',
    borderRadius: '12px',
    background: '#fffbeb',
    border: '1px solid #fde68a',
  },
  containerAtRisk: {
    background: '#fef2f2',
    border: '1px solid #fecaca',
  },
  icon: {
    fontSize: '1.5rem',
    lineHeight: 1,
  },
  info: {
    display: 'flex',
    alignItems: 'baseline',
    gap: '0.375rem',
    flex: 1,
  },
  count: {
    fontSize: '1.25rem',
    fontWeight: '700',
    color: '#92400e',
  },
  label: {
    fontSize: '0.85rem',
    color: '#92400e',
    fontWeight: '500',
  },
  atRiskBadge: {
    fontSize: '0.75rem',
    fontWeight: '600',
    color: '#dc2626',
    background: '#fee2e2',
    padding: '0.25rem 0.5rem',
    borderRadius: '6px',
    whiteSpace: 'nowrap' as const,
  },
};

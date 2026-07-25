/**
 * DailyTaskBanner — Shows incomplete daily task with hours remaining,
 * a "no transactions" single-tap button, and grace period countdown.
 * Requirements: 1.2, 1.3, 1.4, 2.4
 */
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface DailyTaskData {
  id: number;
  user_id: number;
  task_date: string;
  status: string;
  completion_type: string | null;
  completed_at_utc: string | null;
  hours_remaining: number;
}

interface StreakData {
  current_streak: number;
  grace_period_active: boolean;
  grace_remaining_hours: number;
  grace_remaining_minutes: number;
}

export function DailyTaskBanner() {
  const [task, setTask] = useState<DailyTaskData | null>(null);
  const [streak, setStreak] = useState<StreakData | null>(null);
  const [loading, setLoading] = useState(true);
  const [completing, setCompleting] = useState(false);
  const [completed, setCompleted] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [taskRes, streakRes] = await Promise.all([
        axios.get<DailyTaskData>(`${API_BASE}/api/daily-task`),
        axios.get<StreakData>(`${API_BASE}/api/streak`),
      ]);
      // Validate that we got actual task/streak data
      const taskData = taskRes.data;
      const streakData = streakRes.data;
      if (taskData && typeof taskData.status === 'string') {
        setTask(taskData);
      }
      if (streakData && typeof streakData.current_streak === 'number') {
        setStreak(streakData);
      }
    } catch {
      // Non-critical — silently ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  async function handleNoTransactions() {
    setCompleting(true);
    try {
      await axios.post(`${API_BASE}/api/daily-task/complete`);
      setCompleted(true);
    } catch {
      // Show a brief error — user can retry
    } finally {
      setCompleting(false);
    }
  }

  if (loading) {
    return null;
  }

  // If task is already completed or marked done just now, show success
  if (completed || (task && task.status === 'completed')) {
    return (
      <div style={styles.containerCompleted} role="status" aria-live="polite">
        <span style={styles.checkIcon} aria-hidden="true">✓</span>
        <span style={styles.completedText}>Today's task complete</span>
      </div>
    );
  }

  // No task available
  if (!task) {
    return null;
  }

  const isGracePeriod = streak?.grace_period_active || task.status === 'grace_period';

  return (
    <div
      style={{
        ...styles.container,
        ...(isGracePeriod ? styles.containerGrace : {}),
      }}
      role="status"
      aria-live="polite"
    >
      <div style={styles.content}>
        <div style={styles.topRow}>
          <span style={styles.taskIcon} aria-hidden="true">
            {isGracePeriod ? '⏰' : '📋'}
          </span>
          <span style={styles.title}>
            {isGracePeriod ? 'Recover your streak' : 'Log today\'s spending'}
          </span>
        </div>

        <div style={styles.timeRow}>
          {isGracePeriod && streak ? (
            <GracePeriodCountdown
              hours={streak.grace_remaining_hours}
              minutes={streak.grace_remaining_minutes}
            />
          ) : (
            <span style={styles.timeText}>
              {formatHoursRemaining(task.hours_remaining)} remaining
            </span>
          )}
        </div>
      </div>

      <button
        type="button"
        onClick={handleNoTransactions}
        disabled={completing}
        style={{
          ...styles.noTransactionsButton,
          ...(completing ? styles.noTransactionsButtonDisabled : {}),
        }}
        aria-label="Mark as no transactions today"
      >
        {completing ? '...' : 'No transactions'}
      </button>
    </div>
  );
}

/**
 * Grace period countdown display showing remaining hours and minutes.
 * Requirement 2.4
 */
function GracePeriodCountdown({ hours, minutes }: { hours: number; minutes: number }) {
  return (
    <span style={styles.graceText}>
      <span style={styles.graceCountdown}>
        {hours}h {minutes}m
      </span>
      {' '}left to recover
    </span>
  );
}

/**
 * Format hours remaining into a human-readable string.
 */
function formatHoursRemaining(hours: number): string {
  if (hours <= 0) return 'Less than 1 hour';
  if (hours === 1) return '1 hour';
  if (hours < 24) return `${Math.floor(hours)} hours`;
  return `${Math.floor(hours)} hours`;
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '0.875rem 1rem',
    borderRadius: '12px',
    background: '#eff6ff',
    border: '1px solid #bfdbfe',
  },
  containerGrace: {
    background: '#fef3c7',
    border: '1px solid #fde68a',
  },
  containerCompleted: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    padding: '0.75rem 1rem',
    borderRadius: '12px',
    background: '#f0fdf4',
    border: '1px solid #bbf7d0',
  },
  content: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  topRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  taskIcon: {
    fontSize: '1.1rem',
    lineHeight: 1,
  },
  title: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#1e40af',
  },
  timeRow: {
    paddingLeft: '1.6rem',
  },
  timeText: {
    fontSize: '0.8rem',
    color: '#3b82f6',
    fontWeight: '500',
  },
  graceText: {
    fontSize: '0.8rem',
    color: '#92400e',
    fontWeight: '500',
  },
  graceCountdown: {
    fontWeight: '700',
    color: '#d97706',
    fontSize: '0.85rem',
  },
  noTransactionsButton: {
    padding: '0.5rem 0.75rem',
    fontSize: '0.8rem',
    fontWeight: '600',
    borderRadius: '8px',
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
    transition: 'background 0.2s',
  },
  noTransactionsButtonDisabled: {
    background: '#93c5fd',
    cursor: 'not-allowed',
  },
  checkIcon: {
    fontSize: '1rem',
    color: '#16a34a',
    fontWeight: '700',
  },
  completedText: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#16a34a',
  },
};

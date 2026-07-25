/**
 * NotificationBanner — Displays unread notifications on the HomePage.
 * Fetches from GET /api/notifications, shows count and recent items,
 * and allows marking individual notifications as read.
 * Requirements: 12.1, 12.3, 12.4, 12.5
 */
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface Notification {
  id: number;
  user_id: number;
  notification_type: string;
  title: string;
  body: string;
  payload: Record<string, unknown> | null;
  is_read: boolean;
  created_at_utc: string;
}

interface NotificationListResponse {
  notifications: Notification[];
  count: number;
}

function getStorageItem(key: string): string | null {
  try {
    return window.localStorage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

export function NotificationBanner() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  // Check if in-app notifications are enabled (default true per Req 12.4)
  const inAppEnabled = getStorageItem('notif_inapp_enabled') !== 'false';

  const fetchNotifications = useCallback(async () => {
    if (!inAppEnabled) {
      setLoading(false);
      return;
    }
    try {
      const response = await axios.get<NotificationListResponse>(
        `${API_BASE}/api/notifications`
      );
      const data = response.data;
      if (data && Array.isArray(data.notifications)) {
        setNotifications(data.notifications);
        setCount(data.count);
      }
    } catch {
      // Non-critical — silently ignore
    } finally {
      setLoading(false);
    }
  }, [inAppEnabled]);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  async function handleMarkRead(notificationId: number) {
    try {
      await axios.put(`${API_BASE}/api/notifications/${notificationId}/read`);
      setNotifications((prev) => prev.filter((n) => n.id !== notificationId));
      setCount((prev) => Math.max(0, prev - 1));
    } catch {
      // Non-critical — silently ignore
    }
  }

  // Don't render if in-app notifications are disabled
  if (!inAppEnabled) {
    return null;
  }

  if (loading) {
    return null;
  }

  // No unread notifications
  if (count === 0) {
    return null;
  }

  return (
    <div style={styles.container} role="region" aria-label="Notifications">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        style={styles.header}
        aria-expanded={expanded}
        aria-controls="notification-list"
      >
        <span style={styles.bellIcon} aria-hidden="true">🔔</span>
        <span style={styles.headerText}>
          {count} unread notification{count !== 1 ? 's' : ''}
        </span>
        <span style={styles.chevron} aria-hidden="true">
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {expanded && (
        <ul id="notification-list" style={styles.list} role="list">
          {notifications.slice(0, 5).map((notification) => (
            <li key={notification.id} style={styles.item}>
              <div style={styles.itemContent}>
                <span style={styles.itemIcon} aria-hidden="true">
                  {getNotificationIcon(notification.notification_type)}
                </span>
                <div style={styles.itemText}>
                  <span style={styles.itemTitle}>{notification.title}</span>
                  <span style={styles.itemBody}>{notification.body}</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => handleMarkRead(notification.id)}
                style={styles.markReadButton}
                aria-label={`Mark "${notification.title}" as read`}
              >
                ✓
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function getNotificationIcon(type: string): string {
  switch (type) {
    case 'daily_reminder':
      return '📋';
    case 'budget_80':
    case 'budget_100':
      return '💰';
    case 'spike_alert':
      return '📈';
    case 'summary_ready':
      return '📊';
    case 'ai_coaching':
      return '🤖';
    default:
      return '🔔';
  }
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    borderRadius: '12px',
    background: '#f0f9ff',
    border: '1px solid #bae6fd',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    width: '100%',
    padding: '0.75rem 1rem',
    background: 'transparent',
    border: 'none',
    cursor: 'pointer',
    textAlign: 'left' as const,
  },
  bellIcon: {
    fontSize: '1.1rem',
    lineHeight: 1,
  },
  headerText: {
    flex: 1,
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#0369a1',
  },
  chevron: {
    fontSize: '0.7rem',
    color: '#0369a1',
  },
  list: {
    listStyle: 'none',
    margin: 0,
    padding: '0 0.75rem 0.75rem 0.75rem',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.5rem',
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    padding: '0.5rem 0.75rem',
    borderRadius: '8px',
    background: '#ffffff',
    border: '1px solid #e0f2fe',
  },
  itemContent: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '0.5rem',
    flex: 1,
  },
  itemIcon: {
    fontSize: '0.9rem',
    lineHeight: 1,
    marginTop: '0.15rem',
  },
  itemText: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.125rem',
  },
  itemTitle: {
    fontSize: '0.8rem',
    fontWeight: '600',
    color: '#1e3a5f',
  },
  itemBody: {
    fontSize: '0.75rem',
    color: '#64748b',
    lineHeight: '1.3',
  },
  markReadButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    border: '1px solid #bae6fd',
    background: '#e0f2fe',
    color: '#0369a1',
    fontSize: '0.8rem',
    fontWeight: '700',
    cursor: 'pointer',
    flexShrink: 0,
  },
};

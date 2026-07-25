/**
 * Custom Service Worker with caching, Background Sync, and Push Notification support.
 * Requirements: 12.1, 13.1, 13.2
 */
/// <reference lib="webworker" />

import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching';
import { registerRoute } from 'workbox-routing';
import { CacheFirst, NetworkFirst, StaleWhileRevalidate } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';
import { CacheableResponsePlugin } from 'workbox-cacheable-response';

declare const self: ServiceWorkerGlobalScope;

// ==============================
// Precaching & Runtime Caching
// ==============================

// Precache app shell (HTML, JS, CSS) - injected by vite-plugin-pwa at build time
precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

// Runtime caching: Locale configs (CacheFirst - long-lived, rarely changes)
registerRoute(
  ({ url }) => /\/api\/settings\/locale$/.test(url.pathname),
  new CacheFirst({
    cacheName: 'locale-configs',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 20,
        maxAgeSeconds: 60 * 60 * 24 * 7, // 7 days
      }),
      new CacheableResponsePlugin({ statuses: [0, 200] }),
    ],
  })
);

// Runtime caching: Recent transactions (NetworkFirst with stale fallback)
registerRoute(
  ({ url }) => /\/api\/transactions/.test(url.pathname),
  new NetworkFirst({
    cacheName: 'transactions-api',
    networkTimeoutSeconds: 5,
    plugins: [
      new ExpirationPlugin({
        maxEntries: 50,
        maxAgeSeconds: 60 * 5, // 5 minutes
      }),
      new CacheableResponsePlugin({ statuses: [0, 200] }),
    ],
  })
);

// Runtime caching: Budget status (NetworkFirst with 5-minute cache fallback)
registerRoute(
  ({ url }) => /\/api\/budgets/.test(url.pathname),
  new NetworkFirst({
    cacheName: 'budgets-api',
    networkTimeoutSeconds: 5,
    plugins: [
      new ExpirationPlugin({
        maxEntries: 30,
        maxAgeSeconds: 60 * 5, // 5 minutes
      }),
      new CacheableResponsePlugin({ statuses: [0, 200] }),
    ],
  })
);

// Runtime caching: Static assets (StaleWhileRevalidate)
registerRoute(
  ({ url }) => /\.(?:js|css|woff2?|png|jpg|jpeg|gif|svg|ico)$/.test(url.pathname),
  new StaleWhileRevalidate({
    cacheName: 'static-assets',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 100,
        maxAgeSeconds: 60 * 60 * 24 * 30, // 30 days
      }),
      new CacheableResponsePlugin({ statuses: [0, 200] }),
    ],
  })
);

// ==============================
// Background Sync (Offline Transactions)
// ==============================

const API_BASE = 'http://localhost:8000';
const DB_NAME = 'daily-money-tracker';
const STORE_NAME = 'pending_transactions';

/**
 * Open IndexedDB from the service worker context.
 * Uses raw IndexedDB API since the `idb` package may not be available in SW scope.
 */
function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, {
          keyPath: 'id',
          autoIncrement: true,
        });
        store.createIndex('pending_sync', 'pending_sync');
      }
    };
  });
}

interface PendingRecord {
  id: number;
  payload: Record<string, unknown>;
  created_at: string;
  pending_sync: boolean;
}

/**
 * Get all pending transactions from IndexedDB.
 */
function getPendingTransactions(db: IDBDatabase): Promise<PendingRecord[]> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const request = store.getAll();
    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const all = request.result as PendingRecord[];
      resolve(all.filter((t) => t.pending_sync));
    };
  });
}

/**
 * Delete a transaction record from IndexedDB after successful sync.
 */
function deleteTransaction(db: IDBDatabase, id: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const request = store.delete(id);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
  });
}

/**
 * Handle the Background Sync event.
 * Reads pending transactions from IndexedDB, POSTs to the API, and removes on success.
 */
async function syncTransactions(): Promise<void> {
  const db = await openDatabase();

  try {
    const pending = await getPendingTransactions(db);
    if (pending.length === 0) return;

    for (const transaction of pending) {
      try {
        const response = await fetch(`${API_BASE}/api/transactions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(transaction.payload),
        });

        if (response.ok) {
          // Success — remove from IndexedDB
          await deleteTransaction(db, transaction.id);
        } else if (response.status >= 400 && response.status < 500) {
          // Client error — invalid data, remove to prevent infinite retries
          await deleteTransaction(db, transaction.id);
        }
        // 5xx errors: leave in place for next sync attempt
      } catch {
        // Network error — leave in place, will retry on next sync event
      }
    }
  } finally {
    db.close();
  }
}

// Listen for Background Sync events
// Using addEventListener with string type since SyncEvent is not in the standard TS lib
self.addEventListener('sync', ((event: Event & { tag?: string; waitUntil?: (p: Promise<unknown>) => void }) => {
  if (event.tag === 'sync-transactions' && event.waitUntil) {
    event.waitUntil(syncTransactions());
  }
}) as EventListener);

// ==============================
// Push Notification Handling
// ==============================

/**
 * Push notification payload structure from the backend.
 * Supports all notification types:
 * - daily_reminder: Daily task reminder
 * - budget_80: Budget 80% threshold alert
 * - budget_100: Budget 100% threshold alert
 * - spike_alert: Spending spike alert
 * - summary_ready: Periodic summary availability
 * - ai_coaching: AI proactive coaching suggestion
 */
interface PushPayload {
  title?: string;
  body?: string;
  tag?: string;
  notification_type?: string;
  url?: string;
  icon?: string;
  badge?: string;
}

/**
 * Handle incoming push events for all notification types.
 * Displays a notification with:
 * - Icon: 192px app icon
 * - Badge: 72px monochrome badge
 * - Tag: prevents duplicate notifications of the same type
 * - Action URL: stored in notification data for click handling
 */
self.addEventListener('push', (event: PushEvent) => {
  if (!event.data) return;

  let payload: PushPayload;
  try {
    payload = event.data.json();
  } catch {
    // Ignore malformed push data
    return;
  }

  const title = payload.title || 'Daily Money Tracker';
  const options: NotificationOptions & { vibrate?: number[]; renotify?: boolean } = {
    body: payload.body || '',
    // Use tag to prevent duplicate notifications of the same type
    // Prefer the specific tag from payload, fall back to notification_type
    tag: payload.tag || payload.notification_type || 'general',
    // 192px icon for the notification
    icon: payload.icon || '/icons/icon-192x192.png',
    // 72px badge (monochrome, shown in status bar on mobile)
    badge: payload.badge || '/icons/badge-72x72.svg',
    // Store action URL for notificationclick handler
    data: { url: payload.url || '/' },
    // Vibrate pattern for mobile devices
    vibrate: [100, 50, 100],
    // Renotify: show updated notification even if same tag already shown
    renotify: true,
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

/**
 * Handle notification click events.
 * Closes the notification and opens/focuses the action URL.
 * Tries to:
 * 1. Focus an existing window already at the action URL
 * 2. Navigate an existing window to the action URL
 * 3. Open a new window at the action URL
 */
self.addEventListener('notificationclick', (event: NotificationEvent) => {
  // Close the notification
  event.notification.close();

  const actionUrl: string = event.notification.data?.url || '/';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Try to focus an existing window that's already at the action URL
      for (const client of clientList) {
        if (client.url.includes(actionUrl) && 'focus' in client) {
          return (client as WindowClient).focus();
        }
      }

      // Try to navigate an existing window to the action URL
      for (const client of clientList) {
        if ('focus' in client && 'navigate' in client) {
          return (client as WindowClient).focus().then((focusedClient) =>
            focusedClient.navigate(actionUrl)
          );
        }
      }

      // Otherwise open a new window
      return self.clients.openWindow(actionUrl);
    })
  );
});

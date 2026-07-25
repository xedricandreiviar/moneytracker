/**
 * Sync service for offline transaction queue.
 * Reads pending transactions from IndexedDB, POSTs to the API, and clears on success.
 * Registers Background Sync with the service worker for automatic retry on connectivity return.
 * Requirements: 13.1, 13.2
 */
import axios from 'axios';
import {
  getPendingTransactions,
  deletePendingTransaction,
  getStaleTransactions,
  type PendingTransaction,
} from './offlineStore';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const SYNC_TAG = 'sync-transactions';

/**
 * Check if the browser is currently online.
 */
export function isOnline(): boolean {
  return navigator.onLine;
}

/**
 * Register a Background Sync event with the service worker.
 * Falls back silently if Background Sync API is not supported.
 */
export async function registerBackgroundSync(): Promise<boolean> {
  try {
    if (!('serviceWorker' in navigator)) return false;

    const registration = await navigator.serviceWorker.ready;

    // Check if sync is supported
    if (!('sync' in registration)) return false;

    // TypeScript doesn't have built-in types for Background Sync
    await (registration as unknown as { sync: { register: (tag: string) => Promise<void> } })
      .sync.register(SYNC_TAG);
    return true;
  } catch {
    // Background Sync not supported or registration failed — not critical
    return false;
  }
}

/**
 * Sync all pending transactions to the API.
 * For each pending transaction:
 * - POST to the API
 * - On success: delete from IndexedDB
 * - On failure: leave in place for next retry
 *
 * Returns the count of successfully synced transactions.
 */
export async function syncPendingTransactions(): Promise<number> {
  const pending = await getPendingTransactions();
  if (pending.length === 0) return 0;

  let syncedCount = 0;

  for (const transaction of pending) {
    try {
      await axios.post(`${API_BASE}/api/transactions`, transaction.payload);

      // Success — remove from IndexedDB
      if (transaction.id !== undefined) {
        await deletePendingTransaction(transaction.id);
      }
      syncedCount++;
    } catch (error: unknown) {
      // If it's a client error (4xx), the transaction data is invalid
      // Remove it to prevent infinite retries
      if (axios.isAxiosError(error) && error.response && error.response.status >= 400 && error.response.status < 500) {
        if (transaction.id !== undefined) {
          await deletePendingTransaction(transaction.id);
        }
      }
      // For 5xx or network errors, leave in place for next retry
    }
  }

  return syncedCount;
}

/**
 * Check if any pending transactions are stale (older than 24 hours).
 * Returns stale transactions that need user attention.
 */
export async function checkStaleTransactions(): Promise<PendingTransaction[]> {
  return getStaleTransactions(24);
}

/**
 * Set up online/offline event listeners to trigger sync on connectivity return.
 * Call this once during app initialization.
 */
export function setupConnectivityListeners(
  onSyncComplete?: (count: number) => void,
  onStaleDetected?: (stale: PendingTransaction[]) => void
): () => void {
  async function handleOnline() {
    // Try to sync pending transactions
    const synced = await syncPendingTransactions();
    if (synced > 0 && onSyncComplete) {
      onSyncComplete(synced);
    }

    // Check for stale transactions that need user prompt
    const stale = await checkStaleTransactions();
    if (stale.length > 0 && onStaleDetected) {
      onStaleDetected(stale);
    }
  }

  window.addEventListener('online', handleOnline);

  // Cleanup function
  return () => {
    window.removeEventListener('online', handleOnline);
  };
}

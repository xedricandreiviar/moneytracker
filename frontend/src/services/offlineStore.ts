/**
 * Offline transaction storage using IndexedDB.
 * Provides a queue for transactions saved while offline, with a `pending_sync` flag.
 * Handles IndexedDB unavailability gracefully via feature detection.
 * Requirements: 13.1, 13.2
 */
import { openDB, type IDBPDatabase } from 'idb';

const DB_NAME = 'daily-money-tracker';
const DB_VERSION = 1;
const STORE_NAME = 'pending_transactions';

export interface PendingTransaction {
  id?: number;
  /** Transaction payload to POST to the API */
  payload: Record<string, unknown>;
  /** ISO string of when the transaction was saved offline */
  created_at: string;
  /** Whether this transaction is still awaiting sync */
  pending_sync: boolean;
}

let dbInstance: IDBPDatabase | null = null;
let indexedDBAvailable: boolean | null = null;

/**
 * Detect whether IndexedDB is available in the current environment.
 */
export function isIndexedDBAvailable(): boolean {
  if (indexedDBAvailable !== null) return indexedDBAvailable;

  try {
    if (typeof indexedDB === 'undefined' || !indexedDB) {
      indexedDBAvailable = false;
      return false;
    }
    // Test that we can actually open a database
    indexedDBAvailable = true;
    return true;
  } catch {
    indexedDBAvailable = false;
    return false;
  }
}

/**
 * Open (or reuse) the IndexedDB database connection.
 * Returns null if IndexedDB is unavailable.
 */
async function getDB(): Promise<IDBPDatabase | null> {
  if (!isIndexedDBAvailable()) return null;
  if (dbInstance) return dbInstance;

  try {
    dbInstance = await openDB(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, {
            keyPath: 'id',
            autoIncrement: true,
          });
          store.createIndex('pending_sync', 'pending_sync');
        }
      },
    });
    return dbInstance;
  } catch {
    // If opening fails (e.g., private browsing mode in some browsers)
    indexedDBAvailable = false;
    return null;
  }
}

/**
 * Save a transaction to IndexedDB with pending_sync flag set to true.
 * Returns the auto-generated id, or null if IndexedDB is unavailable.
 */
export async function savePendingTransaction(
  payload: Record<string, unknown>
): Promise<number | null> {
  const db = await getDB();
  if (!db) return null;

  const record: PendingTransaction = {
    payload,
    created_at: new Date().toISOString(),
    pending_sync: true,
  };

  const id = await db.add(STORE_NAME, record);
  return id as number;
}

/**
 * Get all transactions with pending_sync = true.
 */
export async function getPendingTransactions(): Promise<PendingTransaction[]> {
  const db = await getDB();
  if (!db) return [];

  const all = await db.getAll(STORE_NAME);
  return all.filter((t: PendingTransaction) => t.pending_sync);
}

/**
 * Delete a pending transaction by id (called after successful sync).
 */
export async function deletePendingTransaction(id: number): Promise<void> {
  const db = await getDB();
  if (!db) return;

  await db.delete(STORE_NAME, id);
}

/**
 * Get count of pending transactions awaiting sync.
 */
export async function getPendingCount(): Promise<number> {
  const db = await getDB();
  if (!db) return 0;

  const all = await db.getAll(STORE_NAME);
  return all.filter((t: PendingTransaction) => t.pending_sync).length;
}

/**
 * Get all transactions that are older than the specified hours.
 * Used to identify stale entries that need user attention.
 */
export async function getStaleTransactions(maxAgeHours: number = 24): Promise<PendingTransaction[]> {
  const db = await getDB();
  if (!db) return [];

  const cutoff = new Date(Date.now() - maxAgeHours * 60 * 60 * 1000).toISOString();
  const all = await db.getAll(STORE_NAME);
  return all.filter(
    (t: PendingTransaction) => t.pending_sync && t.created_at < cutoff
  );
}

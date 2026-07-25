/**
 * Unit tests for offlineStore service.
 * Tests IndexedDB-based offline transaction queue.
 * Requirements: 13.1, 13.2
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

// We need to mock idb before importing the module under test,
// since offlineStore uses a module-level cache for indexedDBAvailable.
// The approach: mock the `idb` module and also ensure `indexedDB` global exists.

const records: Map<number, Record<string, unknown>> = new Map();
let nextId = 1;

const mockDB = {
  add: vi.fn((_storeName: string, record: Record<string, unknown>) => {
    const id = nextId++;
    records.set(id, { ...record, id });
    return Promise.resolve(id);
  }),
  getAll: vi.fn((_storeName: string) => {
    return Promise.resolve(Array.from(records.values()));
  }),
  delete: vi.fn((_storeName: string, id: number) => {
    records.delete(id);
    return Promise.resolve();
  }),
};

vi.mock('idb', () => ({
  openDB: vi.fn(() => Promise.resolve(mockDB)),
}));

// Ensure indexedDB global is defined in test environment
// @ts-expect-error - setting global for test
globalThis.indexedDB = globalThis.indexedDB || {};

describe('offlineStore', () => {
  beforeEach(async () => {
    records.clear();
    nextId = 1;
    vi.resetModules();
  });

  it('savePendingTransaction saves with pending_sync flag and returns id', async () => {
    const { savePendingTransaction } = await import('./offlineStore');
    const payload = {
      amount_smallest_unit: 1500,
      direction: 'spent',
      currency_code: 'USD',
    };

    const id = await savePendingTransaction(payload);
    expect(id).toBe(1);
    expect(records.size).toBe(1);

    const saved = records.get(1)!;
    expect(saved.payload).toEqual(payload);
    expect(saved.pending_sync).toBe(true);
    expect(saved.created_at).toBeDefined();
  });

  it('savePendingTransaction assigns auto-incrementing ids', async () => {
    const { savePendingTransaction } = await import('./offlineStore');

    const id1 = await savePendingTransaction({ amount: 100 });
    const id2 = await savePendingTransaction({ amount: 200 });
    expect(id1).toBe(1);
    expect(id2).toBe(2);
  });

  it('getPendingTransactions returns only pending_sync transactions', async () => {
    const { savePendingTransaction, getPendingTransactions } = await import('./offlineStore');

    await savePendingTransaction({ amount: 100 });
    await savePendingTransaction({ amount: 200 });

    const pending = await getPendingTransactions();
    expect(pending.length).toBe(2);
    expect(pending[0].pending_sync).toBe(true);
    expect(pending[1].pending_sync).toBe(true);
  });

  it('getPendingTransactions returns empty array when no pending', async () => {
    const { getPendingTransactions } = await import('./offlineStore');

    const pending = await getPendingTransactions();
    expect(pending.length).toBe(0);
  });

  it('deletePendingTransaction removes a transaction by id', async () => {
    const { savePendingTransaction, deletePendingTransaction } = await import('./offlineStore');

    await savePendingTransaction({ amount: 100 });
    await savePendingTransaction({ amount: 200 });

    await deletePendingTransaction(1);
    expect(records.size).toBe(1);
    expect(records.has(1)).toBe(false);
    expect(records.has(2)).toBe(true);
  });

  it('getPendingCount returns correct count', async () => {
    const { savePendingTransaction, getPendingCount } = await import('./offlineStore');

    await savePendingTransaction({ amount: 100 });
    await savePendingTransaction({ amount: 200 });
    await savePendingTransaction({ amount: 300 });

    const count = await getPendingCount();
    expect(count).toBe(3);
  });

  it('getPendingCount returns 0 when no pending', async () => {
    const { getPendingCount } = await import('./offlineStore');
    const count = await getPendingCount();
    expect(count).toBe(0);
  });

  it('getStaleTransactions returns transactions older than specified hours', async () => {
    const { getStaleTransactions } = await import('./offlineStore');

    // Manually insert a stale record
    records.set(1, {
      id: 1,
      payload: { amount: 100 },
      created_at: new Date(Date.now() - 25 * 60 * 60 * 1000).toISOString(),
      pending_sync: true,
    });
    // And a fresh record
    records.set(2, {
      id: 2,
      payload: { amount: 200 },
      created_at: new Date().toISOString(),
      pending_sync: true,
    });
    nextId = 3;

    const stale = await getStaleTransactions(24);
    expect(stale.length).toBe(1);
    expect(stale[0].id).toBe(1);
  });

  it('getStaleTransactions returns empty when no stale transactions', async () => {
    const { savePendingTransaction, getStaleTransactions } = await import('./offlineStore');
    await savePendingTransaction({ amount: 100 });

    const stale = await getStaleTransactions(24);
    expect(stale.length).toBe(0);
  });

  it('isIndexedDBAvailable returns true when indexedDB exists', async () => {
    const { isIndexedDBAvailable } = await import('./offlineStore');
    expect(isIndexedDBAvailable()).toBe(true);
  });
});

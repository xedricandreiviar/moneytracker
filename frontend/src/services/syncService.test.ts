/**
 * Unit tests for syncService.
 * Tests online detection, background sync registration, and sync logic.
 * Requirements: 13.1, 13.2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { isOnline, registerBackgroundSync, syncPendingTransactions } from './syncService';

// Mock offlineStore
vi.mock('./offlineStore', () => ({
  getPendingTransactions: vi.fn(() => Promise.resolve([])),
  deletePendingTransaction: vi.fn(() => Promise.resolve()),
  getStaleTransactions: vi.fn(() => Promise.resolve([])),
}));

// Mock axios
vi.mock('axios', () => ({
  default: {
    post: vi.fn(() => Promise.resolve({ status: 200, data: {} })),
    isAxiosError: vi.fn(() => false),
  },
}));

import * as offlineStore from './offlineStore';
import axios from 'axios';

describe('syncService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('isOnline', () => {
    it('returns navigator.onLine value', () => {
      Object.defineProperty(navigator, 'onLine', { value: true, writable: true });
      expect(isOnline()).toBe(true);

      Object.defineProperty(navigator, 'onLine', { value: false, writable: true });
      expect(isOnline()).toBe(false);

      // Reset
      Object.defineProperty(navigator, 'onLine', { value: true, writable: true });
    });
  });

  describe('registerBackgroundSync', () => {
    it('returns false when serviceWorker is not available', async () => {
      const originalSW = navigator.serviceWorker;
      Object.defineProperty(navigator, 'serviceWorker', { value: undefined, writable: true });

      const result = await registerBackgroundSync();
      expect(result).toBe(false);

      Object.defineProperty(navigator, 'serviceWorker', { value: originalSW, writable: true });
    });

    it('returns true when background sync registers successfully', async () => {
      const mockSync = { register: vi.fn(() => Promise.resolve()) };
      const mockRegistration = { sync: mockSync };

      Object.defineProperty(navigator, 'serviceWorker', {
        value: { ready: Promise.resolve(mockRegistration) },
        writable: true,
      });

      const result = await registerBackgroundSync();
      expect(result).toBe(true);
      expect(mockSync.register).toHaveBeenCalledWith('sync-transactions');
    });
  });

  describe('syncPendingTransactions', () => {
    it('returns 0 when no pending transactions', async () => {
      vi.mocked(offlineStore.getPendingTransactions).mockResolvedValue([]);

      const count = await syncPendingTransactions();
      expect(count).toBe(0);
    });

    it('syncs pending transactions and deletes on success', async () => {
      vi.mocked(offlineStore.getPendingTransactions).mockResolvedValue([
        {
          id: 1,
          payload: { amount_smallest_unit: 1500, direction: 'spent', currency_code: 'USD' },
          created_at: new Date().toISOString(),
          pending_sync: true,
        },
        {
          id: 2,
          payload: { amount_smallest_unit: 2000, direction: 'received', currency_code: 'USD' },
          created_at: new Date().toISOString(),
          pending_sync: true,
        },
      ]);

      vi.mocked(axios.post).mockResolvedValue({ status: 200, data: {} });

      const count = await syncPendingTransactions();
      expect(count).toBe(2);
      expect(offlineStore.deletePendingTransaction).toHaveBeenCalledWith(1);
      expect(offlineStore.deletePendingTransaction).toHaveBeenCalledWith(2);
    });

    it('leaves transactions in place on 5xx errors', async () => {
      vi.mocked(offlineStore.getPendingTransactions).mockResolvedValue([
        {
          id: 1,
          payload: { amount_smallest_unit: 1500, direction: 'spent', currency_code: 'USD' },
          created_at: new Date().toISOString(),
          pending_sync: true,
        },
      ]);

      // Simulate server error
      const serverError = {
        response: { status: 500, data: {} },
        isAxiosError: true,
      };
      vi.mocked(axios.post).mockRejectedValue(serverError);
      vi.mocked((axios as unknown as { isAxiosError: (e: unknown) => boolean }).isAxiosError).mockReturnValue(true);

      const count = await syncPendingTransactions();
      expect(count).toBe(0);
      expect(offlineStore.deletePendingTransaction).not.toHaveBeenCalled();
    });

    it('removes transactions on 4xx errors (invalid data)', async () => {
      vi.mocked(offlineStore.getPendingTransactions).mockResolvedValue([
        {
          id: 1,
          payload: { amount_smallest_unit: -100, direction: 'spent', currency_code: 'USD' },
          created_at: new Date().toISOString(),
          pending_sync: true,
        },
      ]);

      // Simulate client validation error
      const clientError = {
        response: { status: 422, data: { detail: 'Invalid amount' } },
        isAxiosError: true,
      };
      vi.mocked(axios.post).mockRejectedValue(clientError);
      vi.mocked((axios as unknown as { isAxiosError: (e: unknown) => boolean }).isAxiosError).mockReturnValue(true);

      const count = await syncPendingTransactions();
      expect(count).toBe(0);
      expect(offlineStore.deletePendingTransaction).toHaveBeenCalledWith(1);
    });
  });
});

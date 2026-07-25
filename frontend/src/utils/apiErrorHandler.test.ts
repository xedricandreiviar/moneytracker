import { describe, it, expect } from 'vitest';
import { handleApiError } from './apiErrorHandler';
import axios, { AxiosError, AxiosHeaders } from 'axios';

function makeAxiosError(status: number, data?: unknown): AxiosError {
  const error = new AxiosError(
    'Request failed',
    'ERR_BAD_REQUEST',
    undefined,
    undefined,
    {
      status,
      statusText: status >= 500 ? 'Internal Server Error' : 'Bad Request',
      data: data || {},
      headers: {},
      config: { headers: new AxiosHeaders() },
    },
  );
  return error;
}

describe('handleApiError', () => {
  it('extracts field-level errors from 422 response with detail array', () => {
    const error = makeAxiosError(422, {
      detail: [
        { field: 'amount', message: 'Amount must be positive' },
        { field: 'note', message: 'Note too long' },
      ],
    });

    const result = handleApiError(error);

    expect(result.fieldErrors).toHaveLength(2);
    expect(result.fieldErrors[0]).toEqual({ field: 'amount', message: 'Amount must be positive' });
    expect(result.generalError).toBeNull();
    expect(result.retryable).toBe(false);
  });

  it('returns general error for 4xx with string detail', () => {
    const error = makeAxiosError(409, { detail: 'A budget already exists for this category' });

    const result = handleApiError(error);

    expect(result.fieldErrors).toHaveLength(0);
    expect(result.generalError).toBe('A budget already exists for this category');
    expect(result.retryable).toBe(false);
  });

  it('returns generic retryable error for 500', () => {
    const error = makeAxiosError(500, {});

    const result = handleApiError(error);

    expect(result.fieldErrors).toHaveLength(0);
    expect(result.generalError).toBe('Something went wrong. Please try again.');
    expect(result.retryable).toBe(true);
  });

  it('returns generic retryable error for 503', () => {
    const error = makeAxiosError(503, {});

    const result = handleApiError(error);

    expect(result.retryable).toBe(true);
    expect(result.generalError).toBe('Something went wrong. Please try again.');
  });

  it('returns network error for axios error with no response', () => {
    const error = new AxiosError('Network Error', 'ERR_NETWORK');

    const result = handleApiError(error);

    expect(result.generalError).toBe('Network error. Please check your connection and try again.');
    expect(result.retryable).toBe(true);
  });

  it('returns unexpected error for non-axios errors', () => {
    const error = new TypeError('Cannot read property of undefined');

    const result = handleApiError(error);

    expect(result.generalError).toBe('An unexpected error occurred. Please try again.');
    expect(result.retryable).toBe(true);
  });

  it('handles 400 with no detail', () => {
    const error = makeAxiosError(400, { message: 'Bad request' });

    const result = handleApiError(error);

    expect(result.fieldErrors).toHaveLength(0);
    expect(result.generalError).toBe('Bad request');
    expect(result.retryable).toBe(false);
  });
});

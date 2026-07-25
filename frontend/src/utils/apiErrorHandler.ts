/**
 * Consistent API error handling utilities.
 * - 4xx responses: extract field-level validation errors
 * - 5xx responses: return a generic error with retry indication
 * Requirements: 13.2, 14.10
 */
import axios from 'axios';

export interface FieldError {
  field: string;
  message: string;
}

export interface ApiErrorResult {
  /** Field-level validation errors (from 4xx responses) */
  fieldErrors: FieldError[];
  /** Generic error message for display as toast/banner (from 5xx or network errors) */
  generalError: string | null;
  /** Whether a retry is appropriate (true for 5xx and network errors) */
  retryable: boolean;
}

/**
 * Processes an API error into a structured result for UI display.
 * 
 * - 4xx (e.g. 422): Extracts field-level errors from response `detail` array
 * - 5xx: Returns a generic "something went wrong" message with retryable flag
 * - Network errors: Returns a connectivity error message with retryable flag
 */
export function handleApiError(error: unknown): ApiErrorResult {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;

    // 4xx — validation/client errors: extract field-level details
    if (status && status >= 400 && status < 500) {
      const detail = error.response?.data?.detail;

      if (Array.isArray(detail)) {
        return {
          fieldErrors: detail as FieldError[],
          generalError: null,
          retryable: false,
        };
      }

      // Single message format
      const message =
        typeof detail === 'string'
          ? detail
          : error.response?.data?.message || 'Validation failed. Please check your input.';

      return {
        fieldErrors: [],
        generalError: message,
        retryable: false,
      };
    }

    // 5xx — server errors: generic toast with retry
    if (status && status >= 500) {
      return {
        fieldErrors: [],
        generalError: 'Something went wrong. Please try again.',
        retryable: true,
      };
    }

    // No response (network issue)
    return {
      fieldErrors: [],
      generalError: 'Network error. Please check your connection and try again.',
      retryable: true,
    };
  }

  // Non-axios error
  return {
    fieldErrors: [],
    generalError: 'An unexpected error occurred. Please try again.',
    retryable: true,
  };
}

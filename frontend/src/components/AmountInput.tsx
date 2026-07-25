import { useState, useCallback } from "react";
import type { ChangeEvent } from "react";
import type { LocaleConfig } from "../types/locale";
import { isValidAmountInput } from "../utils/locale";

export interface AmountInputProps {
  /** Locale configuration for currency formatting */
  locale: LocaleConfig;
  /** Current input value (display string, not smallest unit) */
  value: string;
  /** Called when the input value changes with the raw display string */
  onChange: (value: string) => void;
  /** Optional error message to display */
  error?: string;
  /** Optional placeholder text */
  placeholder?: string;
  /** Whether the input is disabled */
  disabled?: boolean;
}

/**
 * AmountInput component with locale-aware currency formatting.
 *
 * Features:
 * - Shows currency symbol as prefix or suffix per locale convention
 * - Enforces decimal precision (blocks extra decimal places)
 * - Validates positive numeric input in real-time
 * - Displays error state when invalid input is detected
 */
export function AmountInput({
  locale,
  value,
  onChange,
  error,
  placeholder,
  disabled = false,
}: AmountInputProps) {
  const [touched, setTouched] = useState(false);

  const isSymbolSuffix = locale.decimal_separator === ",";

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const rawValue = e.target.value;

      // Allow empty input
      if (rawValue === "") {
        onChange("");
        return;
      }

      // Allow only valid characters for the locale
      const allowedChars = buildAllowedPattern(locale);
      if (!allowedChars.test(rawValue)) {
        return; // Block invalid characters
      }

      // Enforce decimal precision: block extra decimal places
      if (!isWithinDecimalPrecision(rawValue, locale)) {
        return; // Block input that exceeds decimal precision
      }

      onChange(rawValue);
    },
    [locale, onChange]
  );

  const handleBlur = useCallback(() => {
    setTouched(true);
  }, []);

  // Determine validation state
  const showError = touched && value !== "" && !isValidAmountInput(value, locale);
  const displayError = error || (showError ? getValidationMessage(locale) : undefined);

  return (
    <div className="amount-input-container">
      <div
        className={`amount-input-wrapper ${displayError ? "amount-input-error" : ""}`}
      >
        {!isSymbolSuffix && (
          <span className="amount-input-symbol amount-input-symbol--prefix">
            {locale.symbol}
          </span>
        )}
        <input
          type="text"
          inputMode="decimal"
          className="amount-input-field"
          value={value}
          onChange={handleChange}
          onBlur={handleBlur}
          placeholder={placeholder || getPlaceholder(locale)}
          disabled={disabled}
          aria-label="Amount"
          aria-invalid={!!displayError}
          aria-describedby={displayError ? "amount-input-error-msg" : undefined}
        />
        {isSymbolSuffix && (
          <span className="amount-input-symbol amount-input-symbol--suffix">
            {locale.symbol}
          </span>
        )}
      </div>
      {displayError && (
        <p id="amount-input-error-msg" className="amount-input-error-message" role="alert">
          {displayError}
        </p>
      )}
    </div>
  );
}

// --- Internal helpers ---

/**
 * Builds a regex pattern for characters allowed in amount input.
 */
function buildAllowedPattern(locale: LocaleConfig): RegExp {
  const { decimal_separator, thousands_separator } = locale;

  let pattern = "^[0-9";

  if (decimal_separator) {
    pattern += escapeRegex(decimal_separator);
  }
  if (thousands_separator) {
    pattern += escapeRegex(thousands_separator);
  }

  // Allow space for French-style thousands separator
  if (thousands_separator === " ") {
    pattern += "\\s";
  }

  pattern += "]+$";

  return new RegExp(pattern);
}

/**
 * Checks if the input doesn't exceed the allowed decimal precision.
 */
function isWithinDecimalPrecision(input: string, locale: LocaleConfig): boolean {
  const { decimal_precision, decimal_separator } = locale;

  // Zero-precision currencies should not have a decimal separator
  if (decimal_precision === 0) {
    if (decimal_separator && input.includes(decimal_separator)) {
      return false;
    }
    // Also block period for zero-precision
    if (input.includes(".")) {
      return false;
    }
    return true;
  }

  if (!decimal_separator) return true;

  const separatorIndex = input.indexOf(decimal_separator);
  if (separatorIndex === -1) return true;

  // Only allow one decimal separator
  if (input.indexOf(decimal_separator, separatorIndex + 1) !== -1) {
    return false;
  }

  const decimalPart = input.slice(separatorIndex + 1);
  return decimalPart.length <= decimal_precision;
}

function getPlaceholder(locale: LocaleConfig): string {
  if (locale.decimal_precision === 0) {
    return "0";
  }
  const zeros = "0".repeat(locale.decimal_precision);
  return `0${locale.decimal_separator}${zeros}`;
}

function getValidationMessage(locale: LocaleConfig): string {
  if (locale.decimal_precision === 0) {
    return "Enter a positive whole number";
  }
  return `Enter a positive number with up to ${locale.decimal_precision} decimal places`;
}

function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

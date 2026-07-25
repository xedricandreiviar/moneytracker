import type { LocaleConfig } from "../types/locale";
import { LOCALE_CONFIGS } from "../types/locale";
import { formatAmount } from "../utils/locale";

export interface CurrencyDisplayProps {
  /** Amount in smallest currency unit (e.g., cents for USD, yen for JPY) */
  amount: number;
  /** ISO 4217 currency code (e.g., "USD", "GBP", "JPY") */
  currencyCode: string;
  /** Optional locale override. If not provided, resolves from currencyCode. */
  locale?: LocaleConfig;
  /** Optional CSS class name */
  className?: string;
}

/**
 * CurrencyDisplay component that formats an integer amount (in smallest currency unit)
 * into a locale-formatted display string.
 *
 * Uses the currency code to determine the correct locale settings for formatting,
 * including symbol, separators, and decimal places.
 *
 * This is important for displaying historical transactions that may have been
 * recorded in a different currency than the user's current locale.
 */
export function CurrencyDisplay({
  amount,
  currencyCode,
  locale,
  className,
}: CurrencyDisplayProps) {
  const resolvedLocale = locale || resolveLocaleForCurrency(currencyCode);
  const formatted = formatAmount(amount, resolvedLocale);

  return (
    <span className={`currency-display ${className || ""}`} aria-label={`${formatted}`}>
      {formatted}
    </span>
  );
}

/**
 * Resolves the locale configuration for a given currency code.
 * Searches through known locale configs to find a match.
 * Falls back to a basic USD-like config if the currency is not found.
 */
function resolveLocaleForCurrency(currencyCode: string): LocaleConfig {
  // Search through known configs for a matching currency code
  for (const config of Object.values(LOCALE_CONFIGS)) {
    if (config.currency_code === currencyCode) {
      return config;
    }
  }

  // Fallback: use basic formatting for unknown currencies
  return {
    currency_code: currencyCode,
    symbol: currencyCode,
    decimal_precision: 2,
    decimal_separator: ".",
    thousands_separator: ",",
    date_format: "YYYY-MM-DD",
    week_start_day: 1,
  };
}

/**
 * Locale configuration interface matching the backend's structure.
 * Defines currency formatting, date formatting, and week start preferences
 * based on the user's selected country.
 */
export interface LocaleConfig {
  /** ISO 4217 currency code (e.g., "USD", "GBP", "JPY") */
  currency_code: string;
  /** Currency symbol (e.g., "$", "£", "¥") */
  symbol: string;
  /** Number of decimal places: 0 (JPY), 2 (USD/EUR), or 3 (KWD) */
  decimal_precision: number;
  /** Character used as decimal separator ("." or ",") */
  decimal_separator: string;
  /** Character used as thousands separator ("," or "." or " ") */
  thousands_separator: string;
  /** Date format pattern (e.g., "MM/DD/YYYY", "DD/MM/YYYY", "YYYY/MM/DD") */
  date_format: string;
  /** Day the week starts on: 0=Sunday, 1=Monday, ..., 6=Saturday */
  week_start_day: number;
}

/**
 * Predefined locale configurations for supported countries.
 */
export const LOCALE_CONFIGS: Record<string, LocaleConfig> = {
  US: {
    currency_code: "USD",
    symbol: "$",
    decimal_precision: 2,
    decimal_separator: ".",
    thousands_separator: ",",
    date_format: "MM/DD/YYYY",
    week_start_day: 0,
  },
  GB: {
    currency_code: "GBP",
    symbol: "£",
    decimal_precision: 2,
    decimal_separator: ".",
    thousands_separator: ",",
    date_format: "DD/MM/YYYY",
    week_start_day: 1,
  },
  JP: {
    currency_code: "JPY",
    symbol: "¥",
    decimal_precision: 0,
    decimal_separator: "",
    thousands_separator: ",",
    date_format: "YYYY/MM/DD",
    week_start_day: 1,
  },
  IN: {
    currency_code: "INR",
    symbol: "₹",
    decimal_precision: 2,
    decimal_separator: ".",
    thousands_separator: ",",
    date_format: "DD/MM/YYYY",
    week_start_day: 1,
  },
  DE: {
    currency_code: "EUR",
    symbol: "€",
    decimal_precision: 2,
    decimal_separator: ",",
    thousands_separator: ".",
    date_format: "DD.MM.YYYY",
    week_start_day: 1,
  },
  FR: {
    currency_code: "EUR",
    symbol: "€",
    decimal_precision: 2,
    decimal_separator: ",",
    thousands_separator: " ",
    date_format: "DD/MM/YYYY",
    week_start_day: 1,
  },
  BR: {
    currency_code: "BRL",
    symbol: "R$",
    decimal_precision: 2,
    decimal_separator: ",",
    thousands_separator: ".",
    date_format: "DD/MM/YYYY",
    week_start_day: 0,
  },
  AU: {
    currency_code: "AUD",
    symbol: "$",
    decimal_precision: 2,
    decimal_separator: ".",
    thousands_separator: ",",
    date_format: "DD/MM/YYYY",
    week_start_day: 1,
  },
  CA: {
    currency_code: "CAD",
    symbol: "$",
    decimal_precision: 2,
    decimal_separator: ".",
    thousands_separator: ",",
    date_format: "YYYY-MM-DD",
    week_start_day: 0,
  },
  KR: {
    currency_code: "KRW",
    symbol: "₩",
    decimal_precision: 0,
    decimal_separator: "",
    thousands_separator: ",",
    date_format: "YYYY.MM.DD",
    week_start_day: 1,
  },
};

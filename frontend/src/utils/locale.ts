import type { LocaleConfig } from "../types/locale";

/**
 * Formats an integer amount (in smallest currency unit) into a locale-formatted
 * display string with the currency symbol.
 *
 * Examples:
 * - formatAmount(1050, USD locale) → "$10.50"
 * - formatAmount(1050, JPY locale) → "¥1,050"
 * - formatAmount(123456, EUR/DE locale) → "1.234,56 €"
 */
export function formatAmount(
  amountSmallestUnit: number,
  locale: LocaleConfig
): string {
  const { symbol, decimal_precision, decimal_separator, thousands_separator } =
    locale;

  // Convert from smallest unit to major unit
  const divisor = Math.pow(10, decimal_precision);
  const majorAmount = amountSmallestUnit / divisor;

  // Split into integer and decimal parts
  const absoluteAmount = Math.abs(majorAmount);
  const integerPart = Math.floor(absoluteAmount);
  const decimalPart = Math.round(
    (absoluteAmount - integerPart) * Math.pow(10, decimal_precision)
  );

  // Format integer part with thousands separators
  const integerStr = formatWithThousandsSeparator(
    integerPart,
    thousands_separator
  );

  // Build the number string
  let numberStr: string;
  if (decimal_precision === 0) {
    numberStr = integerStr;
  } else {
    const decimalStr = decimalPart
      .toString()
      .padStart(decimal_precision, "0");
    numberStr = `${integerStr}${decimal_separator}${decimalStr}`;
  }

  // Add negative sign if needed
  if (amountSmallestUnit < 0) {
    numberStr = `-${numberStr}`;
  }

  // Apply symbol placement based on locale convention
  return applySymbol(numberStr, symbol, locale);
}

/**
 * Parses a user-entered amount string into the smallest currency unit integer.
 * Handles locale-specific separators.
 *
 * Examples:
 * - parseAmountInput("10.50", USD locale) → 1050
 * - parseAmountInput("1,050", JPY locale) → 1050
 * - parseAmountInput("1.234,56", EUR/DE locale) → 123456
 *
 * Returns null if the input is invalid (non-numeric, negative, or has too many decimals).
 */
export function parseAmountInput(
  input: string,
  locale: LocaleConfig
): number | null {
  const { decimal_precision, decimal_separator, thousands_separator } = locale;

  // Trim whitespace
  const trimmed = input.trim();
  if (trimmed === "") return null;

  // Remove currency symbols and whitespace that might be in the input
  let cleaned = trimmed.replace(/[^0-9.,\s-]/g, "").trim();
  if (cleaned === "") return null;

  // Reject negative values
  if (cleaned.startsWith("-")) return null;

  // Remove thousands separators
  if (thousands_separator) {
    // For zero-precision currencies, validate that thousands separators are
    // in valid positions (every 3 digits from the right). Otherwise, a comma
    // in "10,5" for JPY could be misinterpreted as a thousands separator.
    if (decimal_precision === 0) {
      const parts = cleaned.split(thousands_separator);
      // First part can be 1-3 digits, subsequent parts must be exactly 3 digits
      if (parts.length > 1) {
        for (let i = 1; i < parts.length; i++) {
          if (parts[i].length !== 3) return null;
        }
      }
    }
    cleaned = cleaned.split(thousands_separator).join("");
  }

  // Normalize decimal separator to "."
  if (decimal_separator && decimal_separator !== ".") {
    cleaned = cleaned.replace(decimal_separator, ".");
  }

  // Validate the cleaned string is a valid number
  if (!/^\d+(\.\d+)?$/.test(cleaned)) return null;

  const parts = cleaned.split(".");
  const decimalPart = parts[1] || "";

  // Check decimal precision
  if (decimalPart.length > decimal_precision) return null;

  // For zero-precision currencies, reject any decimal input
  if (decimal_precision === 0 && parts.length > 1) return null;

  // Parse and convert to smallest unit
  const numericValue = parseFloat(cleaned);
  if (numericValue <= 0) return null;
  if (!isFinite(numericValue)) return null;

  // Convert to smallest unit
  const smallestUnit = Math.round(
    numericValue * Math.pow(10, decimal_precision)
  );

  // Guard against unreasonably large values
  if (smallestUnit > Number.MAX_SAFE_INTEGER) return null;

  return smallestUnit;
}

/**
 * Formats a Date object according to the locale's date format pattern.
 *
 * Supports patterns: "MM/DD/YYYY", "DD/MM/YYYY", "YYYY/MM/DD",
 * "DD.MM.YYYY", "YYYY-MM-DD", "YYYY.MM.DD"
 */
export function formatDate(date: Date, locale: LocaleConfig): string {
  const day = date.getDate().toString().padStart(2, "0");
  const month = (date.getMonth() + 1).toString().padStart(2, "0");
  const year = date.getFullYear().toString();

  return locale.date_format
    .replace("DD", day)
    .replace("MM", month)
    .replace("YYYY", year);
}

/**
 * Calculates the start and end dates of the week containing the given date,
 * based on the locale's configured week start day.
 *
 * Returns a tuple [weekStart, weekEnd] where both are Date objects
 * representing the start (00:00) and end (23:59:59) of the week boundaries.
 * The end date is exactly 6 days after the start date.
 */
export function getWeekBoundaries(
  date: Date,
  locale: LocaleConfig
): [Date, Date] {
  const { week_start_day } = locale;

  // Get the day of week (0=Sunday, 6=Saturday)
  const currentDayOfWeek = date.getDay();

  // Calculate days since the week start
  let daysSinceStart = currentDayOfWeek - week_start_day;
  if (daysSinceStart < 0) {
    daysSinceStart += 7;
  }

  // Calculate week start
  const weekStart = new Date(date);
  weekStart.setDate(date.getDate() - daysSinceStart);
  weekStart.setHours(0, 0, 0, 0);

  // Calculate week end (6 days after start)
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekStart.getDate() + 6);
  weekEnd.setHours(23, 59, 59, 999);

  return [weekStart, weekEnd];
}

/**
 * Validates whether an input string represents a valid amount for the given locale.
 * Returns true if the input is a positive number with correct decimal precision.
 */
export function isValidAmountInput(
  input: string,
  locale: LocaleConfig
): boolean {
  return parseAmountInput(input, locale) !== null;
}

// --- Internal helpers ---

function formatWithThousandsSeparator(
  value: number,
  separator: string
): string {
  if (!separator) return value.toString();

  const str = value.toString();
  const parts: string[] = [];

  for (let i = str.length; i > 0; i -= 3) {
    const start = Math.max(0, i - 3);
    parts.unshift(str.slice(start, i));
  }

  return parts.join(separator);
}

function applySymbol(
  numberStr: string,
  symbol: string,
  locale: LocaleConfig
): string {
  // Simple heuristic: if decimal separator is comma, symbol goes after (suffix)
  // This covers EUR locales (DE, FR) and BRL
  if (locale.decimal_separator === ",") {
    return `${numberStr} ${symbol}`;
  }

  return `${symbol}${numberStr}`;
}

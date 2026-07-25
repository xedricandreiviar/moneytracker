"""LocaleService for country-driven currency, date, and week configuration.

Provides locale configuration lookup, amount formatting/parsing,
week boundary calculation, and amount validation.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Tuple


@dataclass(frozen=True)
class LocaleConfig:
    """Immutable locale configuration for a supported country."""

    currency_code: str
    symbol: str
    decimal_precision: int
    decimal_separator: str
    thousands_separator: str
    date_format: str
    week_start_day: int  # 0 = Sunday, 1 = Monday, ..., 6 = Saturday


# Static configuration mapping country codes to locale settings
LOCALE_CONFIGS: dict[str, LocaleConfig] = {
    "US": LocaleConfig(
        currency_code="USD",
        symbol="$",
        decimal_precision=2,
        decimal_separator=".",
        thousands_separator=",",
        date_format="MM/DD/YYYY",
        week_start_day=0,  # Sunday
    ),
    "GB": LocaleConfig(
        currency_code="GBP",
        symbol="£",
        decimal_precision=2,
        decimal_separator=".",
        thousands_separator=",",
        date_format="DD/MM/YYYY",
        week_start_day=1,  # Monday
    ),
    "JP": LocaleConfig(
        currency_code="JPY",
        symbol="¥",
        decimal_precision=0,
        decimal_separator="",
        thousands_separator=",",
        date_format="YYYY/MM/DD",
        week_start_day=1,  # Monday
    ),
    "IN": LocaleConfig(
        currency_code="INR",
        symbol="₹",
        decimal_precision=2,
        decimal_separator=".",
        thousands_separator=",",
        date_format="DD/MM/YYYY",
        week_start_day=1,  # Monday
    ),
    "DE": LocaleConfig(
        currency_code="EUR",
        symbol="€",
        decimal_precision=2,
        decimal_separator=",",
        thousands_separator=".",
        date_format="DD.MM.YYYY",
        week_start_day=1,  # Monday
    ),
    "FR": LocaleConfig(
        currency_code="EUR",
        symbol="€",
        decimal_precision=2,
        decimal_separator=",",
        thousands_separator=" ",
        date_format="DD/MM/YYYY",
        week_start_day=1,  # Monday
    ),
    "BR": LocaleConfig(
        currency_code="BRL",
        symbol="R$",
        decimal_precision=2,
        decimal_separator=",",
        thousands_separator=".",
        date_format="DD/MM/YYYY",
        week_start_day=0,  # Sunday
    ),
    "AU": LocaleConfig(
        currency_code="AUD",
        symbol="$",
        decimal_precision=2,
        decimal_separator=".",
        thousands_separator=",",
        date_format="DD/MM/YYYY",
        week_start_day=1,  # Monday
    ),
    "CA": LocaleConfig(
        currency_code="CAD",
        symbol="$",
        decimal_precision=2,
        decimal_separator=".",
        thousands_separator=",",
        date_format="YYYY-MM-DD",
        week_start_day=0,  # Sunday
    ),
    "KR": LocaleConfig(
        currency_code="KRW",
        symbol="₩",
        decimal_precision=0,
        decimal_separator="",
        thousands_separator=",",
        date_format="YYYY.MM.DD",
        week_start_day=1,  # Monday
    ),
    "PH": LocaleConfig(
        currency_code="PHP",
        symbol="₱",
        decimal_precision=2,
        decimal_separator=".",
        thousands_separator=",",
        date_format="MM/DD/YYYY",
        week_start_day=0,  # Sunday
    ),
}


def _format_with_thousands(number: int, separator: str) -> str:
    """Format an integer with thousands separators.

    Args:
        number: A non-negative integer to format.
        separator: The character to use as thousands separator.

    Returns:
        The formatted string (e.g., 1234567 with "," → "1,234,567").
    """
    if not separator:
        return str(number)

    s = str(number)
    # Insert separator every 3 digits from the right
    groups = []
    while s:
        groups.append(s[-3:])
        s = s[:-3]
    groups.reverse()
    return separator.join(groups)


def get_locale_config(country_code: str) -> LocaleConfig:
    """Look up the complete locale configuration for a country code.

    Args:
        country_code: Two-letter ISO country code (e.g., "US", "JP").

    Returns:
        The LocaleConfig for the given country.

    Raises:
        ValueError: If the country code is not supported.
    """
    code = country_code.upper()
    if code not in LOCALE_CONFIGS:
        supported = sorted(LOCALE_CONFIGS.keys())
        raise ValueError(
            f"Unsupported country code: '{country_code}'. "
            f"Supported countries: {', '.join(supported)}"
        )
    return LOCALE_CONFIGS[code]


def format_amount(amount_smallest_unit: int, locale: LocaleConfig) -> str:
    """Format an integer amount (smallest currency unit) into a display string.

    Converts the integer to a decimal value based on the locale's decimal_precision,
    applies thousands separators, decimal separator, and prepends/appends the symbol.

    Args:
        amount_smallest_unit: The amount as an integer in smallest currency unit
                             (e.g., 1050 for $10.50 in USD, 1050 for ¥1050 in JPY).
        locale: The LocaleConfig to use for formatting.

    Returns:
        A formatted display string (e.g., "$1,050.00", "¥1,050", "€1.050,00").
    """
    precision = locale.decimal_precision

    if precision == 0:
        # No decimal places — the integer IS the amount
        whole_part = abs(amount_smallest_unit)
    else:
        # Convert from smallest unit to major unit
        divisor = 10**precision
        whole_part = abs(amount_smallest_unit) // divisor
        fractional_part = abs(amount_smallest_unit) % divisor

    # Format the whole part with thousands separators
    whole_str = _format_with_thousands(whole_part, locale.thousands_separator)

    # Build the number string
    if precision == 0:
        number_str = whole_str
    else:
        frac_str = str(fractional_part).zfill(precision)
        number_str = f"{whole_str}{locale.decimal_separator}{frac_str}"

    # Prepend negative sign if needed
    sign = "-" if amount_smallest_unit < 0 else ""

    # Attach symbol (always prefix for simplicity, matching design examples)
    return f"{sign}{locale.symbol}{number_str}"


def parse_amount_input(input_str: str, locale: LocaleConfig) -> int:
    """Parse a locale-formatted amount string back to an integer in smallest currency unit.

    This is the inverse of format_amount. It strips the currency symbol, removes
    thousands separators, normalizes the decimal separator, and converts to the
    smallest unit integer.

    Args:
        input_str: The user-entered amount string (may include symbol, separators).
        locale: The LocaleConfig to use for parsing.

    Returns:
        The amount as an integer in the smallest currency unit.

    Raises:
        ValueError: If the input cannot be parsed as a valid amount.
    """
    if not input_str or not input_str.strip():
        raise ValueError("Amount input cannot be empty.")

    cleaned = input_str.strip()

    # Remove the currency symbol
    cleaned = cleaned.replace(locale.symbol, "").strip()

    # Handle negative sign
    negative = False
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:].strip()
    elif cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1].strip()

    # Remove thousands separators
    if locale.thousands_separator:
        cleaned = cleaned.replace(locale.thousands_separator, "")

    # Normalize decimal separator to "."
    if locale.decimal_precision > 0 and locale.decimal_separator:
        cleaned = cleaned.replace(locale.decimal_separator, ".")

    # Validate the remaining string is a valid number
    if not cleaned:
        raise ValueError("Amount input cannot be empty after stripping symbols.")

    try:
        value = float(cleaned)
    except ValueError:
        raise ValueError(f"Cannot parse '{input_str}' as a numeric amount.")

    if locale.decimal_precision == 0:
        # For zero-precision currencies, the number should be an integer
        if "." in cleaned:
            raise ValueError(
                f"Currency {locale.currency_code} does not support decimal places."
            )
        result = int(value)
    else:
        # Convert to smallest unit
        multiplier = 10**locale.decimal_precision
        result = round(value * multiplier)

    if negative:
        result = -result

    return result


def get_week_boundaries(d: date, locale: LocaleConfig) -> Tuple[date, date]:
    """Calculate the start and end dates of the week containing the given date.

    Uses the locale's week_start_day to determine week boundaries.

    Args:
        d: The date for which to find the week boundaries.
        locale: The LocaleConfig with week_start_day (0=Sunday, 1=Monday, ..., 6=Saturday).

    Returns:
        A tuple (week_start, week_end) where both are dates and
        week_end - week_start == 6 days.
    """
    # Python's date.weekday(): Monday=0, Tuesday=1, ..., Sunday=6
    # Our week_start_day: Sunday=0, Monday=1, ..., Saturday=6
    # Convert our week_start_day to Python weekday
    # Our 0 (Sunday) = Python 6
    # Our 1 (Monday) = Python 0
    # Our 6 (Saturday) = Python 5
    python_week_start = (locale.week_start_day - 1) % 7  # Convert to Python weekday

    current_weekday = d.weekday()  # Python weekday (Monday=0 .. Sunday=6)

    # Calculate days since the start of the week
    days_since_start = (current_weekday - python_week_start) % 7

    week_start = d - timedelta(days=days_since_start)
    week_end = week_start + timedelta(days=6)

    return (week_start, week_end)


class AmountValidationError:
    """Describes why an amount validation failed."""

    def __init__(self, message: str):
        self.message = message

    def __repr__(self) -> str:
        return f"AmountValidationError({self.message!r})"


def validate_amount(
    input_str: str, locale: LocaleConfig
) -> Optional[AmountValidationError]:
    """Validate a user-entered amount string against locale currency rules.

    Checks that the input is:
    - Non-empty
    - Numeric (after removing symbol and separators)
    - Positive (greater than zero)
    - Has decimal places not exceeding the currency's decimal precision

    Args:
        input_str: The raw user input string for an amount.
        locale: The LocaleConfig for the user's currency.

    Returns:
        None if the amount is valid, or an AmountValidationError describing
        the validation failure.
    """
    if not input_str or not input_str.strip():
        return AmountValidationError("Amount cannot be empty.")

    cleaned = input_str.strip()

    # Remove currency symbol
    cleaned = cleaned.replace(locale.symbol, "").strip()

    # Remove negative indicators
    if cleaned.startswith("-"):
        return AmountValidationError("Amount must be positive.")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        return AmountValidationError("Amount must be positive.")

    # Remove thousands separators
    if locale.thousands_separator:
        cleaned = cleaned.replace(locale.thousands_separator, "")

    # Determine the decimal separator for checking precision
    dec_sep = locale.decimal_separator if locale.decimal_precision > 0 else ""

    # Check for non-numeric characters (allow digits, at most one decimal separator)
    if dec_sep:
        # Replace the locale decimal separator with "." for validation
        normalized = cleaned.replace(dec_sep, ".", 1)
    else:
        normalized = cleaned

    # Validate numeric format
    if not re.match(r"^\d+(\.\d+)?$", normalized):
        return AmountValidationError("Amount must be a valid positive number.")

    # Parse the numeric value
    try:
        value = float(normalized)
    except ValueError:
        return AmountValidationError("Amount must be a valid positive number.")

    # Check for zero
    if value <= 0:
        return AmountValidationError("Amount must be greater than zero.")

    # Check decimal precision
    if "." in normalized:
        decimal_digits = normalized.split(".")[1]
        if len(decimal_digits) > locale.decimal_precision:
            if locale.decimal_precision == 0:
                return AmountValidationError(
                    f"Currency {locale.currency_code} does not accept decimal places."
                )
            return AmountValidationError(
                f"Amount exceeds maximum of {locale.decimal_precision} decimal places "
                f"for {locale.currency_code}."
            )
    elif locale.decimal_precision == 0 and dec_sep and dec_sep in input_str:
        # Zero-precision currency but user used a decimal separator
        return AmountValidationError(
            f"Currency {locale.currency_code} does not accept decimal places."
        )

    return None

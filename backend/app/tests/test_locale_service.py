"""Unit tests for LocaleService."""

import pytest
from datetime import date

from app.services.locale_service import (
    LOCALE_CONFIGS,
    AmountValidationError,
    LocaleConfig,
    format_amount,
    get_locale_config,
    get_week_boundaries,
    parse_amount_input,
    validate_amount,
)


class TestGetLocaleConfig:
    """Tests for get_locale_config."""

    def test_returns_config_for_valid_country(self):
        config = get_locale_config("US")
        assert config.currency_code == "USD"
        assert config.symbol == "$"
        assert config.decimal_precision == 2

    def test_case_insensitive_lookup(self):
        config = get_locale_config("us")
        assert config.currency_code == "USD"

    def test_raises_for_unsupported_country(self):
        with pytest.raises(ValueError, match="Unsupported country code"):
            get_locale_config("ZZ")

    def test_all_supported_countries_have_complete_config(self):
        for code, config in LOCALE_CONFIGS.items():
            assert len(config.currency_code) == 3
            assert config.symbol
            assert config.decimal_precision in (0, 2, 3)
            assert config.date_format
            assert 0 <= config.week_start_day <= 6

    def test_minimum_supported_countries(self):
        required = {"US", "GB", "JP", "IN", "DE", "FR", "BR", "AU", "CA", "KR"}
        assert required.issubset(set(LOCALE_CONFIGS.keys()))


class TestFormatAmount:
    """Tests for format_amount."""

    def test_usd_basic(self):
        locale = get_locale_config("US")
        assert format_amount(1050, locale) == "$10.50"

    def test_usd_with_thousands(self):
        locale = get_locale_config("US")
        assert format_amount(123456, locale) == "$1,234.56"

    def test_jpy_no_decimals(self):
        locale = get_locale_config("JP")
        assert format_amount(1050, locale) == "¥1,050"

    def test_eur_german_format(self):
        locale = get_locale_config("DE")
        assert format_amount(123456, locale) == "€1.234,56"

    def test_brl_format(self):
        locale = get_locale_config("BR")
        assert format_amount(123456, locale) == "R$1.234,56"

    def test_zero_amount(self):
        locale = get_locale_config("US")
        assert format_amount(0, locale) == "$0.00"

    def test_negative_amount(self):
        locale = get_locale_config("US")
        assert format_amount(-1050, locale) == "-$10.50"

    def test_small_amount(self):
        locale = get_locale_config("US")
        assert format_amount(5, locale) == "$0.05"

    def test_krw_no_decimals(self):
        locale = get_locale_config("KR")
        assert format_amount(50000, locale) == "₩50,000"


class TestParseAmountInput:
    """Tests for parse_amount_input."""

    def test_usd_basic(self):
        locale = get_locale_config("US")
        assert parse_amount_input("$10.50", locale) == 1050

    def test_usd_without_symbol(self):
        locale = get_locale_config("US")
        assert parse_amount_input("10.50", locale) == 1050

    def test_usd_with_thousands(self):
        locale = get_locale_config("US")
        assert parse_amount_input("$1,234.56", locale) == 123456

    def test_jpy_basic(self):
        locale = get_locale_config("JP")
        assert parse_amount_input("¥1,050", locale) == 1050

    def test_eur_german_format(self):
        locale = get_locale_config("DE")
        assert parse_amount_input("€1.234,56", locale) == 123456

    def test_brl_format(self):
        locale = get_locale_config("BR")
        assert parse_amount_input("R$1.234,56", locale) == 123456

    def test_empty_raises(self):
        locale = get_locale_config("US")
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_amount_input("", locale)

    def test_non_numeric_raises(self):
        locale = get_locale_config("US")
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_amount_input("abc", locale)

    def test_jpy_rejects_decimals(self):
        locale = get_locale_config("JP")
        with pytest.raises(ValueError, match="does not support decimal"):
            parse_amount_input("100.50", locale)

    def test_round_trip_usd(self):
        locale = get_locale_config("US")
        original = 123456
        formatted = format_amount(original, locale)
        parsed = parse_amount_input(formatted, locale)
        assert parsed == original

    def test_round_trip_jpy(self):
        locale = get_locale_config("JP")
        original = 1050
        formatted = format_amount(original, locale)
        parsed = parse_amount_input(formatted, locale)
        assert parsed == original

    def test_round_trip_eur_de(self):
        locale = get_locale_config("DE")
        original = 123456
        formatted = format_amount(original, locale)
        parsed = parse_amount_input(formatted, locale)
        assert parsed == original


class TestGetWeekBoundaries:
    """Tests for get_week_boundaries."""

    def test_us_sunday_start(self):
        locale = get_locale_config("US")
        # 2024-01-10 is a Wednesday
        start, end = get_week_boundaries(date(2024, 1, 10), locale)
        assert start == date(2024, 1, 7)  # Sunday
        assert end == date(2024, 1, 13)  # Saturday
        assert start.weekday() == 6  # Sunday in Python weekday

    def test_gb_monday_start(self):
        locale = get_locale_config("GB")
        # 2024-01-10 is a Wednesday
        start, end = get_week_boundaries(date(2024, 1, 10), locale)
        assert start == date(2024, 1, 8)  # Monday
        assert end == date(2024, 1, 14)  # Sunday
        assert start.weekday() == 0  # Monday in Python weekday

    def test_date_on_week_start(self):
        locale = get_locale_config("US")
        # 2024-01-07 is a Sunday (US week start)
        start, end = get_week_boundaries(date(2024, 1, 7), locale)
        assert start == date(2024, 1, 7)
        assert end == date(2024, 1, 13)

    def test_date_on_week_end(self):
        locale = get_locale_config("US")
        # 2024-01-13 is a Saturday (US week end)
        start, end = get_week_boundaries(date(2024, 1, 13), locale)
        assert start == date(2024, 1, 7)
        assert end == date(2024, 1, 13)

    def test_week_span_is_always_6_days(self):
        locale = get_locale_config("GB")
        start, end = get_week_boundaries(date(2024, 3, 15), locale)
        assert (end - start).days == 6

    def test_date_within_boundaries(self):
        locale = get_locale_config("JP")
        d = date(2024, 6, 20)
        start, end = get_week_boundaries(d, locale)
        assert start <= d <= end


class TestValidateAmount:
    """Tests for validate_amount."""

    def test_valid_usd_amount(self):
        locale = get_locale_config("US")
        assert validate_amount("10.50", locale) is None

    def test_valid_jpy_amount(self):
        locale = get_locale_config("JP")
        assert validate_amount("1050", locale) is None

    def test_empty_string(self):
        locale = get_locale_config("US")
        result = validate_amount("", locale)
        assert result is not None
        assert "empty" in result.message.lower()

    def test_negative_amount(self):
        locale = get_locale_config("US")
        result = validate_amount("-10.50", locale)
        assert result is not None
        assert "positive" in result.message.lower()

    def test_zero_amount(self):
        locale = get_locale_config("US")
        result = validate_amount("0", locale)
        assert result is not None
        assert "greater than zero" in result.message.lower()

    def test_non_numeric(self):
        locale = get_locale_config("US")
        result = validate_amount("abc", locale)
        assert result is not None

    def test_excess_decimals_usd(self):
        locale = get_locale_config("US")
        result = validate_amount("10.555", locale)
        assert result is not None
        assert "decimal" in result.message.lower()

    def test_decimals_in_jpy(self):
        locale = get_locale_config("JP")
        result = validate_amount("100.5", locale)
        assert result is not None
        assert "decimal" in result.message.lower()

    def test_valid_with_symbol(self):
        locale = get_locale_config("US")
        assert validate_amount("$10.50", locale) is None

    def test_valid_with_thousands_separator(self):
        locale = get_locale_config("US")
        assert validate_amount("$1,234.56", locale) is None

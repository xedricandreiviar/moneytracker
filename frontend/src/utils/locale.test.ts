import { describe, it, expect } from "vitest";
import {
  formatAmount,
  parseAmountInput,
  formatDate,
  getWeekBoundaries,
  isValidAmountInput,
} from "./locale";
import { LOCALE_CONFIGS } from "../types/locale";

describe("formatAmount", () => {
  it("formats USD amount correctly", () => {
    const locale = LOCALE_CONFIGS["US"];
    expect(formatAmount(1050, locale)).toBe("$10.50");
    expect(formatAmount(100, locale)).toBe("$1.00");
    expect(formatAmount(0, locale)).toBe("$0.00");
    expect(formatAmount(999999, locale)).toBe("$9,999.99");
  });

  it("formats JPY amount correctly (zero decimals)", () => {
    const locale = LOCALE_CONFIGS["JP"];
    expect(formatAmount(1050, locale)).toBe("¥1,050");
    expect(formatAmount(100, locale)).toBe("¥100");
    expect(formatAmount(1000000, locale)).toBe("¥1,000,000");
  });

  it("formats EUR/DE amount correctly (comma decimal, dot thousands)", () => {
    const locale = LOCALE_CONFIGS["DE"];
    expect(formatAmount(123456, locale)).toBe("1.234,56 €");
    expect(formatAmount(100, locale)).toBe("1,00 €");
    expect(formatAmount(0, locale)).toBe("0,00 €");
  });

  it("formats EUR/FR amount correctly (comma decimal, space thousands)", () => {
    const locale = LOCALE_CONFIGS["FR"];
    expect(formatAmount(123456, locale)).toBe("1 234,56 €");
    expect(formatAmount(50, locale)).toBe("0,50 €");
  });

  it("formats GBP amount correctly", () => {
    const locale = LOCALE_CONFIGS["GB"];
    expect(formatAmount(1050, locale)).toBe("£10.50");
    expect(formatAmount(100000, locale)).toBe("£1,000.00");
  });

  it("formats negative amounts with sign", () => {
    const locale = LOCALE_CONFIGS["US"];
    expect(formatAmount(-1050, locale)).toBe("$-10.50");
  });
});

describe("parseAmountInput", () => {
  it("parses USD-style input", () => {
    const locale = LOCALE_CONFIGS["US"];
    expect(parseAmountInput("10.50", locale)).toBe(1050);
    expect(parseAmountInput("1,000.50", locale)).toBe(100050);
    expect(parseAmountInput("1", locale)).toBe(100);
    expect(parseAmountInput("0.01", locale)).toBe(1);
  });

  it("parses JPY-style input (no decimals)", () => {
    const locale = LOCALE_CONFIGS["JP"];
    expect(parseAmountInput("1050", locale)).toBe(1050);
    expect(parseAmountInput("1,000", locale)).toBe(1000);
  });

  it("parses EUR/DE-style input (comma decimal, dot thousands)", () => {
    const locale = LOCALE_CONFIGS["DE"];
    expect(parseAmountInput("10,50", locale)).toBe(1050);
    expect(parseAmountInput("1.000,50", locale)).toBe(100050);
  });

  it("parses EUR/FR-style input (comma decimal, space thousands)", () => {
    const locale = LOCALE_CONFIGS["FR"];
    expect(parseAmountInput("10,50", locale)).toBe(1050);
    expect(parseAmountInput("1 000,50", locale)).toBe(100050);
  });

  it("returns null for invalid inputs", () => {
    const locale = LOCALE_CONFIGS["US"];
    expect(parseAmountInput("", locale)).toBeNull();
    expect(parseAmountInput("abc", locale)).toBeNull();
    expect(parseAmountInput("-10", locale)).toBeNull();
    expect(parseAmountInput("0", locale)).toBeNull();
    expect(parseAmountInput("0.00", locale)).toBeNull();
    expect(parseAmountInput("10.123", locale)).toBeNull(); // Too many decimals
  });

  it("rejects decimals for zero-precision currencies", () => {
    const locale = LOCALE_CONFIGS["JP"];
    expect(parseAmountInput("10.5", locale)).toBeNull();
    expect(parseAmountInput("10,5", locale)).toBeNull();
  });

  it("rejects excess decimal places", () => {
    const locale = LOCALE_CONFIGS["US"];
    expect(parseAmountInput("10.123", locale)).toBeNull();
    expect(parseAmountInput("10.1", locale)).toBe(1010); // Fewer decimals OK
  });
});

describe("formatAmount/parseAmountInput round-trip", () => {
  it("round-trips USD amounts", () => {
    const locale = LOCALE_CONFIGS["US"];
    const amounts = [1, 100, 1050, 999999, 10000000];
    for (const amount of amounts) {
      const formatted = formatAmount(amount, locale);
      // Remove symbol and trim for parsing
      const numericPart = formatted.replace("$", "").trim();
      expect(parseAmountInput(numericPart, locale)).toBe(amount);
    }
  });

  it("round-trips JPY amounts", () => {
    const locale = LOCALE_CONFIGS["JP"];
    const amounts = [1, 100, 1050, 1000000];
    for (const amount of amounts) {
      const formatted = formatAmount(amount, locale);
      const numericPart = formatted.replace("¥", "").trim();
      expect(parseAmountInput(numericPart, locale)).toBe(amount);
    }
  });

  it("round-trips EUR/DE amounts", () => {
    const locale = LOCALE_CONFIGS["DE"];
    const amounts = [1, 100, 1050, 123456];
    for (const amount of amounts) {
      const formatted = formatAmount(amount, locale);
      const numericPart = formatted.replace("€", "").trim();
      expect(parseAmountInput(numericPart, locale)).toBe(amount);
    }
  });
});

describe("formatDate", () => {
  it("formats date in MM/DD/YYYY (US)", () => {
    const locale = LOCALE_CONFIGS["US"];
    const date = new Date(2024, 0, 15); // Jan 15, 2024
    expect(formatDate(date, locale)).toBe("01/15/2024");
  });

  it("formats date in DD/MM/YYYY (GB)", () => {
    const locale = LOCALE_CONFIGS["GB"];
    const date = new Date(2024, 0, 15);
    expect(formatDate(date, locale)).toBe("15/01/2024");
  });

  it("formats date in YYYY/MM/DD (JP)", () => {
    const locale = LOCALE_CONFIGS["JP"];
    const date = new Date(2024, 0, 15);
    expect(formatDate(date, locale)).toBe("2024/01/15");
  });

  it("formats date in DD.MM.YYYY (DE)", () => {
    const locale = LOCALE_CONFIGS["DE"];
    const date = new Date(2024, 11, 25); // Dec 25, 2024
    expect(formatDate(date, locale)).toBe("25.12.2024");
  });

  it("formats date in YYYY-MM-DD (CA)", () => {
    const locale = LOCALE_CONFIGS["CA"];
    const date = new Date(2024, 5, 1); // Jun 1, 2024
    expect(formatDate(date, locale)).toBe("2024-06-01");
  });

  it("formats date in YYYY.MM.DD (KR)", () => {
    const locale = LOCALE_CONFIGS["KR"];
    const date = new Date(2024, 2, 7); // Mar 7, 2024
    expect(formatDate(date, locale)).toBe("2024.03.07");
  });
});

describe("getWeekBoundaries", () => {
  it("returns Sunday-Saturday for US locale (week_start_day=0)", () => {
    const locale = LOCALE_CONFIGS["US"];
    // Wednesday, Jan 17, 2024
    const date = new Date(2024, 0, 17);
    const [start, end] = getWeekBoundaries(date, locale);

    expect(start.getDay()).toBe(0); // Sunday
    expect(start.getDate()).toBe(14); // Jan 14
    expect(end.getDate()).toBe(20); // Jan 20 (Saturday)
  });

  it("returns Monday-Sunday for GB locale (week_start_day=1)", () => {
    const locale = LOCALE_CONFIGS["GB"];
    // Wednesday, Jan 17, 2024
    const date = new Date(2024, 0, 17);
    const [start, end] = getWeekBoundaries(date, locale);

    expect(start.getDay()).toBe(1); // Monday
    expect(start.getDate()).toBe(15); // Jan 15
    expect(end.getDate()).toBe(21); // Jan 21 (Sunday)
  });

  it("handles date that falls on the week start day", () => {
    const locale = LOCALE_CONFIGS["US"];
    // Sunday, Jan 14, 2024
    const date = new Date(2024, 0, 14);
    const [start, end] = getWeekBoundaries(date, locale);

    expect(start.getDay()).toBe(0); // Sunday
    expect(start.getDate()).toBe(14);
    expect(end.getDate()).toBe(20);
  });

  it("has exactly 6 days between start and end", () => {
    const locale = LOCALE_CONFIGS["GB"];
    const date = new Date(2024, 5, 15); // Jun 15, 2024 (Saturday)
    const [start, end] = getWeekBoundaries(date, locale);

    const diffDays =
      (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24);
    expect(Math.floor(diffDays)).toBe(6);
  });

  it("ensures date is within boundaries", () => {
    const locale = LOCALE_CONFIGS["DE"];
    const date = new Date(2024, 2, 7); // Mar 7, 2024 (Thursday)
    const [start, end] = getWeekBoundaries(date, locale);

    expect(date.getTime()).toBeGreaterThanOrEqual(start.getTime());
    expect(date.getTime()).toBeLessThanOrEqual(end.getTime());
  });
});

describe("isValidAmountInput", () => {
  it("validates positive amounts", () => {
    const locale = LOCALE_CONFIGS["US"];
    expect(isValidAmountInput("10.50", locale)).toBe(true);
    expect(isValidAmountInput("1", locale)).toBe(true);
    expect(isValidAmountInput("1000.00", locale)).toBe(true);
  });

  it("rejects invalid amounts", () => {
    const locale = LOCALE_CONFIGS["US"];
    expect(isValidAmountInput("", locale)).toBe(false);
    expect(isValidAmountInput("abc", locale)).toBe(false);
    expect(isValidAmountInput("-5", locale)).toBe(false);
    expect(isValidAmountInput("0", locale)).toBe(false);
    expect(isValidAmountInput("10.123", locale)).toBe(false);
  });
});

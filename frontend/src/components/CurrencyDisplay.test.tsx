import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CurrencyDisplay } from "./CurrencyDisplay";
import { LOCALE_CONFIGS } from "../types/locale";

describe("CurrencyDisplay", () => {
  it("displays USD amount formatted correctly", () => {
    render(<CurrencyDisplay amount={1050} currencyCode="USD" />);
    expect(screen.getByText("$10.50")).toBeInTheDocument();
  });

  it("displays JPY amount formatted correctly (no decimals)", () => {
    render(<CurrencyDisplay amount={1050} currencyCode="JPY" />);
    expect(screen.getByText("¥1,050")).toBeInTheDocument();
  });

  it("displays EUR amount formatted correctly", () => {
    render(<CurrencyDisplay amount={123456} currencyCode="EUR" />);
    expect(screen.getByText("1.234,56 €")).toBeInTheDocument();
  });

  it("displays GBP amount formatted correctly", () => {
    render(<CurrencyDisplay amount={100000} currencyCode="GBP" />);
    expect(screen.getByText("£1,000.00")).toBeInTheDocument();
  });

  it("uses provided locale override", () => {
    const frLocale = LOCALE_CONFIGS["FR"];
    render(
      <CurrencyDisplay amount={123456} currencyCode="EUR" locale={frLocale} />
    );
    expect(screen.getByText("1 234,56 €")).toBeInTheDocument();
  });

  it("falls back gracefully for unknown currency codes", () => {
    render(<CurrencyDisplay amount={1050} currencyCode="XYZ" />);
    // Should render with the currency code as symbol, 2 decimal places
    expect(screen.getByText("XYZ10.50")).toBeInTheDocument();
  });

  it("handles zero amount", () => {
    render(<CurrencyDisplay amount={0} currencyCode="USD" />);
    expect(screen.getByText("$0.00")).toBeInTheDocument();
  });

  it("handles large amounts with thousands separators", () => {
    render(<CurrencyDisplay amount={10000000} currencyCode="USD" />);
    expect(screen.getByText("$100,000.00")).toBeInTheDocument();
  });

  it("applies custom className", () => {
    const { container } = render(
      <CurrencyDisplay amount={1050} currencyCode="USD" className="custom" />
    );
    expect(container.querySelector(".custom")).toBeInTheDocument();
  });

  it("has accessible aria-label", () => {
    render(<CurrencyDisplay amount={1050} currencyCode="USD" />);
    expect(screen.getByLabelText("$10.50")).toBeInTheDocument();
  });
});

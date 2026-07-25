import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AmountInput } from "./AmountInput";
import { LOCALE_CONFIGS } from "../types/locale";

describe("AmountInput", () => {
  const usdLocale = LOCALE_CONFIGS["US"];
  const jpyLocale = LOCALE_CONFIGS["JP"];
  const deLocale = LOCALE_CONFIGS["DE"];

  it("renders with currency symbol as prefix for USD", () => {
    render(
      <AmountInput locale={usdLocale} value="" onChange={vi.fn()} />
    );
    expect(screen.getByText("$")).toBeInTheDocument();
  });

  it("renders with currency symbol as suffix for EUR/DE", () => {
    render(
      <AmountInput locale={deLocale} value="" onChange={vi.fn()} />
    );
    expect(screen.getByText("€")).toBeInTheDocument();
  });

  it("shows placeholder with correct decimal format", () => {
    render(
      <AmountInput locale={usdLocale} value="" onChange={vi.fn()} />
    );
    expect(screen.getByPlaceholderText("0.00")).toBeInTheDocument();
  });

  it("shows whole number placeholder for zero-decimal currencies", () => {
    render(
      <AmountInput locale={jpyLocale} value="" onChange={vi.fn()} />
    );
    expect(screen.getByPlaceholderText("0")).toBeInTheDocument();
  });

  it("calls onChange with valid numeric input", () => {
    const onChange = vi.fn();
    render(
      <AmountInput locale={usdLocale} value="" onChange={onChange} />
    );

    const input = screen.getByLabelText("Amount");
    fireEvent.change(input, { target: { value: "10.50" } });
    expect(onChange).toHaveBeenCalledWith("10.50");
  });

  it("blocks non-numeric characters", () => {
    const onChange = vi.fn();
    render(
      <AmountInput locale={usdLocale} value="" onChange={onChange} />
    );

    const input = screen.getByLabelText("Amount");
    fireEvent.change(input, { target: { value: "abc" } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("blocks excess decimal places for USD", () => {
    const onChange = vi.fn();
    render(
      <AmountInput locale={usdLocale} value="10.50" onChange={onChange} />
    );

    const input = screen.getByLabelText("Amount");
    fireEvent.change(input, { target: { value: "10.501" } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("blocks decimal input for JPY", () => {
    const onChange = vi.fn();
    render(
      <AmountInput locale={jpyLocale} value="100" onChange={onChange} />
    );

    const input = screen.getByLabelText("Amount");
    fireEvent.change(input, { target: { value: "100." } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("allows comma as decimal separator for DE locale", () => {
    const onChange = vi.fn();
    render(
      <AmountInput locale={deLocale} value="" onChange={onChange} />
    );

    const input = screen.getByLabelText("Amount");
    fireEvent.change(input, { target: { value: "10,50" } });
    expect(onChange).toHaveBeenCalledWith("10,50");
  });

  it("displays error message when provided", () => {
    render(
      <AmountInput
        locale={usdLocale}
        value="10.50"
        onChange={vi.fn()}
        error="Amount is required"
      />
    );
    expect(screen.getByText("Amount is required")).toBeInTheDocument();
  });

  it("shows validation error on blur with invalid input", () => {
    render(
      <AmountInput locale={usdLocale} value="0" onChange={vi.fn()} />
    );

    const input = screen.getByLabelText("Amount");
    fireEvent.blur(input);
    expect(
      screen.getByText("Enter a positive number with up to 2 decimal places")
    ).toBeInTheDocument();
  });

  it("allows empty input (clears value)", () => {
    const onChange = vi.fn();
    render(
      <AmountInput locale={usdLocale} value="10" onChange={onChange} />
    );

    const input = screen.getByLabelText("Amount");
    fireEvent.change(input, { target: { value: "" } });
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("is disabled when disabled prop is true", () => {
    render(
      <AmountInput locale={usdLocale} value="" onChange={vi.fn()} disabled />
    );

    const input = screen.getByLabelText("Amount");
    expect(input).toBeDisabled();
  });
});

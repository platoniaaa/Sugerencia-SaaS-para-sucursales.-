import { describe, expect, it } from "vitest";
import {
  formatoCLP,
  formatoCLPCorto,
  formatoFecha,
  formatoNumero,
} from "@/lib/formato";

describe("formato chileno", () => {
  it("formatea CLP sin decimales y miles con punto", () => {
    expect(formatoCLP(1234567)).toContain("1.234.567");
    expect(formatoCLP(null)).toBe("—");
  });

  it("formatea CLP corto en millones", () => {
    expect(formatoCLPCorto(987_000_000)).toContain("mill");
  });

  it("formatea numeros con decimales", () => {
    expect(formatoNumero(1234.5, 1)).toBe("1.234,5");
    expect(formatoNumero(10)).toBe("10");
  });

  it("formatea fecha dd-mm-aaaa", () => {
    expect(formatoFecha("2026-05-21T10:00:00Z")).toMatch(/^\d{2}-\d{2}-2026$/);
    expect(formatoFecha(null)).toBe("—");
  });
});

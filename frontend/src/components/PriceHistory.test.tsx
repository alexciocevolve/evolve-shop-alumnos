import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PriceChange } from "../api";
import PriceHistory from "./PriceHistory";

vi.mock("../api", () => ({ getPriceHistory: vi.fn() }));

const { getPriceHistory } = await import("../api");

function change(previous: number, now: number, at = "2026-09-19T22:31:33+00:00"): PriceChange {
  return { changed_at: at, previous_price_cents: previous, price_cents: now };
}

describe("PriceHistory", () => {
  it("says a product has not changed price, and does not call that an error", async () => {
    // The reason the API answers 200 with an empty list rather than 404 for a product with
    // no changes, checked from the side that has to live with it. useData turns every
    // non-OK answer into the error state, so a 404 here would report the ordinary case -
    // which is most products - as a failure the reader can do nothing about.
    vi.mocked(getPriceHistory).mockResolvedValue([]);

    render(<PriceHistory productId={1} />);

    expect(await screen.findByText("This product has not changed price yet.")).toBeInTheDocument();
    expect(screen.queryByText(/unavailable/)).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows where each price came from and where it went, oldest first", async () => {
    vi.mocked(getPriceHistory).mockResolvedValue([change(89900, 84900), change(84900, 79900)]);

    render(<PriceHistory productId={1} />);

    const rows = await screen.findAllByRole("row");
    // One header row plus the two changes, in the order the API sent them: a history reads
    // forwards, and each row says what the price was and what it became without needing
    // the row before it.
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveTextContent("€899.00");
    expect(rows[1]).toHaveTextContent("€849.00");
    expect(rows[2]).toHaveTextContent("€799.00");
  });

  it("stays quiet when the history cannot be loaded", async () => {
    // The history is extra. A product whose history failed to load is still a product
    // somebody can read about and add to the cart, so this must not take over the modal.
    vi.mocked(getPriceHistory).mockRejectedValue({ status: 0, detail: "Could not reach the server" });

    render(<PriceHistory productId={1} />);

    expect(await screen.findByText("Price history unavailable right now.")).toBeInTheDocument();
  });
});

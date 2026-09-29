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
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("scales the chart to the prices, not from zero, and says so", async () => {
    vi.mocked(getPriceHistory).mockResolvedValue([
      change(89900, 84900, "2026-09-01T10:00:00+00:00"),
      change(84900, 79900, "2026-09-19T10:00:00+00:00"),
    ]);

    render(<PriceHistory productId={1} />);

    // The whole point of the chart. On an axis starting at zero, a hundred euros off an
    // eight-hundred-euro laptop is a flat line: true and useless. The axis runs between the
    // lowest and highest price this product ever had.
    expect(await screen.findByText(/€799.00.*€899.00.*not from zero/)).toBeInTheDocument();

    // And the price of that decision is that it exaggerates, so the chart has to admit its
    // scale rather than let a reader assume the usual one. This is the test that fails if
    // somebody draws the line without the caption underneath it.
    expect(screen.queryByText(/€0.00/)).not.toBeInTheDocument();
  });

  it("gives the chart a name, because a picture on its own says nothing out loud", async () => {
    vi.mocked(getPriceHistory).mockResolvedValue([
      change(89900, 84900, "2026-09-01T10:00:00+00:00"),
      change(84900, 79900, "2026-09-19T10:00:00+00:00"),
    ]);

    render(<PriceHistory productId={1} />);

    const chart = await screen.findByRole("img");
    expect(chart).toHaveAccessibleName(/Price from €899.00 to €799.00 over 2 changes/);
  });

  it("keeps every number in the page, not only in the picture", async () => {
    vi.mocked(getPriceHistory).mockResolvedValue([change(89900, 84900), change(84900, 79900)]);

    render(<PriceHistory productId={1} />);

    // The table is off screen, not gone. A label describes a chart; it is not the data, and
    // somebody using a screen reader should be able to read the figures rather than a
    // summary of them. display:none would have taken it out of the accessibility tree too.
    const rows = await screen.findAllByRole("row");
    expect(rows).toHaveLength(3); // header plus the two changes
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

import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Category, Product, ProductPage } from "../api";
import Catalog from "./Catalog";

// The catalog is the one page with logic of its own, so the API and the cart are replaced
// by things this test controls completely. What is being checked is the page's decisions,
// not whether fetch works.
vi.mock("../api", () => ({
  listCategories: vi.fn(),
  listProducts: vi.fn(),
  reportProductView: vi.fn(),
  getPriceHistory: vi.fn(),
}));
vi.mock("../cart", () => ({
  useCart: () => ({ cart: null, setQuantity: vi.fn() }),
}));

const { listCategories, listProducts, reportProductView, getPriceHistory } = await import("../api");

const CATEGORIES: Category[] = [
  { id: 1, name: "laptops" },
  { id: 2, name: "monitors" },
];

function product(id: number): Product {
  return {
    id,
    name: `Product ${id}`,
    description: "",
    category: "laptops",
    price_cents: 1000,
    stock: 5,
    image_url: `http://localhost:8000/images/product-${id}.jpg`,
  };
}

function page(ids: number[], next: number | null): ProductPage {
  return { items: ids.map(product), next_cursor: next };
}

beforeEach(() => {
  vi.mocked(listCategories).mockResolvedValue(CATEGORIES);
});

describe("Catalog", () => {
  it("adds each page to the ones before it instead of replacing them", async () => {
    vi.mocked(listProducts)
      .mockResolvedValueOnce(page([1, 2], 2))
      .mockResolvedValueOnce(page([3, 4], null));

    render(<Catalog />);

    // On a screen tall enough to show the end of the list, the catalog keeps asking:
    // the sentinel is still visible after the first page, so the second is requested.
    await screen.findByText("Product 3");
    // The first page is still there. Replacing instead of concatenating is the bug this
    // catches, and on screen it looks like the list jumping back to the top.
    expect(screen.getByText("Product 1")).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(4);
  });

  it("stops asking once the server says there is no next page", async () => {
    vi.mocked(listProducts).mockResolvedValue(page([1, 2], null));

    render(<Catalog />);
    await screen.findByText("Product 1");

    // next_cursor was null, so there is nothing more to ask for however visible the
    // sentinel stays. Without that check the page would ask for ever.
    await waitFor(() => expect(listProducts).toHaveBeenCalledTimes(1));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(listProducts).toHaveBeenCalledTimes(1);
  });

  it("throws away an answer that arrives after the reader changed category", async () => {
    // The race the generation counter exists for: a slow answer for the category that was
    // abandoned must not paint over the one that was asked for afterwards.
    let releaseTheSlowOne: (value: ProductPage) => void = () => {};
    vi.mocked(listProducts)
      .mockResolvedValueOnce(page([1], null)) // the first load, "All"
      .mockReturnValueOnce(
        new Promise<ProductPage>((resolve) => {
          releaseTheSlowOne = resolve;
        }),
      )
      .mockResolvedValueOnce(page([99], null)); // monitors, which answers immediately

    render(<Catalog />);
    await screen.findByText("Product 1");

    await userEvent.click(screen.getByRole("button", { name: "laptops" }));
    await userEvent.click(screen.getByRole("button", { name: "monitors" }));
    await screen.findByText("Product 99");

    releaseTheSlowOne(page([50], null)); // the abandoned laptops answer turns up late

    await waitFor(() => expect(screen.getByText("Product 99")).toBeInTheDocument());
    expect(screen.queryByText("Product 50")).not.toBeInTheDocument();
  });

  it("empties the list when the category changes", async () => {
    vi.mocked(listProducts)
      .mockResolvedValueOnce(page([1, 2], null))
      .mockResolvedValueOnce(page([99], null));

    render(<Catalog />);
    await screen.findByText("Product 1");

    await userEvent.click(screen.getByRole("button", { name: "monitors" }));

    await screen.findByText("Product 99");
    expect(screen.queryByText("Product 1")).not.toBeInTheDocument();
  });

  it("says so when a category has nothing in it", async () => {
    vi.mocked(listProducts).mockResolvedValue(page([], null));

    render(<Catalog />);

    expect(await screen.findByText("No products in this category.")).toBeInTheDocument();
  });

  it("shows the reason when the shop cannot be reached, and can try again", async () => {
    vi.mocked(listProducts)
      .mockRejectedValueOnce({ status: 0, detail: "Could not reach the server" })
      .mockResolvedValueOnce(page([1], null));

    render(<Catalog />);
    await screen.findByText(/Could not reach the server/);

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Product 1")).toBeInTheDocument();
  });

  it("asks for no price history at all until somebody opens a product", async () => {
    vi.mocked(listProducts).mockResolvedValue(page([1, 2, 3], null));
    vi.mocked(getPriceHistory).mockResolvedValue([]);

    render(<Catalog />);
    await screen.findByText("Product 3");

    // Three cards on screen and not one request. This is the whole reason the history is
    // not part of GET /products: on a full page it would be twelve requests to draw
    // something nobody is looking at. The N+1 that never happens because nobody asked.
    expect(getPriceHistory).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Product 2" }));

    // And now exactly one, for the one product that was opened.
    await waitFor(() => expect(getPriceHistory).toHaveBeenCalledTimes(1));
    expect(getPriceHistory).toHaveBeenCalledWith(2);
  });

  it("draws the buttons the database sent, not a list written in the page", async () => {
    vi.mocked(listProducts).mockResolvedValue(page([1], null));
    vi.mocked(listCategories).mockResolvedValue([{ id: 7, name: "cables" }]);

    render(<Catalog />);

    // Adding a row to categories must put a button here with nothing else changed.
    expect(await screen.findByRole("button", { name: "cables" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "laptops" })).not.toBeInTheDocument();
  });

  it("tells the server once when a product is opened, even under StrictMode", async () => {
    vi.mocked(listProducts).mockResolvedValue(page([1], null));
    vi.mocked(getPriceHistory).mockResolvedValue([]);

    // StrictMode runs every effect twice while developing. The view is reported from the
    // click and not from an effect inside the modal, so it must still be sent only once.
    // Sent twice, every view in Kibana would count double.
    render(
      <StrictMode>
        <Catalog />
      </StrictMode>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Product 1" }));

    expect(reportProductView).toHaveBeenCalledTimes(1);
    expect(reportProductView).toHaveBeenCalledWith(1);
  });
});

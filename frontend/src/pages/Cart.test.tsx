import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { Address, Cart as CartType, User } from "../api";
import Cart from "./Cart";

const placeOrder = vi.fn();
const setQuantity = vi.fn();
const removeItem = vi.fn();

let cart: CartType | null = null;
let user: User | null = null;
let shippingAddress: Address | null = null;

vi.mock("../cart", () => ({
  useCart: () => ({ cart, setQuantity, removeItem, placeOrder }),
}));
vi.mock("../session", () => ({
  useSession: () => ({ user, shippingAddress }),
}));

const ADDRESS: Address = {
  id: 1,
  kind: "shipping",
  recipient_name: "Ana Torres",
  street: "Calle Mayor 1",
  city: "Madrid",
  postal_code: "28013",
  country: "ES",
};

const ANA: User = {
  id: 1,
  email: "ana@example.com",
  full_name: "Ana Torres",
  created_at: "2026-09-19T10:00:00+00:00",
};

function withCart(items = 1): CartType {
  return {
    token: "t",
    items: [
      {
        product_id: 1,
        name: "ProBook 14 Laptop",
        image_url: "http://localhost:8000/images/product-1.jpg",
        price_cents: 89900,
        quantity: items,
        subtotal_cents: 89900 * items,
      },
    ],
    total_cents: 89900 * items,
  };
}

function show({ signedIn = false, withAddress = false, empty = false } = {}) {
  cart = empty ? null : withCart();
  user = signedIn ? ANA : null;
  shippingAddress = withAddress ? ADDRESS : null;
  render(
    <MemoryRouter>
      <Cart />
    </MemoryRouter>,
  );
}

describe("Cart", () => {
  it("says the cart is empty instead of showing an empty table", () => {
    show({ empty: true });

    expect(screen.getByText(/Your cart is empty/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("will not let a visitor who is not signed in place an order", () => {
    show();

    expect(screen.getByRole("button", { name: "Place order" })).toBeDisabled();
    // Disabled and silent is a dead end. The reason has to be on screen, because the
    // person cannot see the 401 the API would have answered.
    expect(screen.getByText("Sign in to place this order.")).toBeInTheDocument();
  });

  it("will not let a signed-in customer order with nowhere to send it", () => {
    show({ signedIn: true });

    expect(screen.getByRole("button", { name: "Place order" })).toBeDisabled();
    expect(screen.getByText("Add a shipping address to place this order.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Add one in your account/ })).toBeInTheDocument();
  });

  it("shows where the order is going once there is an address", () => {
    show({ signedIn: true, withAddress: true });

    expect(screen.getByText("Shipping to")).toBeInTheDocument();
    expect(screen.getByText("Calle Mayor 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Place order" })).toBeEnabled();
    expect(screen.getByText(/This order will be placed for ana@example.com/)).toBeInTheDocument();
  });

  it("only places the order when everything is in order", async () => {
    show({ signedIn: true, withAddress: true });

    await userEvent.click(screen.getByRole("button", { name: "Place order" }));

    expect(placeOrder).toHaveBeenCalledOnce();
  });

  it("shows the money the server worked out, never a sum done here", () => {
    show({ signedIn: true, withAddress: true });

    // The line total and the total both come from the answer. If this page ever starts
    // multiplying prices itself, the two can disagree, and the customer believes the one
    // that is wrong.
    expect(screen.getAllByText("€899.00").length).toBeGreaterThan(0);
  });

  it("cannot take the last unit of a line away with the minus button", () => {
    show({ signedIn: true, withAddress: true });

    // Quantity zero does not exist: the API refuses it, and removing a line is what
    // Remove is for. The button is disabled rather than sending a request that fails.
    expect(screen.getByRole("button", { name: /One fewer/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /One more/ })).toBeEnabled();
  });

  it("asks the server for a new quantity rather than changing the screen", async () => {
    show({ signedIn: true, withAddress: true });

    await userEvent.click(screen.getByRole("button", { name: /One more/ }));

    expect(setQuantity).toHaveBeenCalledWith(1, 2);
  });
});

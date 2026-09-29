const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// What every failed call throws. `status` is 0 when the server could not be reached at all.
export type ApiError = { status: number; detail: string };

export const CART_TOKEN_KEY = "cart_token";

// Every call to the API goes through here, so errors look the same everywhere.
export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  // The cart token is attached here, once, instead of at every call that needs it.
  const token = localStorage.getItem(CART_TOKEN_KEY);
  const headers: Record<string, string> = {
    ...(options?.body ? { "Content-Type": "application/json" } : {}),
    ...(token ? { "X-Cart-Token": token } : {}),
  };

  let response: Response;
  try {
    response = await fetch(BASE + path, { ...options, headers });
  } catch {
    throw { status: 0, detail: "Could not reach the server" } satisfies ApiError;
  }
  if (!response.ok) {
    // The API always answers errors as {"detail": "..."}
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : response.statusText;
    throw { status: response.status, detail } satisfies ApiError;
  }
  return response.json() as Promise<T>;
}

// The shape of what the API sends. Keys stay snake_case, exactly as on the wire;
// everything we write in TypeScript (variables, functions) is camelCase.
export type Product = {
  id: number;
  name: string;
  description: string;
  category: string;
  price_cents: number;
  stock: number;
  image_url: string;
};

export type ProductPage = { items: Product[]; next_cursor: number | null };

export type Category = { id: number; name: string };

export const listCategories = () => request<Category[]>("/categories");

export function listProducts({ category, cursor }: { category?: string; cursor?: number } = {}) {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (cursor !== undefined) params.set("cursor", String(cursor));
  const query = params.toString();
  return request<ProductPage>(`/products${query ? `?${query}` : ""}`);
}

export const getProduct = (id: number) => request<Product>(`/products/${id}`);

// Tells the server that the customer opened a product's detail, so it can be logged.
// It does not use request(): the answer is empty (204) and nobody waits for it. If the
// call fails, the customer should not notice anything, so the error is ignored.
export function reportProductView(id: number) {
  fetch(`${BASE}/products/${id}/views`, { method: "POST" }).catch(() => {});
}

// A cart line has no price of its own: price_cents is TODAY's price, sent by the server.
export type CartItem = {
  product_id: number;
  name: string;
  image_url: string;
  price_cents: number;
  quantity: number;
  subtotal_cents: number;
};

export type Cart = { token: string; items: CartItem[]; total_cents: number };

// An order line DOES have its own price: the one it was bought at.
export type OrderItem = {
  product_id: number;
  name: string;
  quantity: number;
  price_cents: number;
};

export type Order = {
  id: number;
  customer_email: string;
  status: string;
  total_cents: number;
  created_at: string;
  items: OrderItem[];
};

export const createCart = () => request<Cart>("/cart", { method: "POST" });

export const getCart = () => request<Cart>("/cart");

export const setCartItem = (productId: number, quantity: number) =>
  request<Cart>(`/cart/items/${productId}`, {
    method: "PUT",
    body: JSON.stringify({ quantity }),
  });

export const removeCartItem = (productId: number) =>
  request<Cart>(`/cart/items/${productId}`, { method: "DELETE" });

// No body: the server decides the prices, the total and who is buying.
export const createOrder = () => request<Order>("/orders", { method: "POST" });

export const getOrder = (id: number) => request<Order>(`/orders/${id}`);

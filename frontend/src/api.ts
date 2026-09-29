const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// What every failed call throws. `status` is 0 when the server could not be reached at all.
export type ApiError = { status: number; detail: string };

export const CART_TOKEN_KEY = "cart_token";
export const AUTH_TOKEN_KEY = "auth_token";

// Every call to the API goes through here, so errors look the same everywhere.
export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  // Both tokens are attached here, once, instead of at every call that needs them.
  const cartToken = localStorage.getItem(CART_TOKEN_KEY);
  const authToken = localStorage.getItem(AUTH_TOKEN_KEY);
  const headers: Record<string, string> = {
    ...(options?.body ? { "Content-Type": "application/json" } : {}),
    ...(cartToken ? { "X-Cart-Token": cartToken } : {}),
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
  };

  let response: Response;
  try {
    response = await fetch(BASE + path, { ...options, headers });
  } catch {
    throw { status: 0, detail: "Could not reach the server" } satisfies ApiError;
  }
  // A token we sent and the server rejected is dead: it expired, or somebody signed out
  // somewhere else. Drop it here so the next call does not keep presenting it.
  if (response.status === 401 && authToken) localStorage.removeItem(AUTH_TOKEN_KEY);
  // 204 means "done, nothing to say", and asking it for JSON would throw.
  if (response.status === 204) return undefined as T;
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

// One row per price change, oldest first, the way the API sends it. Each row stands on its
// own: it says what the price came from and what it went to, without needing the row before.
export type PriceChange = {
  changed_at: string;
  previous_price_cents: number;
  price_cents: number;
};

// NOT part of listProducts on purpose. Asking for the history of the 12 products on a page
// would be 12 extra requests to draw something nobody is looking at; this is asked for one
// product, when somebody opens it. See components/PriceHistory.tsx.
export const getPriceHistory = (id: number) =>
  request<PriceChange[]>(`/products/${id}/price-history`);

export type AddressKind = "shipping" | "billing";

export type Address = {
  id: number;
  kind: AddressKind;
  recipient_name: string;
  street: string;
  city: string;
  postal_code: string;
  country: string;
};

// What the form sends: the address itself, with no id and no kind. Which slot it goes
// into is the path, and whose it is comes from the session - never from the body.
export type AddressInput = Omit<Address, "id" | "kind">;

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
  // The address this order went to, as it was on the day. Null for an order placed
  // without signing in.
  shipping_address: Address | null;
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

// The order, plus the one-off address to go and pay at. `checkout_url` is not stored
// anywhere and is not part of the order: it belongs to this single answer, because the
// browser is expected to leave for Stripe immediately.
export type PlacedOrder = Order & { checkout_url: string };

// No body: the server decides the prices, the total and who is buying.
export const createOrder = () => request<PlacedOrder>("/orders", { method: "POST" });

// Called by the success page when Stripe sends the buyer back. It tells the shop nothing
// Stripe said - it just asks it to believe that the payment happened, which is exactly
// the weakness this objective leaves in place on purpose.
export const confirmOrder = (id: number) =>
  request<Order>(`/orders/${id}/confirm`, { method: "POST" });

export const getOrder = (id: number) => request<Order>(`/orders/${id}`);

// Only ever your own: the server decides that from the token, not from anything sent here.
export const listOrders = () => request<Order[]>("/orders");

export type User = { id: number; email: string; full_name: string; created_at: string };

// The password travels in the body of a POST, never in the address: a URL ends up in the
// browser history, in the server log and in the Referer header sent to the next site.
export const registerUser = (email: string, password: string, fullName: string) =>
  request<User>("/users", {
    method: "POST",
    body: JSON.stringify({ email, password, full_name: fullName }),
  });

export const signIn = (email: string, password: string) =>
  request<{ token: string }>("/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

export const getMe = () => request<User>("/me");

export const signOut = () => request<void>("/logout", { method: "POST" });

export const listAddresses = () => request<Address[]>("/me/addresses");

export const saveAddress = (kind: AddressKind, address: AddressInput) =>
  request<Address>(`/me/addresses/${kind}`, {
    method: "PUT",
    body: JSON.stringify(address),
  });

export const deleteAddress = (kind: AddressKind) =>
  request<void>(`/me/addresses/${kind}`, { method: "DELETE" });

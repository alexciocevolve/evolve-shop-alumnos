import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  CART_TOKEN_KEY,
  createCart,
  createOrder,
  getCart,
  removeCartItem,
  setCartItem,
  type ApiError,
  type Cart,
  type Order,
} from "./api";

type CartValue = {
  cart: Cart | null;
  itemCount: number;
  error: string | null;
  clearError: () => void;
  setQuantity: (productId: number, quantity: number) => Promise<void>;
  removeItem: (productId: number) => Promise<void>;
  placeOrder: () => Promise<Order | null>;
};

const CartContext = createContext<CartValue | null>(null);

// Every screen reads the cart through this, instead of each one keeping its own copy
// and them drifting apart.
export function useCart(): CartValue {
  const value = useContext(CartContext);
  if (value === null) throw new Error("useCart used outside CartProvider");
  return value;
}

export function CartProvider({ children }: { children: ReactNode }) {
  const [cart, setCart] = useState<Cart | null>(null);
  const [error, setError] = useState<string | null>(null);

  // What is drawn is ALWAYS the last answer from the server, never a guess made here.
  // That is why every operation below ends in setCart(<what the server replied>).
  useEffect(() => {
    if (!localStorage.getItem(CART_TOKEN_KEY)) return;
    getCart().then(setCart, (e: ApiError) => {
      // 404 means the token names a cart the server no longer has: it became an order,
      // or the database was reset. The token is stale, so throw it away.
      if (e.status === 404) localStorage.removeItem(CART_TOKEN_KEY);
    });
  }, []);

  async function run(action: () => Promise<Cart>) {
    setError(null);
    try {
      setCart(await action());
    } catch (e) {
      setError((e as ApiError).detail);
    }
  }

  async function setQuantity(productId: number, quantity: number) {
    await run(async () => {
      // No cart yet? One is created on the first thing added, not when the page loads:
      // a visitor who only looks around never makes a row in the database.
      if (!localStorage.getItem(CART_TOKEN_KEY)) {
        localStorage.setItem(CART_TOKEN_KEY, (await createCart()).token);
      }
      return setCartItem(productId, quantity);
    });
  }

  async function removeItem(productId: number) {
    await run(() => removeCartItem(productId));
  }

  async function placeOrder(): Promise<Order | null> {
    setError(null);
    try {
      const order = await createOrder();
      // The server deleted the cart when it became an order, so the token is now useless.
      localStorage.removeItem(CART_TOKEN_KEY);
      setCart(null);
      return order;
    } catch (e) {
      setError((e as ApiError).detail);
      return null;
    }
  }

  const itemCount = cart?.items.reduce((total, item) => total + item.quantity, 0) ?? 0;

  return (
    <CartContext.Provider
      value={{
        cart,
        itemCount,
        error,
        clearError: () => setError(null),
        setQuantity,
        removeItem,
        placeOrder,
      }}
    >
      {children}
    </CartContext.Provider>
  );
}

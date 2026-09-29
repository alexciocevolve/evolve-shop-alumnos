import { BrowserRouter, Route, Routes } from "react-router-dom";
import { CartProvider, useCart } from "./cart";
import { SessionProvider } from "./session";
import Header from "./components/Header";
import Auth from "./pages/Auth";
import Catalog from "./pages/Catalog";
import Cart from "./pages/Cart";
import OrderConfirmation from "./pages/OrderConfirmation";

// One place for anything the cart could not do, whichever screen asked for it: adding
// from the catalog and placing the order from the cart page both end up here.
function CartError() {
  const { error, clearError } = useCart();
  if (!error) return null;
  return (
    <p className="status error">
      {error}{" "}
      <button type="button" className="chip" onClick={clearError}>
        Dismiss
      </button>
    </p>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <CartProvider>
          <Header />
          <main>
            <CartError />
            <Routes>
              <Route path="/" element={<Catalog />} />
              <Route path="/auth" element={<Auth />} />
              <Route path="/cart" element={<Cart />} />
              <Route path="/orders/:id" element={<OrderConfirmation />} />
            </Routes>
          </main>
        </CartProvider>
      </SessionProvider>
    </BrowserRouter>
  );
}

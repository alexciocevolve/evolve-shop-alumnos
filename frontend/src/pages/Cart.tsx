import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useCart } from "../cart";
import { formatPrice } from "../format";

export default function Cart() {
  const { cart, setQuantity, removeItem, placeOrder } = useCart();
  const [placing, setPlacing] = useState(false);
  const navigate = useNavigate();

  if (!cart || cart.items.length === 0) {
    return (
      <p className="status">
        Your cart is empty. <Link to="/">Back to the shop</Link>
      </p>
    );
  }

  async function submit() {
    setPlacing(true);
    const order = await placeOrder();
    setPlacing(false);
    // On failure placeOrder returns null and leaves the reason in the banner above,
    // with the cart untouched so it can be fixed and tried again.
    if (order) navigate(`/orders/${order.id}`);
  }

  return (
    <>
      <h2>Your cart</h2>
      <table>
        <thead>
          <tr>
            <th>Product</th>
            <th>Price</th>
            <th>Quantity</th>
            <th>Subtotal</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {cart.items.map((item) => (
            <tr key={item.product_id}>
              <td className="cart-product">
                <img src={item.image_url} alt="" width="56" height="42" />
                {item.name}
              </td>
              <td>{formatPrice(item.price_cents)}</td>
              <td>
                <div className="quantity">
                  {/* At one unit there is nothing to take away: removing the line is
                      what Remove is for, and the API refuses a quantity of zero. */}
                  <button
                    type="button"
                    aria-label={`One fewer ${item.name}`}
                    disabled={item.quantity === 1}
                    onClick={() => setQuantity(item.product_id, item.quantity - 1)}
                  >
                    −
                  </button>
                  <span>{item.quantity}</span>
                  <button
                    type="button"
                    aria-label={`One more ${item.name}`}
                    onClick={() => setQuantity(item.product_id, item.quantity + 1)}
                  >
                    +
                  </button>
                </div>
              </td>
              <td>{formatPrice(item.subtotal_cents)}</td>
              <td>
                <button
                  type="button"
                  className="link-button"
                  onClick={() => removeItem(item.product_id)}
                >
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th colSpan={3}>Total</th>
            <td className="price">{formatPrice(cart.total_cents)}</td>
            <td />
          </tr>
        </tfoot>
      </table>

      <div className="checkout">
        {/* No email field and no sign-in yet: every order goes to the same placeholder
            customer, decided by the server. Registration comes in the next checkpoint. */}
        <p className="status">This order will be placed for the demo customer.</p>
        <button type="button" className="primary" disabled={placing} onClick={submit}>
          {placing ? "Placing…" : "Place order"}
        </button>
      </div>
    </>
  );
}

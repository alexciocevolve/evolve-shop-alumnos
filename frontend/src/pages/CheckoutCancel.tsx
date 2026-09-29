import { Link } from "react-router-dom";

/**
 * Where Stripe sends the buyer if they back out of the payment page.
 *
 * Nothing is undone here, and that is not an omission - it is the honest state of things,
 * and it is worth showing rather than hiding:
 *
 *  · The order still exists, still pending. It was created before anybody paid.
 *  · Its stock is still reserved, because the shop took it off the shelf at that moment.
 *  · The cart is gone, because the order replaced it. The buyer retries against the ORDER.
 *  · And over at Stripe nothing becomes `canceled` by itself either. Backing out is not an
 *    event: the payment simply never happens, and sits there.
 *
 * So the shop is now holding stock for a purchase that will probably never happen, with
 * nothing to release it. That is the orphan, and it is why a later objective has to give
 * reservations an expiry.
 */
export default function CheckoutCancel() {
  return (
    <>
      <h2>Payment cancelled</h2>
      <p className="status">
        Nothing has been charged. Your order is still waiting to be paid.
      </p>
      <p>
        <Link to="/account">See your orders</Link> · <Link to="/">Back to the shop</Link>
      </p>
    </>
  );
}

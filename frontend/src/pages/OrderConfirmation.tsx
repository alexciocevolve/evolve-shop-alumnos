import { Link, useParams } from "react-router-dom";
import { getOrder } from "../api";
import AddressLines from "../components/AddressLines";
import { formatDate, formatPrice } from "../format";
import { useData } from "../useData";

export default function OrderConfirmation() {
  const { id } = useParams();
  // One load that replaces its data, so this is exactly what useData is for.
  const state = useData(() => getOrder(Number(id)), [id]);

  if (state.phase === "loading") return <p className="status">Loading…</p>;
  if (state.phase === "error") return <p className="status error">{state.detail}</p>;

  const order = state.data;
  return (
    <>
      <h2>Thank you! Order #{order.id}</h2>
      <p className="status">
        {formatDate(order.created_at)} · {order.status} · {order.customer_email}
      </p>

      {order.shipping_address && (
        <section className="shipping-to">
          <h3>Shipped to</h3>
          {/* The address as it was on the day. It does not follow the customer around:
              the order points at a row that is never edited. */}
          <AddressLines address={order.shipping_address} />
        </section>
      )}

      <table>
        <thead>
          <tr>
            <th>Product</th>
            <th>Price paid</th>
            <th>Quantity</th>
            <th>Subtotal</th>
          </tr>
        </thead>
        <tbody>
          {order.items.map((item) => (
            <tr key={item.product_id}>
              <td>{item.name}</td>
              {/* The price this was bought at. If the product changes price tomorrow,
                  this line keeps saying what was actually paid. */}
              <td>{formatPrice(item.price_cents)}</td>
              <td>{item.quantity}</td>
              <td>{formatPrice(item.price_cents * item.quantity)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th colSpan={3}>Total</th>
            <td className="price">{formatPrice(order.total_cents)}</td>
          </tr>
        </tfoot>
      </table>

      <p className="checkout">
        <Link to="/">Back to the shop</Link>
      </p>
    </>
  );
}

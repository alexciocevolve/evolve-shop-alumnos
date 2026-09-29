import { Link } from "react-router-dom";
import { listOrders } from "../api";
import { formatDate, formatPrice } from "../format";
import { useData } from "../useData";

export default function OrderList() {
  // One load that replaces its data: useData again, the same as the order page.
  const state = useData(listOrders);

  if (state.phase === "loading") return <p className="status">Loading orders…</p>;
  if (state.phase === "error") return <p className="status error">{state.detail}</p>;
  if (state.data.length === 0) {
    return (
      <p className="status">
        No orders yet. <Link to="/">Back to the shop</Link>
      </p>
    );
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Order</th>
          <th>Date</th>
          <th>Items</th>
          <th>Shipped to</th>
          <th>Total</th>
        </tr>
      </thead>
      <tbody>
        {state.data.map((order) => (
          <tr key={order.id}>
            <td>
              <Link to={`/orders/${order.id}`}>#{order.id}</Link>
            </td>
            <td>{formatDate(order.created_at)}</td>
            <td>{order.items.reduce((total, item) => total + item.quantity, 0)}</td>
            {/* The address as it was that day, not where this person lives now. */}
            <td>
              {order.shipping_address
                ? `${order.shipping_address.city} (${order.shipping_address.country})`
                : "—"}
            </td>
            <td className="price">{formatPrice(order.total_cents)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

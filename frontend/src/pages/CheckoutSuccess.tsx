import { useSearchParams } from "react-router-dom";
import { confirmOrder } from "../api";
import { useData } from "../useData";

/**
 * Where Stripe sends the buyer after they pay.
 *
 * Stripe adds `?session_id=cs_...` to this address. The shop reads it, tells the backend
 * the order is paid, and shows the confirmation.
 *
 * AND THAT IS WRONG, on purpose, in a way worth stopping on because almost every first
 * integration looks exactly like this:
 *
 *  · This page is the only thing that tells the shop anything. Close the tab one second
 *    after paying and the shop never finds out: Stripe has the money and the order sits
 *    pending forever, with nobody to notice.
 *  · It does not check the session_id against anything. It could be missing, invented, or
 *    copied from somebody else's purchase, and the shop would believe it just the same.
 *
 * Stripe says so itself, on the same page that explains how to build this: "Activar la
 * gestión logística solo desde tu página de éxito de Checkout no es fiable." The next
 * objective is that sentence being earned instead of quoted.
 */
export default function CheckoutSuccess() {
  const [params] = useSearchParams();
  // Stripe puts it there. It is read only to prove, in class, that it arrives - nothing
  // is done with it yet, which is the point.
  const sessionId = params.get("session_id");
  const orderId = Number(params.get("order_id"));

  const state = useData(() => confirmOrder(orderId), [orderId]);

  if (state.phase === "loading") return <p className="status">Confirming your payment…</p>;
  if (state.phase === "error") return <p className="status error">{state.detail}</p>;

  const order = state.data;
  return (
    <>
      <h2>Thank you! Order #{order.id}</h2>
      <p className="status">
        {order.status} · {order.customer_email}
      </p>
      <p>
        Paid with Stripe. <a href={`/orders/${order.id}`}>See the order</a>
      </p>
      {/* Visible on purpose while this is being taught: it is the only thing Stripe sends
          back, and the next objective turns it from decoration into the actual proof. */}
      {sessionId && <p className="status">Stripe session: {sessionId}</p>}
    </>
  );
}

import { getPriceHistory } from "../api";
import { formatDate, formatPrice } from "../format";
import { useData } from "../useData";

// The price history of ONE product, asked for when this component appears.
//
// That is the whole design, and it is worth saying why it is not in `GET /products`. The
// catalog draws 12 cards a page and nobody is reading the price history of 12 products at
// once: putting it in the listing would mean 12 histories fetched, sorted and sent to draw
// something that stays hidden. Asking here instead is one request for the one product
// somebody actually opened - and the request only happens because the modal mounted this,
// so browsing the catalog asks for nothing at all.
//
// It is the same N+1 question as the one in the backend (session 13's joinedload), asked
// from the other end. There the fix was to fetch the many in ONE query, because every row
// on screen needed its category. Here the fix is the opposite - do not fetch them at all -
// because only one product's history is ever on screen. "Batch it" and "do not ask for it"
// are both answers to N+1; which one is right depends on how much of it gets looked at.
export default function PriceHistory({ productId }: { productId: number }) {
  const state = useData(() => getPriceHistory(productId), [productId]);

  if (state.phase === "loading") {
    return <p className="price-history-note">Loading price history…</p>;
  }

  if (state.phase === "error") {
    // Deliberately quiet. The history is extra: a product whose history cannot be loaded is
    // still a product somebody can read about and buy, so this does not take over the modal.
    return <p className="price-history-note">Price history unavailable right now.</p>;
  }

  if (state.data.length === 0) {
    // NOT an error, and this is exactly why the API answers 200 with an empty list rather
    // than a 404 for a product that has never changed price. With a 404, useData would put
    // this component into the error state above, and the ordinary case - which is most
    // products - would be reported to the reader as a failure.
    return <p className="price-history-note">This product has not changed price yet.</p>;
  }

  return (
    <section className="price-history">
      <h3 id="price-history-caption">Price history</h3>
      <table aria-labelledby="price-history-caption">
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Before</th>
            <th scope="col">After</th>
          </tr>
        </thead>
        <tbody>
          {state.data.map((change) => (
            // changed_at is not unique: several changes committed in one transaction carry
            // the same timestamp, because now() in PostgreSQL is the start of the
            // transaction. The date and both prices together are what tells them apart.
            <tr key={`${change.changed_at}-${change.previous_price_cents}-${change.price_cents}`}>
              <td>{formatDate(change.changed_at)}</td>
              <td className="price-before">{formatPrice(change.previous_price_cents)}</td>
              <td>{formatPrice(change.price_cents)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

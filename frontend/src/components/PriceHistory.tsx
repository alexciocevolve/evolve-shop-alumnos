import { getPriceHistory, type PriceChange } from "../api";
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

const WIDTH = 320;
const HEIGHT = 110;
const PAD = { left: 52, right: 10, top: 10, bottom: 22 };

// How much room to leave above the highest price and below the lowest, as a share of the
// range they span. Without it the line would touch the edges of the box and the first and
// last points would be half cut off.
const BREATHING_ROOM = 0.15;

type Point = { x: number; cents: number };

function scale(history: PriceChange[]) {
  // Every price the product has ever had: the one before each change and the one after.
  const prices = history.flatMap((c) => [c.previous_price_cents, c.price_cents]);
  const lowest = Math.min(...prices);
  const highest = Math.max(...prices);

  // THE DECISION OF THIS CHART: the vertical axis runs from the lowest price to the
  // highest, NOT from zero. On a shop where everything costs three figures, an axis
  // starting at zero would squash every change this product has ever had into a couple of
  // pixels and draw a flat line - technically honest and completely useless.
  //
  // The price of that decision is that it EXAGGERATES: on a truncated axis a 2% change
  // looks as dramatic as a 50% one, which is the oldest trick in misleading charts. So the
  // chart says what its scale is, under the picture, instead of leaving it to be assumed.
  const room = Math.max(1, (highest - lowest) * BREATHING_ROOM);
  const bottom = lowest - room;
  const top = highest + room;

  const times = history.map((c) => new Date(c.changed_at).getTime());
  const span = times[times.length - 1] - times[0];

  // Time-proportional, because the whole question is how the price moved OVER TIME: two
  // changes a year apart and two a minute apart are different stories, and spacing them
  // evenly would erase the difference. Even spacing is the fallback for the one case where
  // proportional is impossible - every change in the same transaction, so span is zero.
  const at = (index: number) =>
    span > 0
      ? (times[index] - times[0]) / span
      : history.length > 1
        ? index / (history.length - 1)
        : 0;

  // Two points per change, and together they draw a staircase: the vertical jump is the
  // change itself, and the horizontal run to the next one is the time the new price held.
  // It joins up on its own because each change's "before" IS the previous change's "after".
  const points: Point[] = history.flatMap((change, index) => [
    { x: at(index), cents: change.previous_price_cents },
    { x: at(index), cents: change.price_cents },
  ]);

  return { points, lowest, highest, bottom, top, firstDate: times[0], lastDate: times.at(-1)! };
}

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

  const { points, lowest, highest, bottom, top, firstDate, lastDate } = scale(state.data);
  const x = (share: number) => PAD.left + share * (WIDTH - PAD.left - PAD.right);
  const y = (cents: number) =>
    PAD.top + (1 - (cents - bottom) / (top - bottom)) * (HEIGHT - PAD.top - PAD.bottom);

  const line = points.map((point) => `${x(point.x)},${y(point.cents)}`).join(" ");
  const paid = state.data.at(-1)!.price_cents;
  const started = state.data[0].previous_price_cents;

  return (
    <section className="price-history">
      <h3 id="price-history-caption">Price history</h3>

      <svg
        className="price-chart"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        // role="img" with a label, because a chart is a picture: without this a screen
        // reader announces a pile of meaningless shapes. The table below says the rest.
        role="img"
        aria-label={
          `Price from ${formatPrice(started)} to ${formatPrice(paid)} over ` +
          `${state.data.length} ${state.data.length === 1 ? "change" : "changes"}, ` +
          `between ${formatDate(state.data[0].changed_at)} and ` +
          `${formatDate(state.data.at(-1)!.changed_at)}.`
        }
      >
        {/* The two prices that bound the drawing, so the numbers are readable without
            counting pixels - and so the truncated axis cannot be mistaken for one that
            starts at zero. */}
        <text className="price-chart-tick" x={PAD.left - 6} y={y(highest) + 3} textAnchor="end">
          {formatPrice(highest)}
        </text>
        <text className="price-chart-tick" x={PAD.left - 6} y={y(lowest) + 3} textAnchor="end">
          {formatPrice(lowest)}
        </text>
        <line className="price-chart-grid" x1={PAD.left} x2={WIDTH - PAD.right} y1={y(highest)} y2={y(highest)} />
        <line className="price-chart-grid" x1={PAD.left} x2={WIDTH - PAD.right} y1={y(lowest)} y2={y(lowest)} />

        <polyline className="price-chart-line" points={line} />
        {points.map((point, index) => (
          <circle key={index} className="price-chart-dot" cx={x(point.x)} cy={y(point.cents)} r="2" />
        ))}

        <text className="price-chart-tick" x={PAD.left} y={HEIGHT - 6}>
          {formatDate(new Date(firstDate).toISOString())}
        </text>
        <text className="price-chart-tick" x={WIDTH - PAD.right} y={HEIGHT - 6} textAnchor="end">
          {formatDate(new Date(lastDate).toISOString())}
        </text>
      </svg>

      <p className="price-history-note">
        Vertical axis {formatPrice(lowest)}–{formatPrice(highest)}, not from zero, so small
        changes stay visible.
      </p>

      {/* The same numbers, out of sight but still in the page. A chart is unreadable to a
          screen reader however well it is labelled, and a summary is not the data. Keeping
          the table costs nothing and is the difference between "described" and "available". */}
      <table className="visually-hidden" aria-labelledby="price-history-caption">
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
              <td>{formatPrice(change.previous_price_cents)}</td>
              <td>{formatPrice(change.price_cents)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

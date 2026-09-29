import { getPriceHistory, type PriceChange } from "../api";
import { formatDate, formatDay, formatPrice, formatTime } from "../format";
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

// Roughly the size in pixels this is drawn at inside the modal, and that is the point. An
// SVG with a small viewBox stretched to fill a wide box magnifies EVERYTHING in it, text
// and stroke widths included. The first version was authored at 320x110, drawn at about
// 600 wide, and every 9px label came out at 18px - a small diagram wearing the lettering
// of a poster, which is what made it look wrong long before anybody could say why.
// Authoring at the size it is shown means a font-size of 12 is 12.
const WIDTH = 640;
const HEIGHT = 190;
const PAD = { left: 68, right: 16, top: 18, bottom: 34 };

// Room above the highest price and below the lowest, as a share of the range they span, so
// the line never touches the edge of the box and the end points are not half cut off.
const BREATHING_ROOM = 0.18;

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

  return { points, at, lowest, highest, bottom, top };
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

  const { points, at, lowest, highest, bottom, top } = scale(state.data);
  const x = (share: number) => PAD.left + share * (WIDTH - PAD.left - PAD.right);
  const y = (cents: number) =>
    PAD.top + (1 - (cents - bottom) / (top - bottom)) * (HEIGHT - PAD.top - PAD.bottom);

  const line = points.map((point) => `${x(point.x)},${y(point.cents)}`).join(" ");
  // The same outline, closed down to the floor of the plot. A bare line on a wide white box
  // reads as an afterthought; the area under it gives the shape something to be the edge of.
  const last = points[points.length - 1].cents;
  const area = `${x(0)},${y(bottom)} ${line} ${x(1)},${y(last)} ${x(1)},${y(bottom)}`;
  const floor = HEIGHT - PAD.bottom;
  // Unique per product: two charts on one page would otherwise share one gradient.
  const fadeId = `price-fade-${productId}`;

  const started = state.data[0].previous_price_cents;
  const ended = state.data[state.data.length - 1];

  // Both ends of the axis say the date - unless every change happened on the same day, in
  // which case printing it twice says nothing twice, and the clock is what tells them
  // apart. It is the ordinary case in a classroom: somebody changes a price three times
  // in one session, and the chart would otherwise read "20 Sept 2026 … 20 Sept 2026".
  // The left end carries the date either way; only the right end changes, so the pair
  // reads "20 Sept 2026, 21:11 … 23:38" instead of the same date printed twice.
  const sameDay = formatDay(state.data[0].changed_at) === formatDay(ended.changed_at);
  const firstLabel = sameDay ? formatDate(state.data[0].changed_at) : formatDay(state.data[0].changed_at);
  const lastLabel = sameDay ? formatTime(ended.changed_at) : formatDay(ended.changed_at);

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
          `Price from ${formatPrice(started)} to ${formatPrice(ended.price_cents)} over ` +
          `${state.data.length} ${state.data.length === 1 ? "change" : "changes"}, ` +
          `between ${formatDate(state.data[0].changed_at)} and ` +
          `${formatDate(ended.changed_at)}.`
        }
      >
        <defs>
          <linearGradient id={fadeId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" className="price-chart-fade-top" />
            <stop offset="100%" className="price-chart-fade-bottom" />
          </linearGradient>
        </defs>

        {/* The two prices that bound the drawing, so the numbers are readable without
            counting pixels - and so the truncated axis cannot be mistaken for one that
            starts at zero. */}
        {[
          { cents: highest, kind: "high" },
          { cents: lowest, kind: "low" },
        ].map(({ cents, kind }) => (
          <g key={cents}>
            <line
              className={`price-chart-grid price-chart-grid-${kind}`}
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={y(cents)}
              y2={y(cents)}
            />
            {/* The number is coloured, and so is the point where the price first reached
                it. That pairing is the whole trick: the eye ties the figure on the axis to
                the moment it happened, without a legend and without another label on top
                of the drawing. */}
            <text
              className={`price-chart-tick price-chart-tick-${kind}`}
              x={PAD.left - 12}
              y={y(cents) + 4}
              textAnchor="end"
            >
              {formatPrice(cents)}
            </text>
          </g>
        ))}

        <polygon className="price-chart-area" points={area} fill={`url(#${fadeId})`} />
        <polyline className="price-chart-line" points={line} />

        {/* One dot per change, at the price it moved TO - not two, which is what the pair
            of points behind each step gives and which doubled the clutter for nothing. */}
        {state.data.map((change, index) => (
          <circle
            key={`${change.changed_at}-${change.price_cents}`}
            className="price-chart-dot"
            cx={x(at(index))}
            cy={y(change.price_cents)}
            r="3.5"
          >
            {/* A native tooltip: no JavaScript and no library, and it puts the exact
                figures within reach without crowding the picture with them. */}
            <title>
              {`${formatDate(change.changed_at)}: ${formatPrice(change.previous_price_cents)} → ${formatPrice(change.price_cents)}`}
            </title>
          </circle>
        ))}

        {/* The cheapest and the dearest this product has ever been, marked where they
            happened. They are the two points somebody actually came to find out - "is this
            a good price?" is answered by where today sits between them - so they are solid
            and coloured while every other change is a hollow dot. Guarded because a row
            whose two prices are equal would make the range collapse. */}
        {lowest !== highest &&
          [
            { cents: lowest, kind: "low", name: "Lowest" },
            { cents: highest, kind: "high", name: "Highest" },
          ].map(({ cents, kind, name }) => {
            // Where it FIRST reached that price, which is the moment worth pointing at.
            const reached = points.find((point) => point.cents === cents)!;
            return (
              <circle
                key={kind}
                className={`price-chart-mark price-chart-mark-${kind}`}
                cx={x(reached.x)}
                cy={y(cents)}
                r="5"
              >
                <title>{`${name} price: ${formatPrice(cents)}`}</title>
              </circle>
            );
          })}

        <text className="price-chart-tick" x={PAD.left} y={floor + 22}>
          {firstLabel}
        </text>
        <text className="price-chart-tick" x={WIDTH - PAD.right} y={floor + 22} textAnchor="end">
          {lastLabel}
        </text>
      </svg>

      <p className="price-history-note">
        Lowest <b className="price-chart-tick-low">{formatPrice(lowest)}</b> · Highest{" "}
        <b className="price-chart-tick-high">{formatPrice(highest)}</b> — axis not from
        zero, so small changes stay visible.
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

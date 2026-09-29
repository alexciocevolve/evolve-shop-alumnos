"""The only file in the shop that knows Stripe exists.

Everything else asks for a checkout and gets back a `Checkout`. That boundary is not
decoration, it buys three things:

  · The tests replace the whole gateway with a function that returns whatever the test
    needs. No network and no Stripe account in CI - not because CI cannot reach the
    internet, it can, but because a test that calls Stripe is testing Stripe's uptime,
    goes red when somebody else has a bad day, and cannot make a card be refused on demand.
  · The rest of the code never learns Stripe's vocabulary. `services.py` does not know what
    a Checkout Session is, and the day this moves to something else it will not care.
  · There is exactly one place to look when something about money goes wrong.

WHAT CHANGED IN OBJECTIVE 17, and it is the whole point of the objective: the shop used to
charge a hardcoded test card from the server and wait for the answer. One call, one answer,
no screen. That was honest for as long as it lasted, and it had one fatal problem - no real
buyer could use it, because nobody was ever asked for a card.

Now the buyer goes to Stripe's own page and types it. Which means the shop stops getting an
answer at all: it hands over a URL and the customer walks away. Everything difficult about
this objective comes from that sentence.

(The old server-side version is not kept here as a comment. It is in the history, at commit
fe89722, which is where old code belongs.)
"""

import stripe

from app.config import PUBLIC_WEB_URL, STRIPE_SECRET_KEY

stripe.api_key = STRIPE_SECRET_KEY

# Euros. The shop has only ever had one currency and the catalogue is priced in it.
CURRENCY = "eur"


class Checkout:
    """What the shop keeps about a checkout it has started. Deliberately tiny.

    `url` is where to send the buyer. `session_id` is what comes back in the return
    address, and the only thread joining a payment over there to an order over here.
    """

    def __init__(self, session_id: str, url: str):
        self.session_id = session_id
        self.url = url


def start_checkout_with_stripe(*, order_id: int, lines: list[dict], customer_email: str) -> Checkout:
    """Create a Checkout Session and return where to send the buyer.

    Nothing is charged here. This only builds the page the customer is about to see; the
    money moves, or does not, minutes later and somewhere else. The shop finds out when the
    browser comes back - which is exactly the weak point this objective is about.

    `lines` carries what is being bought, and this is new. The previous design could not:
    a PaymentIntent takes ONE number and has no concept of lines, so what was bought had to
    travel as a description. A Checkout Session takes real line items, which is what puts
    the product names and quantities on Stripe's own page and on the receipt.

    It also reverses who does the arithmetic. Before, the shop sent a total and Stripe
    charged it blindly; now Stripe ADDS UP the lines, and whatever that sum is, is what the
    customer pays. If our total and our lines ever disagree, the customer is charged
    Stripe's answer and not ours - so the two are compared when the order is confirmed
    rather than trusted.
    """
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=lines,
        # Where Stripe sends the buyer afterwards. {CHECKOUT_SESSION_ID} is a placeholder
        # Stripe fills in - it is not an f-string we forgot, and it must reach Stripe
        # literally.
        # {CHECKOUT_SESSION_ID} is a placeholder Stripe fills in - not an f-string somebody
        # forgot, and it has to reach Stripe literally.
        #
        # The order id is put in by us, and putting it in the address is the naive decision
        # of this objective made visible: it is in the URL bar, the buyer can edit it, and
        # the page that reads it believes it. Somebody will spot that in class before it is
        # explained, which is the best possible outcome.
        success_url=(
            f"{PUBLIC_WEB_URL}/checkout/success"
            f"?order_id={order_id}&session_id={{CHECKOUT_SESSION_ID}}"
        ),
        cancel_url=f"{PUBLIC_WEB_URL}/checkout/cancel",
        # Read back when the buyer returns, and the reason a forged return cannot point at
        # somebody else's order: the session itself says which order it belongs to.
        metadata={"order_id": str(order_id)},
        customer_email=customer_email,
    )
    return Checkout(session_id=session.id, url=session.url)


def fetch_checkout_with_stripe(session_id: str) -> dict:
    """Ask Stripe what really happened in a session. Used when the buyer comes back.

    Deliberately NOT used yet by the code that marks an order paid - that code believes the
    browser instead, which is the naive version this objective builds on purpose and the
    next one takes apart. This function exists because the tests of those failures need it.
    """
    session = stripe.checkout.Session.retrieve(session_id)
    return {
        # "paid" | "unpaid" | "no_payment_required"
        "payment_status": session.payment_status,
        "amount_total": session.amount_total,
        "payment_intent": session.payment_intent,
        "order_id": session.metadata.get("order_id"),
    }


def get_gateway():
    """FastAPI dependency, and the seam the tests pull on.

    It exists so that `app.dependency_overrides[get_gateway]` can hand the routes a
    different object - the same trick conftest.py already plays with get_db. Without this
    indirection the only way to test a checkout would be a real key and a real network.
    """
    return Gateway(start=start_checkout_with_stripe, fetch=fetch_checkout_with_stripe)


class Gateway:
    """The two functions the shop needs, handed over together.

    One object instead of two dependencies because they always travel as a pair: whoever
    starts a checkout is going to have to ask how it ended.
    """

    def __init__(self, start, fetch):
        self.start = start
        self.fetch = fetch

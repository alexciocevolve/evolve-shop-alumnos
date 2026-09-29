"""The only file in the shop that knows Stripe exists.

Everything else asks for a `charge` and gets back a `Charge` or a `PaymentDeclined`. That
boundary is not decoration, it buys three things:

  · The tests replace the whole gateway with a function that returns whatever the test
    needs. No network, no Stripe account, no keys in CI - which matters because CI has no
    internet, the same rule the e2e tests already live by.
  · The rest of the code never learns Stripe's vocabulary. `services.py` does not know what
    a PaymentIntent is, and when a later phase moves to a different flow, it will not care.
  · There is exactly one place to look when something about money goes wrong.

WHAT THIS DOES *NOT* DO YET, and both are on purpose:
  · It charges a HARDCODED TEST CARD. No real buyer can use this shop yet - there is no
    payment screen, because building one is a later phase. Say so in class: this is a
    scaffold, and it is the second lie the shop tells after the one phase 0 found.
  · It refuses anything that needs the customer to do something (3D Secure). See
    error_on_requires_action below.
"""

import stripe

from app.config import STRIPE_SECRET_KEY

stripe.api_key = STRIPE_SECRET_KEY

# The card. Stripe publishes ready-made test payment methods so a server can charge
# without ever touching a card number - which is the only reason this file can exist
# without dragging PCI compliance into a teaching project.
#
# `pm_card_visa` always succeeds. Its siblings are the whole failure catalogue and the
# tests use them by name: pm_card_visa_chargeDeclined, ...InsufficientFunds, ...LostCard,
# ...StolenCard, pm_card_chargeDeclinedExpiredCard, ...IncorrectCvc, ...ProcessingError.
TEST_PAYMENT_METHOD = "pm_card_visa"

# Euros. The shop has only ever had one currency and the catalogue is priced in it.
CURRENCY = "eur"


class PaymentDeclined(Exception):
    """The gateway said no, and the shop has to tell somebody why.

    Carries the message Stripe gave, which is already written for a human. It is NOT the
    right exception for "Stripe was unreachable": that is not a decline, it is an unknown
    outcome, and the difference is the whole of the next phase.
    """


class Charge:
    """What the shop keeps about a payment. Deliberately tiny.

    Two fields, and the second one is the interesting one: the amount Stripe says it
    charged, not the amount we asked for. They are always equal today, and checking that
    they are is how the shop would notice if they ever stopped being.
    """

    def __init__(self, payment_intent_id: str, amount_cents: int):
        self.payment_intent_id = payment_intent_id
        self.amount_cents = amount_cents


def charge_with_stripe(
    *,
    amount_cents: int,
    description: str,
    metadata: dict[str, str],
    receipt_email: str,
) -> Charge:
    """Charge the card and WAIT. Returns on success, raises PaymentDeclined on refusal.

    One call, one answer, no webhook and no redirect - which is what makes this phase
    small enough to read in one sitting, and what the next phase takes apart.

    The three parameters that make it behave that way:

    `confirm=True` creates and charges in the same request, instead of creating something
    the customer then has to confirm from a browser.

    `payment_method_types=["card"]` says what this shop accepts instead of letting the
    Stripe Dashboard decide. Two things follow: nothing that needs a redirect can be
    chosen - there is nowhere to redirect from, this shop has no payment screen - and the
    next parameter becomes legal at all. See the note beside it.

    `error_on_requires_action=True` is the one worth stopping on. Without it, a card that
    needs 3D Secure comes back with status `requires_action` - neither a yes nor a no -
    and this code would have nowhere to put it. With it, Stripe turns that third answer
    into a plain error. Its own documentation says this is for "simpler integrations that
    don't handle customer actions", which is an honest description of what this is.
    Europe is exactly where that matters: under SCA, needing authentication is the normal
    case, not the odd one. So this line is the phase's boundary, written down.
    """
    try:
        intent = stripe.PaymentIntent.create(
            # The amount is an integer, in cents, and it comes from the order. Never from
            # the browser - that decision was made in objective 12, when POST /orders was
            # left with no body at all, and this is the day it gets paid for.
            amount=amount_cents,
            currency=CURRENCY,
            # Stripe has no concept of lines. `amount` is one number, and what is being
            # bought travels as text: `description` is shown to the buyer on the receipt
            # Stripe sends, `metadata` is for us and for the dashboard and is never shown.
            #
            # Worth naming in class: STRIPE CHARGES A NUMBER, THE LINES ARE OURS. If the
            # total and the lines disagree, Stripe does not notice - it charges whatever
            # it was told. That is why the total is computed from order_items.
            description=description,
            metadata=metadata,
            receipt_email=receipt_email,
            payment_method=TEST_PAYMENT_METHOD,
            # This shop takes cards. Said here, in code, and not left to the account's
            # settings - which is not a style preference, it is the only way the next line
            # is allowed to exist.
            #
            # The first version used automatic_payment_methods, where Stripe picks from
            # whatever is ticked in the Dashboard. Against a real key it failed:
            #
            #   InvalidRequestError: The `error_on_requires_action` parameter can't be used
            #   with PaymentIntents which use payment methods managed through the Dashboard
            #
            # Which is a lesson on its own, and an uncomfortable one: a checkbox on a web
            # page, in nobody's repository and in nobody's review, decided which arguments
            # this function was allowed to pass. Naming the types takes that decision back
            # into the code, where it can be read and diffed.
            #
            # It also makes the old allow_redirects="never" unnecessary. That existed to
            # stop Stripe choosing a payment method that sends the customer to another
            # site; with only "card" on the list there is nothing to choose.
            payment_method_types=["card"],
            confirm=True,
            error_on_requires_action=True,
        )
    except stripe.CardError as e:
        # The card was refused. Stripe's message is already written for a person
        # ("Your card has insufficient funds.") so it goes straight through.
        raise PaymentDeclined(e.user_message or str(e)) from e

    if intent.status != "succeeded":
        # Should not happen with the parameters above, and that is exactly why it is
        # checked. A gateway that answers something unexpected must not be read as a yes.
        raise PaymentDeclined(f"The payment ended as {intent.status}, not succeeded")

    return Charge(payment_intent_id=intent.id, amount_cents=intent.amount)


def get_gateway():
    """FastAPI dependency, and the seam the tests pull on.

    It exists so that `app.dependency_overrides[get_gateway]` can hand the routes a
    different function - the same trick conftest.py already plays with get_db. Without
    this indirection the only way to test a declined card would be to have a real key and
    a real network in CI, and there is neither.
    """
    return charge_with_stripe

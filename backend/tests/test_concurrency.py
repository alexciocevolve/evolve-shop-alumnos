"""Two buyers going for the last unit at the same time.

This is the one test that cannot use the rollback harness. Concurrency means two
transactions that can see each other's commits, and the `db` fixture deliberately gives
every test a single transaction that is thrown away - inside it, two "buyers" would just
be one transaction talking to itself, and the test would pass with the lock removed.

So this one commits for real, which brings two obligations the other tests do not have:
it must touch nothing the other tests rely on, and it must clear up after itself even
when it fails. Both are handled in the fixture below.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app import services
from app.models import Order, Product, User
from app.schemas import AddressIn
from tests.conftest import PASSWORD

EMAIL = "race@example.com"


@pytest.fixture
def committed_world(engine):
    """A buyer with an address and a product of its own, with one unit left.

    A product of its own, and not one of the 36 from the seed data, on purpose. Changing
    a seed product's stock here would mean putting it back afterwards, and the day that
    restoring step fails every other test starts from a shop that is quietly wrong. This
    way there is nothing to restore: everything this test touches, it also created.
    """
    with Session(engine) as setup:
        category_id = setup.execute(
            text("SELECT id FROM categories WHERE name = 'laptops'")
        ).scalar()
        product = Product(
            name="Race Test Laptop",
            description="Only used by the concurrency test.",
            category_id=category_id,
            price_cents=100000,
            stock=1,  # the last unit
            image_url="/images/product-1.jpg",
        )
        setup.add(product)
        setup.flush()

        user = services.register_user(setup, EMAIL, PASSWORD, "Race")
        services.save_address(
            setup,
            user,
            is_billing=False,
            data=AddressIn(
                recipient_name="Race", street="Calle 1", city="Madrid", postal_code="28001"
            ),
        )
        carts = [services.create_cart(setup) for _ in range(2)]
        for cart in carts:
            services.set_cart_item(setup, cart, product.id, 1)
        setup.commit()
        user_id, product_id = user.id, product.id
        tokens = [cart.token for cart in carts]

    yield user_id, product_id, tokens

    # Plain SQL, not the ORM. A cleanup written with the models stops working the moment
    # a model changes - and then a failing test leaves committed rows behind and every
    # later run starts from a dirty database. This has to be the most boring code here.
    with Session(engine) as cleanup:
        cleanup.execute(
            text(
                "DELETE FROM order_items WHERE order_id IN"
                " (SELECT id FROM orders WHERE user_id = :u)"
            ),
            {"u": user_id},
        )
        cleanup.execute(text("DELETE FROM orders WHERE user_id = :u"), {"u": user_id})
        cleanup.execute(
            text("DELETE FROM cart_items WHERE product_id = :p"), {"p": product_id}
        )
        cleanup.execute(
            text("DELETE FROM carts WHERE token = ANY(:t)"), {"t": list(tokens)}
        )
        cleanup.execute(text("DELETE FROM sessions WHERE user_id = :u"), {"u": user_id})
        cleanup.execute(text("DELETE FROM addresses WHERE user_id = :u"), {"u": user_id})
        cleanup.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        cleanup.execute(text("DELETE FROM products WHERE id = :p"), {"p": product_id})
        cleanup.commit()


@pytest.fixture
def both_read_before_either_writes(engine, committed_world):
    """Hold each checkout at the door until the other one is there too.

    Without this the two threads simply take turns: the first finishes in under a
    millisecond and the second starts afterwards, so there is no overlap, nothing races,
    and the test passes just as happily with the lock taken out - which would make it
    worthless. The barrier sits immediately BEFORE the statement that reads the stock, so
    both transactions are really trying to buy the same unit at the same moment.
    """
    barrier = threading.Barrier(2, timeout=10)
    already_waited: set[int] = set()
    lock = threading.Lock()

    def wait_for_the_other_buyer(conn, cursor, statement, parameters, context, executemany):
        if "FROM products" not in statement or " IN (" not in statement:
            return
        with lock:
            if threading.get_ident() in already_waited:
                return
            already_waited.add(threading.get_ident())
        barrier.wait()

    event.listen(engine, "before_cursor_execute", wait_for_the_other_buyer)
    yield
    event.remove(engine, "before_cursor_execute", wait_for_the_other_buyer)


def checkout(engine, user_id: int, token: str) -> str:
    """Run one whole checkout in its own session, and report what happened."""
    with Session(engine) as session:
        try:
            services.create_order(
                session, services.get_cart(session, token), session.get(User, user_id)
            )
            return "sold"
        except ValueError:
            return "refused"


def test_two_buyers_and_one_unit_means_one_sale(
    committed_world, both_read_before_either_writes, engine
):
    user_id, product_id, tokens = committed_world

    # Both start before either finishes. SELECT ... FOR UPDATE makes the second wait on
    # the first; when it wakes up it re-reads the row under the lock and sees no stock.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(lambda t: checkout(engine, user_id, t), tokens))

    assert results == ["refused", "sold"], f"both buyers got through: {results}"

    with Session(engine) as check:
        # The number that matters. Without the lock this goes to -1, which is a laptop the
        # shop does not have and has already taken the money for.
        assert check.get(Product, product_id).stock == 0
        assert check.query(Order).filter(Order.user_id == user_id).count() == 1

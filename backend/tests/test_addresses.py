"""Addresses are never edited: changing one retires a row and writes another. These tests
are what stops somebody "simplifying" that back into an UPDATE."""

import pytest
from sqlalchemy.exc import IntegrityError

from app import services
from app.models import Address
from app.schemas import AddressIn

MADRID = AddressIn(
    recipient_name="Ana Torres", street="Calle Mayor 1", city="Madrid", postal_code="28013"
)
VALENCIA = AddressIn(
    recipient_name="Ana Torres",
    street="Avenida del Puerto 7",
    city="Valencia",
    postal_code="46021",
)


def test_saving_an_address_makes_it_the_active_one(db, user):
    saved = services.save_address(db, user, is_billing=False, data=MADRID)

    assert saved.is_active is True
    assert saved.is_billing is False
    assert services.get_active_address(db, user, is_billing=False).id == saved.id


def test_the_country_is_stored_in_upper_case(db, user):
    lower = AddressIn(
        recipient_name="A", street="B", city="C", postal_code="D", country="es"
    )
    # Otherwise the table ends up holding es, ES and Es, all meaning the same place.
    assert services.save_address(db, user, is_billing=False, data=lower).country == "ES"


def test_changing_an_address_writes_a_new_row_and_retires_the_old_one(db, user):
    first = services.save_address(db, user, is_billing=False, data=MADRID)

    second = services.save_address(db, user, is_billing=False, data=VALENCIA)

    assert second.id != first.id, "an UPDATE would have kept the same id"
    db.expire_all()
    assert db.get(Address, first.id).is_active is False
    assert db.get(Address, first.id).street == "Calle Mayor 1"  # the old one is unchanged
    assert second.is_active is True


def test_an_order_keeps_the_address_it_was_sent_to_after_the_customer_moves(db, user):
    services.save_address(db, user, is_billing=False, data=MADRID)
    cart = services.create_cart(db)
    services.set_cart_item(db, cart, 1, 1)
    order = services.create_order(db, cart, user)

    services.save_address(db, user, is_billing=False, data=VALENCIA)

    db.expire_all()
    reread = services.get_order(db, order.id, user)
    # Pointing at a row that never changes does the same job the copied price does in
    # order_items, from the other direction.
    assert reread.shipping_address.city == "Madrid"
    assert services.get_active_address(db, user, is_billing=False).city == "Valencia"


def test_only_the_addresses_in_use_are_listed(db, user):
    services.save_address(db, user, is_billing=False, data=MADRID)
    services.save_address(db, user, is_billing=False, data=VALENCIA)
    services.save_address(db, user, is_billing=True, data=MADRID)

    listed = services.list_addresses(db, user)

    assert len(listed) == 2  # one shipping, one billing; the retired one is nobody's business
    assert {a.is_billing for a in listed} == {False, True}
    assert all(a.is_active for a in listed)
    # Shipping first, so the account page always shows them in the same order.
    assert [a.is_billing for a in listed] == [False, True]


def test_shipping_and_billing_do_not_overwrite_each_other(db, user):
    shipping = services.save_address(db, user, is_billing=False, data=MADRID)
    billing = services.save_address(db, user, is_billing=True, data=VALENCIA)

    assert shipping.id != billing.id
    assert services.get_active_address(db, user, is_billing=False).city == "Madrid"
    assert services.get_active_address(db, user, is_billing=True).city == "Valencia"


def test_the_database_refuses_a_second_active_address_of_the_same_kind(db, user):
    services.save_address(db, user, is_billing=False, data=MADRID)

    # Straight past the service, which would have retired the first one. This is what the
    # partial unique index is for: the rule holds even when the code forgets it.
    db.add(
        Address(
            user_id=user.id,
            is_billing=False,
            is_active=True,
            recipient_name="X",
            street="X",
            city="X",
            postal_code="X",
        )
    )
    with pytest.raises(IntegrityError, match="uq_addresses_one_active"):
        db.flush()
    db.rollback()


def test_any_number_of_retired_addresses_is_fine(db, user):
    # The other half of the same index: it is unique only WHERE is_active.
    for _ in range(5):
        services.save_address(db, user, is_billing=False, data=MADRID)

    assert db.query(Address).filter(Address.user_id == user.id).count() == 5
    assert len(services.list_addresses(db, user)) == 1


def test_deleting_an_address_retires_it_instead_of_removing_the_row(db, user):
    saved = services.save_address(db, user, is_billing=False, data=MADRID)

    assert services.deactivate_address(db, user, is_billing=False) is True

    db.expire_all()
    assert services.list_addresses(db, user) == []
    # The row stays, because an order may point at it and the foreign key exists to stop
    # that order losing the address it was sent to.
    assert db.get(Address, saved.id) is not None


def test_deleting_an_address_that_is_not_there_says_so(db, user):
    assert services.deactivate_address(db, user, is_billing=False) is False


def test_one_person_never_sees_anothers_addresses(db, user, other_user):
    services.save_address(db, user, is_billing=False, data=MADRID)

    assert services.list_addresses(db, other_user) == []
    assert services.get_active_address(db, other_user, is_billing=False) is None


def test_deleting_a_user_takes_their_addresses_with_them(db, user):
    services.save_address(db, user, is_billing=False, data=MADRID)
    db.delete(user)
    db.commit()

    assert db.query(Address).count() == 0

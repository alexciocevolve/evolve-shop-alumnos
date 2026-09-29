"""Passwords. The only module with no database at all, so these are unit tests in the
strictest sense: a function, an argument, an answer."""

from app.security import DUMMY_HASH, hash_password, verify_password

PASSWORD = "correct horse battery staple"


def test_the_stored_value_does_not_contain_the_password():
    stored = hash_password(PASSWORD)
    assert PASSWORD not in stored
    # Nor any recognisable part of it, which is what "cannot be turned back" means.
    for word in PASSWORD.split():
        assert word not in stored


def test_the_stored_value_says_which_algorithm_made_it():
    algorithm, salt, digest = hash_password(PASSWORD).split("$")
    assert algorithm == "scrypt"
    assert len(salt) == 32  # 16 random bytes in hex
    assert len(digest) == 64  # 32 bytes in hex
    # The name travels with the row so that the day this becomes argon2, the old rows can
    # still be recognised and upgraded as people sign in.


def test_the_right_password_verifies():
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


def test_a_wrong_password_does_not():
    stored = hash_password(PASSWORD)
    assert verify_password("wrong", stored) is False
    assert verify_password("", stored) is False
    assert verify_password(PASSWORD + " ", stored) is False  # not even by one space


def test_the_same_password_twice_gives_two_different_hashes():
    # Because of the salt. Without it, two people who chose the same password would be
    # visibly the same in the table, and one precomputed table would open both accounts.
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second
    assert verify_password(PASSWORD, first)
    assert verify_password(PASSWORD, second)


def test_a_row_that_is_not_a_hash_is_refused_rather_than_crashing():
    # Whatever ends up in that column - a truncated value, something from an old format,
    # an empty string - has to answer "no", not raise and turn into a 500.
    for stored in ["", "not-a-hash", "scrypt$only-two-parts", "scrypt$zz$zz", "a$b$c$d"]:
        assert verify_password(PASSWORD, stored) is False


def test_an_unknown_algorithm_is_refused():
    algorithm, salt, digest = hash_password(PASSWORD).split("$")
    assert verify_password(PASSWORD, f"md5${salt}${digest}") is False


def test_the_dummy_hash_is_a_real_hash_that_nothing_matches():
    # login() checks against this when the email is not registered, so that answering
    # "no such account" takes as long as answering "wrong password".
    assert DUMMY_HASH.startswith("scrypt$")
    assert verify_password("", DUMMY_HASH) is False
    assert verify_password(PASSWORD, DUMMY_HASH) is False

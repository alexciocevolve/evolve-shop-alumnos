import hashlib
import hmac
import os

# Only the standard library. In production the usual choice is bcrypt or argon2, which are
# maintained by people who do this for a living; scrypt is here because it comes with
# Python and the point is to see what is going on, not to invent cryptography.

# Cost parameters. n is the work factor: raising it makes every attempt slower, for us and
# for anyone trying to guess. 2**14 with r=8 needs about 16 MB of memory per attempt, which
# is what makes guessing with graphics cards expensive.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LENGTH = 32


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=KEY_LENGTH,
        maxmem=64 * 1024 * 1024,
    )


def hash_password(plain: str) -> str:
    """Turn a password into something safe to store. There is no way back."""
    # A different random salt per user, so two people with the same password get two
    # different hashes, and a table of pre-computed hashes is of no use to anyone.
    salt = os.urandom(16)
    # The salt is stored next to the hash: it is not a secret, it only has to be unique.
    # The algorithm name is stored too, so the day this moves to argon2 the old rows can
    # still be recognised and upgraded as people sign in.
    return f"scrypt${salt.hex()}${_derive(plain, salt).hex()}"


def verify_password(plain: str, stored: str) -> bool:
    """Say whether this password produces the stored hash."""
    try:
        algorithm, salt_hex, hash_hex = stored.split("$")
        if algorithm != "scrypt":
            return False
        expected = bytes.fromhex(hash_hex)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False  # a row that is not in our format is not a password anyone can use

    # compare_digest, not ==. A normal comparison stops at the first byte that differs, so
    # how long it takes leaks how much of the guess was right; this one always takes the
    # same time. It matters less here than in the days of dial-up, and it costs nothing.
    return hmac.compare_digest(_derive(plain, salt), expected)


# A hash of a random string nobody will ever type, worked out once when the app starts.
# login() checks the password against this when the email is not registered, so that
# answering "no such account" takes just as long as answering "wrong password". Without
# it, the difference in timing is enough to find out who has an account in this shop.
DUMMY_HASH = hash_password(os.urandom(16).hex())

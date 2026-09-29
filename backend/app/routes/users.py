from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.models import Address, User
from app.observability import fingerprint, log
from app.schemas import AddressIn, LoginIn, UserIn

router = APIRouter(tags=["users"])


def _bearer_token(authorization: str | None) -> str:
    # "Authorization: Bearer <token>". Anything else is not a sign-in attempt we can read.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid or expired token")
    return authorization.removeprefix("Bearer ")


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    # A missing header is answered with 401 and not with the 422 that a required header
    # would give: "you are not signed in" is the honest answer, not "your request is
    # malformed". The message is the same whether the token is unknown or simply old,
    # because the difference is of no use to the person asking.
    token = _bearer_token(authorization)
    user = services.get_user_by_session(db, token)
    if user is None:
        # An old token (a session lasts 24 hours) or a made-up one. The browser forgets
        # the token after this answer, so one of these per person now and then is normal.
        # Hundreds of them, each with a different fingerprint, are not.
        log.info(
            "session rejected",
            extra={
                "event.action": "user.session",
                "event.outcome": "failure",
                "shop.session_ref": fingerprint(token),
            },
        )
        raise HTTPException(401, "Invalid or expired token")
    return user


def user_to_dict(user: User) -> dict:
    # password_hash is not here, and it never will be. It is not needed on any screen, and
    # what is never sent cannot leak through a screenshot, a log or a cached response.
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "created_at": user.created_at.isoformat(),
    }


@router.post("/users", status_code=201)
def register(body: UserIn, db: Session = Depends(get_db)):
    user = services.register_user(db, body.email, body.password, body.full_name)
    if user is None:
        # The email is not written here either. The reason is enough to count how often
        # people try to register twice, which usually means they forgot they had an account.
        log.warning(
            "registration refused",
            extra={
                "event.action": "user.register",
                "event.outcome": "failure",
                "event.reason": "email_taken",
            },
        )
        raise HTTPException(409, f"Email {body.email} is already registered")

    log.info(
        f"user {user.id} registered",
        extra={"event.action": "user.register", "event.outcome": "success", "user.id": user.id},
    )
    return user_to_dict(user)


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    session = services.login(db, body.email, body.password)
    if session is None:
        # Deliberately the same sentence whether the email is unknown or the password is
        # wrong. Saying "no account with that email" turns the login form into a way of
        # finding out who is registered here.
        raise HTTPException(401, "Invalid email or password")
    return {"token": session.token}


@router.post("/logout", status_code=204)
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    token = _bearer_token(authorization)
    services.logout(db, token)
    # The same fingerprint as in the user.login line, so the two can be matched and the
    # length of the visit worked out.
    log.info(
        "signed out",
        extra={"event.action": "user.logout", "shop.session_ref": fingerprint(token)},
    )


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_to_dict(user)


def address_to_dict(address: Address) -> dict:
    return {
        "id": address.id,
        # The API says "shipping" / "billing" rather than a true/false that the reader has
        # to decode. The column is a boolean because two kinds is all there is; the answer
        # is a word because that is what the screen and the address bar are made of.
        "kind": "billing" if address.is_billing else "shipping",
        "recipient_name": address.recipient_name,
        "street": address.street,
        "city": address.city,
        "postal_code": address.postal_code,
        "country": address.country,
    }


@router.get("/me/addresses")
def list_addresses(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [address_to_dict(a) for a in services.list_addresses(db, user)]


@router.put("/me/addresses/{kind}")
def save_address(
    # Literal, so FastAPI itself refuses anything that is not one of the two kinds and
    # answers 422 before our code runs. No hand-written check, and it shows up in /docs.
    kind: Literal["shipping", "billing"],
    body: AddressIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    # PUT and not POST: it sets what the address at this slot IS. Sending it twice leaves
    # the same address, and the caller does not have to know whether one existed already.
    address = services.save_address(db, user, kind == "billing", body)

    # An address is the most personal thing this shop keeps: name, street and postcode
    # point to one house. None of that goes in the log. The country is kept because it is
    # useful (where do our customers live?) and says nothing about who they are.
    log.info(
        f"{kind} address saved",
        extra={
            "event.action": "user.address.save",
            "user.id": user.id,
            "shop.address_kind": kind,
            "shop.address_country": address.country,
        },
    )
    return address_to_dict(address)


@router.delete("/me/addresses/{kind}", status_code=204)
def delete_address(
    kind: Literal["shipping", "billing"],
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not services.delete_address(db, user, kind == "billing"):
        raise HTTPException(404, f"No {kind} address to delete")
    log.info(
        f"{kind} address deleted",
        extra={"event.action": "user.address.delete", "user.id": user.id, "shop.address_kind": kind},
    )

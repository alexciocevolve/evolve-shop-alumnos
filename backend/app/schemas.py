from pydantic import BaseModel, EmailStr, Field


class QuantityIn(BaseModel):
    # ge=1 means a request asking for zero units is rejected by FastAPI before any of our
    # code runs, with a 422. Removing a line is what DELETE is for, not a quantity of zero.
    quantity: int = Field(ge=1)


class UserIn(BaseModel):
    email: EmailStr
    # The one rule worth enforcing on the server: length. Demanding symbols and capitals
    # mostly produces "Password1!", which is shorter and easier to guess than a long
    # phrase. The client shows this same minimum so nobody finds out by being rejected.
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)


class LoginIn(BaseModel):
    email: EmailStr
    # No min_length here on purpose: rejecting a short password at sign-in would say
    # "that is not even the right shape", which is one more thing a guesser learns.
    password: str


class AddressIn(BaseModel):
    recipient_name: str = Field(min_length=1)
    street: str = Field(min_length=1)
    city: str = Field(min_length=1)
    postal_code: str = Field(min_length=1)
    # Two letters, ISO 3166-1: "ES", "PT", "FR". Storing the country as free text is how
    # a table ends up holding Spain, España, ESP and es all meaning the same place.
    country: str = Field(default="ES", min_length=2, max_length=2)

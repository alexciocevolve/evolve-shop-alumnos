from pydantic import BaseModel, Field


class QuantityIn(BaseModel):
    # ge=1 means a request asking for zero units is rejected by FastAPI before any of our
    # code runs, with a 422. Removing a line is what DELETE is for, not a quantity of zero.
    quantity: int = Field(ge=1)

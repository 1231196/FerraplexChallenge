from datetime import date

from pydantic import BaseModel, Field


class OrderLine(BaseModel):
    reference: str
    quantity: int


class ExtractionIssue(BaseModel):
    type: str
    message: str


class ExtractedOrder(BaseModel):
    customer_name: str | None = None
    customer_email: str
    requested_delivery_date: date | None = None
    lines: list[OrderLine] = Field(default_factory=list)
    issues: list[ExtractionIssue] = Field(default_factory=list)

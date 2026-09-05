"""Invoice schema definition."""
from pydantic import BaseModel, Field


class InvoiceData(BaseModel):
    """Structured fields extracted from an invoice document."""
    company_name: str = Field(
        ...,
        description="Name of the vendor, issuer, or company issuing the invoice"
    )
    invoice_number: str = Field(
        ...,
        description="Unique identifier or reference number of the invoice"
    )
    date: str = Field(
        ...,
        description="Invoice billing date in ISO 8601 format (YYYY-MM-DD)"
    )
    customer_name: str = Field(
        ...,
        description="Name of client or customer being billed"
    )
    amount: float = Field(
        ...,
        description="Total invoice monetary amount due"
    )
    currency: str = Field(
        default="USD",
        description="Three-letter ISO currency code or currency symbol (e.g. USD, EUR, GBP)"
    )

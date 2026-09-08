"""Invoice schema definition."""
from pydantic import BaseModel, Field


# Plain-English: Defines the data blueprint (schema) for an invoice.
# It ensures every extracted invoice contains a vendor name, invoice number,
# billing date, customer name, total amount, and currency.
class InvoiceData(BaseModel):
    """Structured fields extracted from an invoice, billing statement, or commercial invoice document."""
    company_name: str = Field(
        ...,
        description="Name of the vendor, issuer, seller, shipper, or exporter company issuing the invoice"
    )
    invoice_number: str = Field(
        ...,
        description="Unique identifier, invoice number, statement number, or reference code"
    )
    date: str = Field(
        ...,
        description="Invoice billing date in ISO 8601 format (YYYY-MM-DD)"
    )
    customer_name: str = Field(
        ...,
        description="Name of client, customer, buyer, or consignee being billed"
    )
    amount: float = Field(
        ...,
        description="Total invoice monetary amount due, payable, or billed"
    )
    currency: str = Field(
        default="USD",
        description="Three-letter ISO currency code or currency symbol (e.g. USD, EUR, GBP, JPY)"
    )


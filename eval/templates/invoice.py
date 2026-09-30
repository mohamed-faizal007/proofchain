from __future__ import annotations

from templates.base import Section, TypeDef

TYPE = TypeDef(
    name="invoice",
    title="Tax Invoice",
    party_kind="company",
    header=(
        ("line", "Invoice number {ref} dated {date}."),
        ("line", "Billed by {party_a}, {address}, {city}."),
        ("line", "Billed to {party_b}."),
    ),
    sections=(
        Section(
            "Charges",
            (
                "{item} for {num} units at {amount} per unit, payable in full.",
                "{item} delivered on {date}, charged at {amount}.",
                "Additional {item} for {months} months at {amount} per month.",
                "Handling fee of {pct} applied to {item} supplied on {date}.",
            ),
        ),
        Section(
            "Taxes and totals",
            (
                "GST at {pct} is charged on the taxable value of {amount}.",
                "The total amount payable is {amount}, due on {date}.",
                "A late fee of {pct} per month shall apply after {days} days.",
            ),
        ),
        Section(
            "Payment terms",
            (
                "Payment must be made by bank transfer to {party_a} within {days} days of the "
                "invoice date.",
                "The Buyer may dispute a charge in writing within {days} days of receipt.",
                "Goods remain the property of the Seller until {amount} has been received.",
                "Queries about this invoice should quote reference {ref}.",
            ),
        ),
    ),
    closing=(("signature", "Authorised signatory for {party_a}"),),
)

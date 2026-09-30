from __future__ import annotations

from templates.base import Section, TypeDef
from templates.common import GENERAL

TYPE = TypeDef(
    name="lease",
    title="Residential Lease Agreement",
    party_kind="person",
    header=(
        (
            "line",
            "This Lease Agreement is made on {date} between {party_a} (the Landlord) and "
            "{party_b} (the Tenant).",
        ),
        ("line", "The premises are situated at {address}, {city} (the Premises)."),
    ),
    sections=(
        Section(
            "Term and possession",
            (
                "The Landlord shall let the Premises to the Tenant for a term of {months} months "
                "commencing on {date}.",
                "The Tenant shall take possession on {date} and may renew this lease for a further "
                "{months} months by giving {days} days written notice.",
                "The Landlord must hand over the Premises in habitable condition together with "
                "{num} sets of keys.",
                "Holding over after the term shall be treated as a monthly tenancy at a rent "
                "increased by {pct}.",
            ),
        ),
        Section(
            "Rent and deposit",
            (
                "The Tenant shall pay monthly rent of {amount} on or before the {num} day of each "
                "calendar month.",
                "The Tenant shall pay a refundable security deposit of {amount} on {date}, "
                "without interest.",
                "The rent shall increase by {pct} at each renewal of the lease.",
                "Late payment shall attract interest at {pct} per annum on the overdue amount "
                "after {days} days.",
                "The Landlord may deduct from the deposit the cost of damage beyond ordinary wear, "
                "not exceeding {amount}.",
            ),
        ),
        Section(
            "Use and maintenance",
            (
                "The Tenant shall use the Premises for residential purposes only and must not "
                "sublet any part without the Landlord's written consent.",
                "The Tenant shall keep the Premises clean and shall bear routine repairs costing "
                "less than {amount}.",
                "The Landlord shall bear structural repairs and must complete them within "
                "{days} days of notice.",
                "The Tenant may keep no more than {num} occupants in the Premises at any time.",
                "The Landlord may inspect the Premises on {days} hours notice at reasonable times.",
            ),
        ),
        Section(
            "Termination",
            (
                "Either party may terminate this lease by giving {days} days written notice after "
                "the first {months} months.",
                "The Landlord may terminate immediately if the Tenant fails to pay rent for "
                "{num} consecutive months.",
                "On termination the Tenant shall vacate the Premises and return all keys within "
                "{days} days.",
                "The Landlord shall refund the deposit within {days} days after vacant possession, "
                "less lawful deductions.",
            ),
        ),
        *GENERAL,
    ),
    closing=(
        ("line", "Signed on {date} at {city}."),
        ("signature", "Landlord: {party_a}"),
        ("signature", "Tenant: {party_b}"),
    ),
)

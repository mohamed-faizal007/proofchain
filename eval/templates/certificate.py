from __future__ import annotations

from templates.base import Section, TypeDef

TYPE = TypeDef(
    name="certificate",
    title="Certificate of Completion",
    party_kind="person",
    header=(
        ("line", "This is to certify that {party_a} has successfully completed the programme."),
        ("line", "Awarded by {party_b} at {city} on {date}, certificate number {ref}."),
    ),
    sections=(
        Section(
            "Programme details",
            (
                "The holder completed {num} modules over {months} months and scored an aggregate "
                "of {pct}.",
                "The programme comprised {days} days of supervised practice at {city}.",
                "The fee of {amount} was received in full on {date}.",
            ),
        ),
        Section(
            "Conditions of validity",
            (
                "This certificate is valid for {months} months from {date} and may be renewed on "
                "application.",
                "The issuing body shall verify this certificate on written request within {days} "
                "days.",
                "The holder must not alter, copy or transfer this certificate.",
                "The certificate shall be void if obtained by misrepresentation.",
            ),
        ),
    ),
    closing=(("signature", "Registrar, {party_b}"),),
)

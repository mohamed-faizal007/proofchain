from __future__ import annotations

from templates.base import Section, TypeDef
from templates.common import GENERAL

TYPE = TypeDef(
    name="nda",
    title="Non-Disclosure Agreement",
    party_kind="company",
    header=(
        (
            "line",
            "This Non-Disclosure Agreement is made on {date} between {party_a} (the Disclosing "
            "Party) and {party_b} (the Receiving Party).",
        ),
        ("line", "The Parties wish to discuss a potential business relationship in {city}."),
    ),
    sections=(
        Section(
            "Confidential information",
            (
                "Confidential Information means all technical, commercial and financial "
                "information disclosed by the Disclosing Party on or after {date}.",
                "Information that is public, independently developed or lawfully received from a "
                "third party is not Confidential Information.",
                "The Disclosing Party shall mark written material as confidential where "
                "practicable, but failure to mark does not remove protection.",
            ),
        ),
        Section(
            "Obligations of the Receiving Party",
            (
                "The Receiving Party shall use Confidential Information solely to evaluate the "
                "proposed relationship.",
                "The Receiving Party must protect Confidential Information with at least the care "
                "it uses for its own, and no less than reasonable care.",
                "The Receiving Party may share Confidential Information only with the {num} "
                "employees who need it and who are bound by written duties.",
                "The Receiving Party shall notify the Disclosing Party within {days} days of any "
                "unauthorised disclosure.",
                "The Receiving Party must not copy Confidential Information except as strictly "
                "needed for the permitted purpose.",
            ),
        ),
        Section(
            "Term and return",
            (
                "The obligations in this Agreement shall continue for {months} months from {date}.",
                "On request the Receiving Party shall return or destroy all Confidential "
                "Information within {days} days.",
                "Either Party may end discussions at any time by written notice without liability "
                "other than for prior breach.",
            ),
        ),
        Section(
            "Remedies",
            (
                "The Receiving Party acknowledges that breach may cause irreparable harm and that "
                "the Disclosing Party may seek injunctive relief.",
                "The Receiving Party shall pay liquidated damages of {amount} for each proven "
                "unauthorised disclosure.",
                "Nothing in this Agreement grants a licence to any intellectual property of either "
                "Party.",
            ),
        ),
        *GENERAL,
    ),
    closing=(
        ("line", "Signed on {date} at {city}."),
        ("signature", "Disclosing Party: {party_a}"),
        ("signature", "Receiving Party: {party_b}"),
    ),
)

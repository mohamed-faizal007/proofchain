from __future__ import annotations

from templates.base import Section, TypeDef
from templates.common import GENERAL

TYPE = TypeDef(
    name="service_agreement",
    title="Master Service Agreement",
    party_kind="company",
    header=(
        (
            "line",
            "This Service Agreement is entered into on {date} between {party_a} (the Provider) "
            "and {party_b} (the Client).",
        ),
        ("line", "The Provider is registered at {address}, {city}."),
    ),
    sections=(
        Section(
            "Services",
            (
                "The Provider shall perform the services described in each statement of work, "
                "including {item} for the Client.",
                "The Provider must assign at least {num} qualified staff to the services and may "
                "replace them on {days} days notice.",
                "The Client shall give the Provider timely access to premises, data and personnel "
                "needed to perform the services.",
                "Each change to the scope requires a written change order and may alter the fees "
                "by up to {pct}.",
            ),
        ),
        Section(
            "Fees and payment",
            (
                "The Client shall pay the Provider a monthly fee of {amount} for the services.",
                "The Provider shall invoice the Client on the last day of each month and the "
                "Client shall pay within {days} days of the invoice date.",
                "Overdue amounts bear interest at {pct} per annum until paid in full.",
                "The Client may withhold up to {amount} of a disputed invoice while the dispute is "
                "resolved under this Agreement.",
                "Fees are exclusive of GST, which the Client shall pay at the prevailing rate of "
                "{pct}.",
            ),
        ),
        Section(
            "Service levels",
            (
                "The Provider shall meet an availability target of {pct} measured monthly.",
                "If the target is missed the Provider shall credit the Client {pct} of the monthly "
                "fee for each shortfall.",
                "The Provider must respond to critical incidents within {num} hours and resolve "
                "them within {days} days.",
                "The Client may audit the Provider's service records once every {months} months on "
                "{days} days notice.",
            ),
        ),
        Section(
            "Term and termination",
            (
                "This Agreement shall commence on {date} and continue for {months} months unless "
                "terminated earlier.",
                "Either party may terminate for convenience on {days} days written notice.",
                "The Client may terminate immediately if the Provider materially breaches this "
                "Agreement and fails to remedy it within {days} days.",
                "On termination the Provider shall deliver all work in progress and the Client "
                "shall pay for services performed until {date}.",
            ),
        ),
        Section(
            "Intellectual property",
            (
                "The Client shall own all deliverables on full payment and the Provider assigns "
                "all rights in them accordingly.",
                "The Provider may reuse its pre-existing tools and know-how, and grants the Client "
                "a perpetual licence to any embedded in deliverables.",
                "The Provider must not incorporate third-party material into deliverables "
                "without the Client's consent.",
            ),
        ),
        *GENERAL,
    ),
    closing=(
        ("line", "Executed on {date} at {city}."),
        ("signature", "For the Provider: {party_a}"),
        ("signature", "For the Client: {party_b}"),
    ),
)

"""Clause banks shared by the contract types. Roles are written literally in each type's own file;
these generic sections use "the Parties" so they read correctly in every contract."""

from __future__ import annotations

from templates.base import Section

GENERAL = (
    Section(
        "Notices",
        (
            "Any notice under this Agreement shall be given in writing and delivered to the other "
            "Party at its address in {city} within {days} days of the event giving rise to it.",
            "A notice sent by registered post is deemed received {num} days after dispatch unless "
            "the recipient proves otherwise.",
            "Either Party may change its address for notices by giving {days} days written notice "
            "to the other Party.",
            "Notices concerning a dispute must quote reference {ref} and shall be signed by an "
            "authorised signatory.",
        ),
    ),
    Section(
        "Confidentiality",
        (
            "Each Party shall keep the terms of this Agreement and all non-public information of "
            "the other Party confidential for {months} months after termination.",
            "A Party may disclose confidential information to its professional advisers if they "
            "are bound by equivalent duties of confidence.",
            "The Parties must not use confidential information for any purpose other than "
            "performing this Agreement.",
            "On written request a Party shall return or destroy confidential material within "
            "{days} days and confirm this in writing.",
        ),
    ),
    Section(
        "Liability and indemnity",
        (
            "The total liability of either Party under this Agreement shall not exceed {amount} "
            "in any period of {months} months.",
            "Each Party shall indemnify the other against third-party claims arising from its "
            "breach of this Agreement, up to {amount}.",
            "Neither Party may claim indirect or consequential loss, including loss of profit "
            "above {pct} of the fees paid.",
            "A Party seeking indemnity shall notify the other within {days} days of receiving a "
            "claim and may not settle it without consent.",
        ),
    ),
    Section(
        "Force majeure",
        (
            "Neither Party shall be liable for delay caused by events beyond its reasonable "
            "control, provided it notifies the other within {days} days.",
            "If a force majeure event continues for more than {days} days, either Party may "
            "terminate this Agreement by written notice.",
            "The affected Party must use reasonable efforts to resume performance and shall "
            "report progress every {num} days.",
        ),
    ),
    Section(
        "Dispute resolution",
        (
            "The Parties shall first try to resolve any dispute by negotiation for {days} days "
            "before starting any proceeding.",
            "Unresolved disputes shall be referred to arbitration seated in {city} under the "
            "Arbitration and Conciliation Act, 1996.",
            "The arbitral tribunal shall consist of {num} arbitrator(s) and its award is final "
            "and binding on the Parties.",
            "The costs of arbitration shall be shared equally unless the tribunal orders "
            "otherwise, and a Party may seek interim relief from the courts at {city}.",
        ),
    ),
    Section(
        "Assignment and amendment",
        (
            "Neither Party may assign this Agreement without the prior written consent of the "
            "other, which shall not be unreasonably withheld.",
            "An amendment is effective only if it is in writing and signed by both Parties on or "
            "after {date}.",
            "If any provision is held invalid the remaining provisions shall continue in full "
            "force and effect.",
            "This Agreement is the entire agreement of the Parties and replaces all earlier "
            "understandings dated before {date}.",
        ),
    ),
)

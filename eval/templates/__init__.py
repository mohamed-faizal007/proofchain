"""Document type registry."""

from __future__ import annotations

from templates import certificate, invoice, lease, nda, service_agreement
from templates.base import TypeDef

TYPES: dict[str, TypeDef] = {
    m.TYPE.name: m.TYPE for m in (lease, service_agreement, nda, invoice, certificate)
}

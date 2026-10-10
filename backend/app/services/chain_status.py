"""Chain summary for GET /chain/status (docs/04_API_SPEC.md, System). Public facts only."""

import asyncio

from pydantic import BaseModel

from app.chain import RegistryClient


class ChainStatus(BaseModel):
    configured: bool
    healthy: bool
    chain_id: int | None = None
    contract: str | None = None
    latest_block: int | None = None


async def get_chain_status(chain: RegistryClient | None, timeout: float) -> ChainStatus:
    """Never raises and never surfaces exception text; any probe failure is `healthy=False`."""
    if chain is None:
        return ChainStatus(configured=False, healthy=False)
    try:
        h = await asyncio.wait_for(chain.health(), timeout)
    except Exception:  # noqa: BLE001 - outage is a status, not an error
        return ChainStatus(configured=True, healthy=False)
    return ChainStatus(
        configured=True,
        healthy=h.ok,
        chain_id=h.chain_id,
        contract=h.registry_address,
        latest_block=h.block_number,
    )

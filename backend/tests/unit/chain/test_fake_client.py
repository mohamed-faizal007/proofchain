import pytest

from app.chain import FakeRegistryClient, RegistryClient
from app.errors import AnchorFailedError

DOC = "d0" * 32
OTHER_DOC = "d1" * 32
F1, R1 = "f1" * 32, "a1" * 32
F2, R2 = "f2" * 32, "a2" * 32
ZERO = "0" * 64


@pytest.fixture
def client() -> FakeRegistryClient:
    return FakeRegistryClient()


def test_fake_satisfies_protocol(client: FakeRegistryClient) -> None:
    c: RegistryClient = client
    assert c is client


async def test_first_anchor_is_version_one(client: FakeRegistryClient) -> None:
    receipt = await client.anchor_version(DOC, F1, R1, 1)
    assert (receipt.version_no, receipt.already_anchored) == (1, False)
    assert receipt.tx_hash is not None and receipt.tx_hash.startswith("0x")
    v = await client.get_version(DOC, 1)
    assert v is not None
    assert (v.file_hash, v.text_root, v.prev_text_root) == (F1, R1, ZERO)
    assert (v.canon_version, v.revoked, v.version_no) == (1, False, 1)
    assert await client.version_count(DOC) == 1


async def test_v2_links_prev_text_root(client: FakeRegistryClient) -> None:
    await client.anchor_version(DOC, F1, R1, 1)
    receipt = await client.anchor_version(DOC, F2, R2, 1)
    assert receipt.version_no == 2
    v2 = await client.get_version(DOC, 2)
    assert v2 is not None and v2.prev_text_root == R1
    assert await client.version_count(DOC) == 2


async def test_docs_are_independent(client: FakeRegistryClient) -> None:
    await client.anchor_version(DOC, F1, R1, 1)
    assert await client.version_count(OTHER_DOC) == 0
    assert (await client.anchor_version(OTHER_DOC, F1, R1, 1)).version_no == 1


async def test_get_version_missing_returns_none(client: FakeRegistryClient) -> None:
    assert await client.get_version(DOC, 1) is None
    await client.anchor_version(DOC, F1, R1, 1)
    assert await client.get_version(DOC, 0) is None
    assert await client.get_version(DOC, 2) is None
    assert await client.version_count(DOC) == 1


@pytest.mark.parametrize("args", [(ZERO, F1, R1), (DOC, ZERO, R1), (DOC, F1, ZERO)])
async def test_zero_hashes_rejected(client: FakeRegistryClient, args: tuple[str, str, str]) -> None:
    with pytest.raises(AnchorFailedError):
        await client.anchor_version(args[0], args[1], args[2], 1)
    assert await client.version_count(DOC) == 0


async def test_malformed_hex_rejected(client: FakeRegistryClient) -> None:
    with pytest.raises(ValueError):
        await client.anchor_version("nothex", F1, R1, 1)


async def test_revoke_keeps_version_readable(client: FakeRegistryClient) -> None:
    await client.anchor_version(DOC, F1, R1, 1)
    receipt = await client.revoke_version(DOC, 1, "wrong file")
    assert receipt.tx_hash.startswith("0x")
    v = await client.get_version(DOC, 1)
    assert v is not None and v.revoked is True and v.file_hash == F1
    assert await client.version_count(DOC) == 1


async def test_double_revoke_and_missing_version_fail(client: FakeRegistryClient) -> None:
    await client.anchor_version(DOC, F1, R1, 1)
    with pytest.raises(AnchorFailedError):
        await client.revoke_version(DOC, 2, "nope")
    with pytest.raises(AnchorFailedError):
        await client.revoke_version(DOC, 0, "nope")
    await client.revoke_version(DOC, 1, "x")
    with pytest.raises(AnchorFailedError):
        await client.revoke_version(DOC, 1, "again")


async def test_reanchor_when_latest_is_live_is_idempotent(client: FakeRegistryClient) -> None:
    first = await client.anchor_version(DOC, F1, R1, 1)
    again = await client.anchor_version(DOC, F1, R1, 1)
    assert (again.version_no, again.already_anchored) == (1, True)
    assert again.tx_hash is None and first.tx_hash is not None
    assert await client.version_count(DOC) == 1


async def test_reanchor_after_revoke_creates_new_version(client: FakeRegistryClient) -> None:
    await client.anchor_version(DOC, F1, R1, 1)
    await client.revoke_version(DOC, 1, "mistake")
    receipt = await client.anchor_version(DOC, F1, R1, 1)
    assert (receipt.version_no, receipt.already_anchored) == (2, False)
    assert receipt.tx_hash is not None
    assert await client.version_count(DOC) == 2
    v1, v2 = await client.get_version(DOC, 1), await client.get_version(DOC, 2)
    assert v1 is not None and v1.revoked is True
    assert v2 is not None and v2.revoked is False and v2.prev_text_root == R1


async def test_reanchor_matches_only_latest(client: FakeRegistryClient) -> None:
    await client.anchor_version(DOC, F1, R1, 1)
    await client.anchor_version(DOC, F2, R2, 1)
    receipt = await client.anchor_version(DOC, F1, R1, 1)
    assert (receipt.version_no, receipt.already_anchored) == (3, False)


async def test_same_file_different_text_root_is_a_new_version(client: FakeRegistryClient) -> None:
    await client.anchor_version(DOC, F1, R1, 1)
    receipt = await client.anchor_version(DOC, F1, R2, 1)
    assert (receipt.version_no, receipt.already_anchored) == (2, False)


async def test_tx_hashes_are_deterministic_and_distinct() -> None:
    a, b = FakeRegistryClient(), FakeRegistryClient()
    ra = await a.anchor_version(DOC, F1, R1, 1)
    rb = await b.anchor_version(DOC, F1, R1, 1)
    assert ra.tx_hash == rb.tx_hash
    assert (await a.anchor_version(DOC, F2, R2, 1)).tx_hash != ra.tx_hash


async def test_health(client: FakeRegistryClient) -> None:
    h = await client.health()
    assert h.ok is True and h.chain_id == 31337

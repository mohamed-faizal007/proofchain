# 05 — Smart Contract: `ProofChainRegistry`

Toolchain: Hardhat (TypeScript config), Solidity `0.8.24`, OpenZeppelin Contracts v5 (`AccessControl`),
ethers v6, `@nomicfoundation/hardhat-toolbox`. Networks: `hardhat`, `localhost` (31337), `sepolia` (11155111).

## Storage & API
```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

contract ProofChainRegistry is AccessControl {
    bytes32 public constant ANCHOR_ROLE = keccak256("ANCHOR_ROLE");

    struct Version {
        bytes32 fileHash;
        bytes32 textRoot;
        bytes32 prevTextRoot;   // bytes32(0) for version 1
        uint64  anchoredAt;     // block.timestamp
        uint16  canonVersion;
        bool    revoked;
    }

    mapping(bytes32 => Version[]) private _versions;   // docId => versions (index 0 = version 1)

    event VersionAnchored(bytes32 indexed docId, uint32 indexed versionNo,
        bytes32 fileHash, bytes32 textRoot, bytes32 prevTextRoot, uint16 canonVersion, uint64 anchoredAt);
    event VersionRevoked(bytes32 indexed docId, uint32 indexed versionNo, string reason, uint64 revokedAt);

    error ZeroHash();
    error VersionNotFound(bytes32 docId, uint32 versionNo);
    error AlreadyRevoked(bytes32 docId, uint32 versionNo);

    constructor(address admin, address anchorer);           // grants DEFAULT_ADMIN_ROLE and ANCHOR_ROLE

    function anchorVersion(bytes32 docId, bytes32 fileHash, bytes32 textRoot, uint16 canonVersion)
        external onlyRole(ANCHOR_ROLE) returns (uint32 versionNo);   // prevTextRoot taken from last version
    function revokeVersion(bytes32 docId, uint32 versionNo, string calldata reason) external onlyRole(ANCHOR_ROLE);
    function getVersion(bytes32 docId, uint32 versionNo) external view returns (Version memory);
    function latestVersion(bytes32 docId) external view returns (uint32 versionNo, Version memory);
    function versionCount(bytes32 docId) external view returns (uint32);
    function findByFileHash(bytes32 docId, bytes32 fileHash) external view returns (bool found, uint32 versionNo);
}
```
Rules: reject zero `docId/fileHash/textRoot`; `versionNo` is 1-based; revoke cannot be undone;
`findByFileHash` is a linear scan (fine for tens of versions — note in report).

Implementation details (P4-01):
- The constructor also reverts `ZeroAddress()` for a zero `admin` or `anchorer` (error added beyond the sketch above).
- `latestVersion` on a doc with no versions reverts `VersionNotFound(docId, 0)`.
- `findByFileHash` scans newest to oldest and returns the latest matching version.
- Revocation is audit-preserving, not a deletion: a revoked version stays readable (`revoked = true`) and is still
  returned by `getVersion` / `findByFileHash`; callers must check the flag. Anchoring after a revoke is allowed and
  `prevTextRoot` still points at the previous version's `textRoot` even if that version is revoked.
  `revokedAt` exists only in the `VersionRevoked` event (the struct has no field for it).

## Required tests (`contracts/test/ProofChainRegistry.test.ts`)
anchor v1/v2 & prevTextRoot linkage · event args · only ANCHOR_ROLE (revert with `AccessControlUnauthorizedAccount`) ·
zero-hash reverts · getVersion out of range reverts · revoke + double revoke · findByFileHash hit/miss ·
gas report enabled (`REPORT_GAS=true`) — the numbers go into the report.

## Deployment (`scripts/deploy.ts`)
1. Deploy with `admin = deployer`, `anchorer = ANCHOR address` (env `ANCHOR_ADDRESS`, default deployer).
2. Write `deployments/<network>.json` `{ address, chainId, deployer, blockNumber, txHash, deployedAt }`.
3. Copy ABI to `backend/app/chain/abi/ProofChainRegistry.json` (this path is committed).
4. Print the `REGISTRY_ADDRESS=` line for `.env`.
Sepolia: verify via `npx hardhat verify` with Etherscan key.

## Backend client (`app/chain/registry_client.py`)
Interface `RegistryClient` (Protocol) with implementations `Web3RegistryClient` and `FakeRegistryClient`
(in-memory, used in tests):
```python
async def anchor_version(doc_id: bytes32hex, file_hash: str, text_root: str, canon_version: int) -> AnchorReceipt
async def revoke_version(doc_id, version_no: int, reason: str) -> TxReceipt
async def get_version(doc_id, version_no: int) -> OnChainVersion | None
async def version_count(doc_id) -> int
async def health() -> ChainHealth
```
- Uses web3.py v6+ `AsyncWeb3`; builds EIP-1559 tx, signs with `ANCHOR_PRIVATE_KEY`, manages nonce
  (single asyncio lock), waits `CHAIN_CONFIRMATIONS`; parses `VersionAnchored` log to get `versionNo`.
- Idempotency: before sending, if `versionCount` > known and latest version's fileHash equals ours, treat as already anchored.
- Hex conversion lives only here: Python hex ↔ `bytes32`.

Implementation details (P4-03):
- Idempotency rule (`is_already_anchored`, shared by both clients): skip the tx only when the **latest** on-chain
  version has the same `fileHash` and `textRoot` **and is not revoked**. Otherwise a new version is anchored, so
  re-anchoring identical content after a revoke yields a fresh valid version. A skipped anchor returns
  `AnchorReceipt(already_anchored=True, tx_hash=None)`.
- Before sending, the client refuses (`AnchorFailedError`) while the anchor account has a pending nonce above its
  mined nonce: an earlier tx (e.g. after a receipt timeout) may still be mined, and a second send could anchor the
  same version twice (P5-04).
- `docId` arguments are the 64-char lowercase hex `chain_doc_id`; `tx_hash` values are `0x`-prefixed.
- `OnChainVersion` exposes `revoked` (needed by the P6 cross-check). `get_version` returns `None` when out of range.
- Reverts map to `AnchorFailedError`; unreachable node or timeout maps to `ChainUnavailableError`.
- `aclose()` releases the HTTP session; the app lifespan calls it.
- Prod config requires non-empty `ANCHOR_PRIVATE_KEY` and `REGISTRY_ADDRESS`.

# Contracts rules (Hardhat + Solidity 0.8.24)

- Spec: `docs/05_SMART_CONTRACT.md`. The contract stores hashes only — never strings of document content.
- Use custom errors, not revert strings (except OpenZeppelin's). Emit an event for every state change.
- Checks-effects-interactions; no external calls; no `tx.origin`; no upgradeability in v1.
- Tests in TypeScript with ethers v6 + chai matchers; `REPORT_GAS=true npx hardhat test` for gas.
  (PowerShell: `$env:REPORT_GAS="true"; npx hardhat test`)
- After any ABI change: rerun `scripts/deploy.ts` locally so `backend/app/chain/abi/ProofChainRegistry.json` updates,
  and update `docs/05_SMART_CONTRACT.md` + the Python client in the same task.
- Never put private keys in files; read from env via `hardhat.config.ts`.

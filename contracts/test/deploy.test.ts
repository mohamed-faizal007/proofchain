import { expect } from "chai";
import { ethers } from "hardhat";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { deployRegistry } from "../scripts/lib/deploy-lib";

describe("deployRegistry", () => {
  let tmp: string;
  let out: { deploymentsDir: string; abiPath: string };

  beforeEach(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), "pc-deploy-"));
    out = {
      deploymentsDir: path.join(tmp, "deployments"),
      abiPath: path.join(tmp, "abi", "ProofChainRegistry.json"),
    };
  });
  afterEach(() => fs.rmSync(tmp, { recursive: true, force: true }));

  it("defaults the anchorer to the deployer", async () => {
    const [deployer] = await ethers.getSigners();
    const r = await deployRegistry({ ...out });
    const c = await ethers.getContractAt("ProofChainRegistry", r.address);
    expect(await c.hasRole(await c.DEFAULT_ADMIN_ROLE(), deployer.address)).to.equal(true);
    expect(await c.hasRole(await c.ANCHOR_ROLE(), deployer.address)).to.equal(true);
  });

  it("grants ANCHOR_ROLE only to ANCHOR_ADDRESS when given", async () => {
    const [deployer, anchorer] = await ethers.getSigners();
    const r = await deployRegistry({ ...out, anchorAddress: anchorer.address });
    const c = await ethers.getContractAt("ProofChainRegistry", r.address);
    expect(await c.hasRole(await c.ANCHOR_ROLE(), anchorer.address)).to.equal(true);
    expect(await c.hasRole(await c.ANCHOR_ROLE(), deployer.address)).to.equal(false);
    expect(await c.hasRole(await c.DEFAULT_ADMIN_ROLE(), deployer.address)).to.equal(true);
  });

  it("writes a complete deployment record for a contract that has code", async () => {
    const [deployer] = await ethers.getSigners();
    const r = await deployRegistry({ ...out });
    const file = path.join(out.deploymentsDir, "hardhat.json");
    const rec = JSON.parse(fs.readFileSync(file, "utf8"));
    expect(Object.keys(rec).sort()).to.deep.equal(
      ["address", "blockNumber", "chainId", "deployedAt", "deployer", "txHash"].sort(),
    );
    expect(rec.address).to.equal(r.address);
    expect(rec.chainId).to.equal(31337);
    expect(rec.deployer).to.equal(deployer.address);
    expect(rec.txHash).to.match(/^0x[0-9a-f]{64}$/);
    expect(rec.blockNumber).to.be.a("number");
    expect(new Date(rec.deployedAt).toISOString()).to.equal(rec.deployedAt);
    expect(await ethers.provider.getCode(rec.address)).to.not.equal("0x");
  });

  it("exports the artifact ABI as a bare array with the client-facing members", async () => {
    await deployRegistry({ ...out });
    const abi = JSON.parse(fs.readFileSync(out.abiPath, "utf8"));
    const artifact = JSON.parse(
      fs.readFileSync(
        path.join(__dirname, "..", "artifacts", "contracts", "ProofChainRegistry.sol", "ProofChainRegistry.json"),
        "utf8",
      ),
    );
    expect(abi).to.deep.equal(artifact.abi);
    const names = abi.map((e: { name?: string }) => e.name);
    for (const n of ["anchorVersion", "revokeVersion", "getVersion", "versionCount", "VersionAnchored"]) {
      expect(names).to.include(n);
    }
  });

  it("produces byte-identical ABI output on repeated runs", async () => {
    await deployRegistry({ ...out });
    const first = fs.readFileSync(out.abiPath);
    await deployRegistry({ ...out });
    expect(fs.readFileSync(out.abiPath).equals(first)).to.equal(true);
  });

  it("rejects a malformed ANCHOR_ADDRESS before sending any tx", async () => {
    const before = await ethers.provider.getBlockNumber();
    let err: unknown;
    try {
      await deployRegistry({ ...out, anchorAddress: "0x1234" });
    } catch (e) {
      err = e;
    }
    expect(String(err)).to.match(/ANCHOR_ADDRESS/);
    expect(await ethers.provider.getBlockNumber()).to.equal(before);
    expect(fs.existsSync(out.abiPath)).to.equal(false);
  });
});

import { expect } from "chai";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { envFilePaths, loadEnvFiles, networksFromEnv } from "../scripts/lib/env-lib";
import { verifyArgs, verifyTarget } from "../scripts/lib/verify-lib";

const A = "0x1111111111111111111111111111111111111111";
const B = "0x2222222222222222222222222222222222222222";

describe("env loading", () => {
  let tmp: string;
  beforeEach(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), "pc-env-"));
  });
  afterEach(() => fs.rmSync(tmp, { recursive: true, force: true }));

  it("looks in the repo root first, then contracts/", () => {
    const paths = envFilePaths(path.join("/repo", "contracts"));
    expect(paths).to.deep.equal([
      path.resolve("/repo", ".env"),
      path.resolve("/repo", "contracts", ".env"),
    ]);
  });

  it("reads the root file and does not need a contracts/.env", () => {
    const root = path.join(tmp, ".env");
    fs.writeFileSync(root, "SEPOLIA_RPC_URL=https://rpc.example\nDEPLOYER_PRIVATE_KEY=0xabc\n");
    const target: NodeJS.ProcessEnv = {};
    loadEnvFiles([root, path.join(tmp, "contracts", ".env")], target);
    expect(target.SEPOLIA_RPC_URL).to.equal("https://rpc.example");
    expect(target.DEPLOYER_PRIVATE_KEY).to.equal("0xabc");
  });

  it("falls back to the contracts file for variables the root file lacks, root wins on conflict", () => {
    const root = path.join(tmp, ".env");
    const local = path.join(tmp, "local.env");
    fs.writeFileSync(root, "SEPOLIA_RPC_URL=https://root\n");
    fs.writeFileSync(local, "SEPOLIA_RPC_URL=https://local\nETHERSCAN_API_KEY=k\n");
    const target: NodeJS.ProcessEnv = {};
    loadEnvFiles([root, local], target);
    expect(target.SEPOLIA_RPC_URL).to.equal("https://root");
    expect(target.ETHERSCAN_API_KEY).to.equal("k");
  });

  it("never overrides a variable already set in the process environment", () => {
    const root = path.join(tmp, ".env");
    fs.writeFileSync(root, "SEPOLIA_RPC_URL=https://file\n");
    const target: NodeJS.ProcessEnv = { SEPOLIA_RPC_URL: "https://shell" };
    loadEnvFiles([root], target);
    expect(target.SEPOLIA_RPC_URL).to.equal("https://shell");
  });

  it("ignores missing files", () => {
    const target: NodeJS.ProcessEnv = {};
    expect(() => loadEnvFiles([path.join(tmp, "nope.env")], target)).to.not.throw();
    expect(target).to.deep.equal({});
  });
});

describe("networksFromEnv", () => {
  it("always has localhost", () => {
    expect(networksFromEnv({})).to.have.property("localhost");
  });

  it("registers sepolia only when both the RPC url and the key are set", () => {
    expect(networksFromEnv({ SEPOLIA_RPC_URL: "https://x" })).to.not.have.property("sepolia");
    expect(networksFromEnv({ DEPLOYER_PRIVATE_KEY: "0xabc" })).to.not.have.property("sepolia");
    const n = networksFromEnv({ SEPOLIA_RPC_URL: "https://x", DEPLOYER_PRIVATE_KEY: "0xabc" });
    expect(n.sepolia).to.include({ url: "https://x", chainId: 11155111 });
  });

  it("treats blank values as unset", () => {
    const n = networksFromEnv({ SEPOLIA_RPC_URL: "  ", DEPLOYER_PRIVATE_KEY: "" });
    expect(n).to.not.have.property("sepolia");
  });
});

describe("verify script helpers", () => {
  const record = {
    address: B,
    chainId: 11155111,
    deployer: A,
    blockNumber: 1,
    txHash: "0x" + "0".repeat(64),
    deployedAt: "2026-10-01T00:00:00.000Z",
  };

  it("uses [deployer, deployer] when no anchor address is configured", () => {
    expect(verifyArgs(record, undefined)).to.deep.equal([A, A]);
    expect(verifyArgs(record, "  ")).to.deep.equal([A, A]);
  });

  it("uses [deployer, anchor] when ANCHOR_ADDRESS is set", () => {
    expect(verifyArgs(record, B)).to.deep.equal([A, B]);
  });

  it("rejects a malformed ANCHOR_ADDRESS", () => {
    expect(() => verifyArgs(record, "0x1234")).to.throw(/ANCHOR_ADDRESS/);
  });

  it("reads address and args from a deployment record file", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "pc-verify-"));
    try {
      fs.writeFileSync(path.join(tmp, "sepolia.json"), JSON.stringify(record));
      const t = verifyTarget(tmp, "sepolia", undefined);
      expect(t).to.deep.equal({ address: B, constructorArguments: [A, A] });
    } finally {
      fs.rmSync(tmp, { recursive: true, force: true });
    }
  });

  it("fails clearly when there is no deployment record for the network", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "pc-verify-"));
    try {
      expect(() => verifyTarget(tmp, "sepolia", undefined)).to.throw(/sepolia\.json/);
    } finally {
      fs.rmSync(tmp, { recursive: true, force: true });
    }
  });
});

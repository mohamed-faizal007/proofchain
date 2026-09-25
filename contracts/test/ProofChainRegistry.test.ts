import { expect } from "chai";
import { ethers } from "hardhat";
import { time } from "@nomicfoundation/hardhat-toolbox/network-helpers";
import type { HardhatEthersSigner } from "@nomicfoundation/hardhat-ethers/signers";
import type { ProofChainRegistry } from "../typechain-types";

const h = (s: string): string => ethers.keccak256(ethers.toUtf8Bytes(s));
const ZERO = ethers.ZeroHash;
const DOC = h("doc-1");
const CANON = 1;

describe("ProofChainRegistry", () => {
  let registry: ProofChainRegistry;
  let admin: HardhatEthersSigner;
  let anchorer: HardhatEthersSigner;
  let other: HardhatEthersSigner;

  beforeEach(async () => {
    [admin, anchorer, other] = await ethers.getSigners();
    registry = (await ethers.deployContract("ProofChainRegistry", [
      admin.address,
      anchorer.address,
    ])) as unknown as ProofChainRegistry;
  });

  const anchor = (doc = DOC, file = h("f1"), root = h("r1")) =>
    registry.connect(anchorer).anchorVersion(doc, file, root, CANON);

  describe("constructor and roles", () => {
    it("grants DEFAULT_ADMIN_ROLE to admin and ANCHOR_ROLE to anchorer only", async () => {
      const anchorRole = await registry.ANCHOR_ROLE();
      const adminRole = await registry.DEFAULT_ADMIN_ROLE();
      expect(await registry.hasRole(adminRole, admin.address)).to.equal(true);
      expect(await registry.hasRole(anchorRole, anchorer.address)).to.equal(true);
      expect(await registry.hasRole(anchorRole, admin.address)).to.equal(false);
      expect(await registry.hasRole(adminRole, anchorer.address)).to.equal(false);
    });

    it("rejects a zero admin or anchorer address", async () => {
      const factory = await ethers.getContractFactory("ProofChainRegistry");
      await expect(
        factory.deploy(ethers.ZeroAddress, anchorer.address),
      ).to.be.revertedWithCustomError(factory, "ZeroAddress");
      await expect(
        factory.deploy(admin.address, ethers.ZeroAddress),
      ).to.be.revertedWithCustomError(factory, "ZeroAddress");
    });

    it("lets the admin grant and revoke ANCHOR_ROLE", async () => {
      const role = await registry.ANCHOR_ROLE();
      await registry.connect(admin).grantRole(role, other.address);
      await registry.connect(other).anchorVersion(DOC, h("f1"), h("r1"), CANON);
      await registry.connect(admin).revokeRole(role, other.address);
      await expect(
        registry.connect(other).anchorVersion(DOC, h("f2"), h("r2"), CANON),
      ).to.be.revertedWithCustomError(registry, "AccessControlUnauthorizedAccount");
    });
  });

  describe("anchorVersion", () => {
    it("anchors v1 then v2 and links prevTextRoot", async () => {
      await anchor(DOC, h("f1"), h("r1"));
      await anchor(DOC, h("f2"), h("r2"));

      const v1 = await registry.getVersion(DOC, 1);
      const v2 = await registry.getVersion(DOC, 2);
      expect(v1.prevTextRoot).to.equal(ZERO);
      expect(v1.fileHash).to.equal(h("f1"));
      expect(v1.textRoot).to.equal(h("r1"));
      expect(v1.canonVersion).to.equal(CANON);
      expect(v1.revoked).to.equal(false);
      expect(v2.prevTextRoot).to.equal(h("r1"));
      expect(await registry.versionCount(DOC)).to.equal(2);
    });

    it("returns the new versionNo from a static call", async () => {
      expect(
        await registry.connect(anchorer).anchorVersion.staticCall(DOC, h("f1"), h("r1"), CANON),
      ).to.equal(1);
      await anchor();
      expect(
        await registry.connect(anchorer).anchorVersion.staticCall(DOC, h("f2"), h("r2"), CANON),
      ).to.equal(2);
    });

    it("records block.timestamp and emits VersionAnchored with the right args", async () => {
      const tx = await anchor(DOC, h("f1"), h("r1"));
      const block = await ethers.provider.getBlock("latest");
      const ts = block!.timestamp;
      await expect(tx)
        .to.emit(registry, "VersionAnchored")
        .withArgs(DOC, 1, h("f1"), h("r1"), ZERO, CANON, ts);
      expect((await registry.getVersion(DOC, 1)).anchoredAt).to.equal(ts);

      await time.increase(10);
      const tx2 = await anchor(DOC, h("f2"), h("r2"));
      const ts2 = (await ethers.provider.getBlock("latest"))!.timestamp;
      await expect(tx2)
        .to.emit(registry, "VersionAnchored")
        .withArgs(DOC, 2, h("f2"), h("r2"), h("r1"), CANON, ts2);
    });

    it("keeps documents independent", async () => {
      const other_doc = h("doc-2");
      await anchor(DOC, h("f1"), h("r1"));
      await anchor(other_doc, h("g1"), h("s1"));
      expect(await registry.versionCount(DOC)).to.equal(1);
      expect(await registry.versionCount(other_doc)).to.equal(1);
      expect((await registry.getVersion(other_doc, 1)).prevTextRoot).to.equal(ZERO);
    });

    it("reverts for callers without ANCHOR_ROLE", async () => {
      const role = await registry.ANCHOR_ROLE();
      await expect(registry.connect(other).anchorVersion(DOC, h("f1"), h("r1"), CANON))
        .to.be.revertedWithCustomError(registry, "AccessControlUnauthorizedAccount")
        .withArgs(other.address, role);
      await expect(registry.connect(admin).anchorVersion(DOC, h("f1"), h("r1"), CANON))
        .to.be.revertedWithCustomError(registry, "AccessControlUnauthorizedAccount")
        .withArgs(admin.address, role);
    });

    it("reverts with ZeroHash for a zero docId, fileHash or textRoot", async () => {
      const a = registry.connect(anchorer);
      await expect(a.anchorVersion(ZERO, h("f"), h("r"), CANON)).to.be.revertedWithCustomError(
        registry,
        "ZeroHash",
      );
      await expect(a.anchorVersion(DOC, ZERO, h("r"), CANON)).to.be.revertedWithCustomError(
        registry,
        "ZeroHash",
      );
      await expect(a.anchorVersion(DOC, h("f"), ZERO, CANON)).to.be.revertedWithCustomError(
        registry,
        "ZeroHash",
      );
      expect(await registry.versionCount(DOC)).to.equal(0);
    });
  });

  describe("access edge cases", () => {
    it("denies grantRole to a non-admin, including the anchorer", async () => {
      const role = await registry.ANCHOR_ROLE();
      await expect(
        registry.connect(anchorer).grantRole(role, other.address),
      ).to.be.revertedWithCustomError(registry, "AccessControlUnauthorizedAccount");
    });

    it("checks the role before existence when a non-anchorer revokes a missing doc", async () => {
      await expect(
        registry.connect(other).revokeVersion(h("nope"), 1, "x"),
      ).to.be.revertedWithCustomError(registry, "AccessControlUnauthorizedAccount");
    });

    it("round-trips the maximum uint16 canonVersion", async () => {
      await registry.connect(anchorer).anchorVersion(DOC, h("f1"), h("r1"), 65535);
      expect((await registry.getVersion(DOC, 1)).canonVersion).to.equal(65535);
    });
  });

  describe("getVersion / latestVersion / versionCount", () => {
    it("reverts VersionNotFound for version 0 and out-of-range versions", async () => {
      await expect(registry.getVersion(DOC, 0))
        .to.be.revertedWithCustomError(registry, "VersionNotFound")
        .withArgs(DOC, 0);
      await anchor();
      await expect(registry.getVersion(DOC, 2))
        .to.be.revertedWithCustomError(registry, "VersionNotFound")
        .withArgs(DOC, 2);
    });

    it("latestVersion returns the newest version, and reverts for an unknown doc", async () => {
      await expect(registry.latestVersion(DOC))
        .to.be.revertedWithCustomError(registry, "VersionNotFound")
        .withArgs(DOC, 0);
      await anchor(DOC, h("f1"), h("r1"));
      await anchor(DOC, h("f2"), h("r2"));
      const [no, v] = await registry.latestVersion(DOC);
      expect(no).to.equal(2);
      expect(v.fileHash).to.equal(h("f2"));
    });

    it("versionCount is 0 for an unknown doc", async () => {
      expect(await registry.versionCount(h("nope"))).to.equal(0);
    });
  });

  describe("revokeVersion", () => {
    it("marks the version revoked and emits VersionRevoked", async () => {
      await anchor();
      const tx = await registry.connect(anchorer).revokeVersion(DOC, 1, "mistake");
      const ts = (await ethers.provider.getBlock("latest"))!.timestamp;
      await expect(tx).to.emit(registry, "VersionRevoked").withArgs(DOC, 1, "mistake", ts);
      expect((await registry.getVersion(DOC, 1)).revoked).to.equal(true);
    });

    it("cannot be revoked twice", async () => {
      await anchor();
      await registry.connect(anchorer).revokeVersion(DOC, 1, "x");
      await expect(registry.connect(anchorer).revokeVersion(DOC, 1, "again"))
        .to.be.revertedWithCustomError(registry, "AlreadyRevoked")
        .withArgs(DOC, 1);
    });

    it("reverts VersionNotFound for a missing version", async () => {
      await expect(registry.connect(anchorer).revokeVersion(DOC, 1, "x"))
        .to.be.revertedWithCustomError(registry, "VersionNotFound")
        .withArgs(DOC, 1);
      await expect(registry.connect(anchorer).revokeVersion(DOC, 0, "x"))
        .to.be.revertedWithCustomError(registry, "VersionNotFound")
        .withArgs(DOC, 0);
    });

    it("reverts for callers without ANCHOR_ROLE", async () => {
      await anchor();
      await expect(
        registry.connect(other).revokeVersion(DOC, 1, "x"),
      ).to.be.revertedWithCustomError(registry, "AccessControlUnauthorizedAccount");
      expect((await registry.getVersion(DOC, 1)).revoked).to.equal(false);
    });

    it("only revokes the targeted version", async () => {
      await anchor(DOC, h("f1"), h("r1"));
      await anchor(DOC, h("f2"), h("r2"));
      await registry.connect(anchorer).revokeVersion(DOC, 1, "x");
      expect((await registry.getVersion(DOC, 1)).revoked).to.equal(true);
      expect((await registry.getVersion(DOC, 2)).revoked).to.equal(false);
    });

    // Revocation is audit-preserving, not a deletion: a revoked version stays readable and
    // later versions still link to its textRoot via prevTextRoot. Verification (02 §11)
    // is what treats revoked versions as not authentic.
    it("keeps the hash chain intact when anchoring after a revoke (v1 -> v2 -> revoke v2 -> v3)", async () => {
      await anchor(DOC, h("f1"), h("r1"));
      await anchor(DOC, h("f2"), h("r2"));
      await registry.connect(anchorer).revokeVersion(DOC, 2, "mistake found");
      const versionNo = await registry
        .connect(anchorer)
        .anchorVersion.staticCall(DOC, h("f3"), h("r3"), CANON);
      await anchor(DOC, h("f3"), h("r3"));

      expect(versionNo).to.equal(3);
      const v2 = await registry.getVersion(DOC, 2);
      const v3 = await registry.getVersion(DOC, 3);
      expect(v2.revoked).to.equal(true);
      expect(v2.textRoot).to.equal(h("r2"));
      expect(v3.prevTextRoot).to.equal(v2.textRoot);
      expect(v3.revoked).to.equal(false);
      const [latestNo] = await registry.latestVersion(DOC);
      expect(latestNo).to.equal(3);
    });
  });

  describe("findByFileHash", () => {
    it("finds a version by file hash", async () => {
      await anchor(DOC, h("f1"), h("r1"));
      await anchor(DOC, h("f2"), h("r2"));
      const [found, no] = await registry.findByFileHash(DOC, h("f1"));
      expect(found).to.equal(true);
      expect(no).to.equal(1);
    });

    it("misses for an unknown hash or unknown doc", async () => {
      await anchor();
      expect((await registry.findByFileHash(DOC, h("zzz")))[0]).to.equal(false);
      expect((await registry.findByFileHash(h("nope"), h("f1")))[0]).to.equal(false);
    });

    it("returns the latest version when a file hash was anchored more than once", async () => {
      await anchor(DOC, h("f1"), h("r1"));
      await anchor(DOC, h("f2"), h("r2"));
      await anchor(DOC, h("f1"), h("r3"));
      const [found, no] = await registry.findByFileHash(DOC, h("f1"));
      expect(found).to.equal(true);
      expect(no).to.equal(3);
    });

    it("still finds revoked versions (callers check the revoked flag)", async () => {
      await anchor();
      await registry.connect(anchorer).revokeVersion(DOC, 1, "x");
      const [found, no] = await registry.findByFileHash(DOC, h("f1"));
      expect(found).to.equal(true);
      expect(no).to.equal(1);
    });
  });
});

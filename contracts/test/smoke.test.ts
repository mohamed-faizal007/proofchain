import { expect } from "chai";
import { ethers } from "hardhat";

describe("toolchain smoke", () => {
  it("deploys and grants DEFAULT_ADMIN_ROLE to the admin", async () => {
    const [admin, other] = await ethers.getSigners();
    const placeholder = await ethers.deployContract("Placeholder", [admin.address]);
    const role = await placeholder.DEFAULT_ADMIN_ROLE();

    expect(await placeholder.hasRole(role, admin.address)).to.equal(true);
    expect(await placeholder.hasRole(role, other.address)).to.equal(false);
  });
});

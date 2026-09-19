// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @dev Temporary toolchain smoke contract (P0-04). Replaced by ProofChainRegistry in P4-01.
contract Placeholder is AccessControl {
    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }
}

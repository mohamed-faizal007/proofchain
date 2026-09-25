// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @notice Anchors document version hashes. Stores hashes only, never document content.
contract ProofChainRegistry is AccessControl {
    bytes32 public constant ANCHOR_ROLE = keccak256("ANCHOR_ROLE");

    struct Version {
        bytes32 fileHash;
        bytes32 textRoot;
        bytes32 prevTextRoot; // bytes32(0) for version 1
        uint64 anchoredAt; // block.timestamp
        uint16 canonVersion;
        bool revoked;
    }

    mapping(bytes32 => Version[]) private _versions; // docId => versions (index 0 = version 1)

    event VersionAnchored(
        bytes32 indexed docId,
        uint32 indexed versionNo,
        bytes32 fileHash,
        bytes32 textRoot,
        bytes32 prevTextRoot,
        uint16 canonVersion,
        uint64 anchoredAt
    );
    event VersionRevoked(bytes32 indexed docId, uint32 indexed versionNo, string reason, uint64 revokedAt);

    error ZeroHash();
    error ZeroAddress();
    error VersionNotFound(bytes32 docId, uint32 versionNo);
    error AlreadyRevoked(bytes32 docId, uint32 versionNo);

    constructor(address admin, address anchorer) {
        if (admin == address(0) || anchorer == address(0)) revert ZeroAddress();
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ANCHOR_ROLE, anchorer);
    }

    function anchorVersion(
        bytes32 docId,
        bytes32 fileHash,
        bytes32 textRoot,
        uint16 canonVersion
    ) external onlyRole(ANCHOR_ROLE) returns (uint32 versionNo) {
        if (docId == bytes32(0) || fileHash == bytes32(0) || textRoot == bytes32(0)) revert ZeroHash();

        Version[] storage versions = _versions[docId];
        uint256 count = versions.length;
        // The previous root is taken even if that version was revoked: revocation keeps the chain intact.
        bytes32 prevTextRoot = count == 0 ? bytes32(0) : versions[count - 1].textRoot;
        uint64 ts = uint64(block.timestamp);

        versions.push(
            Version({
                fileHash: fileHash,
                textRoot: textRoot,
                prevTextRoot: prevTextRoot,
                anchoredAt: ts,
                canonVersion: canonVersion,
                revoked: false
            })
        );
        versionNo = uint32(count + 1);
        emit VersionAnchored(docId, versionNo, fileHash, textRoot, prevTextRoot, canonVersion, ts);
    }

    /// @param reason Free text emitted in the event; must never contain document content.
    function revokeVersion(
        bytes32 docId,
        uint32 versionNo,
        string calldata reason
    ) external onlyRole(ANCHOR_ROLE) {
        Version storage v = _at(docId, versionNo);
        if (v.revoked) revert AlreadyRevoked(docId, versionNo);
        v.revoked = true;
        emit VersionRevoked(docId, versionNo, reason, uint64(block.timestamp));
    }

    function getVersion(bytes32 docId, uint32 versionNo) external view returns (Version memory) {
        return _at(docId, versionNo);
    }

    function latestVersion(bytes32 docId) external view returns (uint32 versionNo, Version memory version) {
        uint256 count = _versions[docId].length;
        if (count == 0) revert VersionNotFound(docId, 0);
        versionNo = uint32(count);
        version = _versions[docId][count - 1];
    }

    function versionCount(bytes32 docId) external view returns (uint32) {
        return uint32(_versions[docId].length);
    }

    /// @dev Linear scan from newest to oldest; fine for tens of versions per document.
    function findByFileHash(bytes32 docId, bytes32 fileHash) external view returns (bool found, uint32 versionNo) {
        Version[] storage versions = _versions[docId];
        for (uint256 i = versions.length; i > 0; i--) {
            if (versions[i - 1].fileHash == fileHash) {
                return (true, uint32(i));
            }
        }
        return (false, 0);
    }

    function _at(bytes32 docId, uint32 versionNo) private view returns (Version storage) {
        Version[] storage versions = _versions[docId];
        if (versionNo == 0 || versionNo > versions.length) revert VersionNotFound(docId, versionNo);
        return versions[versionNo - 1];
    }
}

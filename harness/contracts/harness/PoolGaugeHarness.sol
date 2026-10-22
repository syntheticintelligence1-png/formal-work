// SPDX-License-Identifier: MIT
pragma solidity =0.8.20;

import { ERC20 } from "@openzeppelin/contracts-v4/token/ERC20/ERC20.sol";

import { BoostableRebalancePool } from "../bundle/f(x)/rebalance-pool/BoostableRebalancePool.sol";

contract PGToken is ERC20 {
  constructor(string memory n) ERC20(n, n) {}

  function mint(address to, uint256 a) external {
    _mint(to, a);
  }

  function burn(address from, uint256 a) external {
    _burn(from, a);
  }
}

contract PGVotingEscrow {
  mapping(address => uint256) public balanceOf;
  uint256 public totalSupply;

  function set(address a, uint256 b) external {
    totalSupply = totalSupply - balanceOf[a] + b;
    balanceOf[a] = b;
  }
}

/// @dev Treasury surface used by the pool's initializer and liquidation guard.
contract PGTreasury {
  address public baseToken;
  address public fToken;
  uint256 public collateralRatio = 1e18;

  constructor(address b, address f) {
    baseToken = b;
    fToken = f;
  }

  function maxRedeemableFToken(uint256) external pure returns (uint256, uint256) {
    return (0, type(uint128).max);
  }
}

/// @dev ICurveTokenMinter stand-in: `mint(gauge)` transfers the configured emission to the caller.
contract PGMinter {
  PGToken public immutable fxn;
  uint256 public next;

  constructor(PGToken _fxn) {
    fxn = _fxn;
  }

  function setNext(uint256 a) external {
    next = a;
  }

  function mint(address) external {
    if (next > 0) fxn.mint(msg.sender, next);
    next = 0;
  }
}

contract PGExpose {
  BoostableRebalancePool public pool;
}

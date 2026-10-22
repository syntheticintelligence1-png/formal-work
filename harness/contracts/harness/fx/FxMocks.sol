// SPDX-License-Identifier: MIT
pragma solidity =0.8.20;

import { ERC20 } from "@openzeppelin/contracts-v4/token/ERC20/ERC20.sol";

// Exposes the bundle contracts to the Hardhat artifact set.
import { BoostableRebalancePool } from "../../bundle/f(x)/rebalance-pool/BoostableRebalancePool.sol";
import { ShareableRebalancePool } from "../../bundle/f(x)/rebalance-pool/ShareableRebalancePool.sol";
import { TreasuryWithFundingCost } from "../../bundle/f(x)/funding-cost-market/TreasuryWithFundingCost.sol";
import { MarketWithFundingCost } from "../../bundle/f(x)/funding-cost-market/MarketWithFundingCost.sol";
import { WrappedTokenTreasuryV2 } from "../../bundle/f(x)/v2/WrappedTokenTreasuryV2.sol";
import { MarketV2 } from "../../bundle/f(x)/v2/MarketV2.sol";

contract FxMockToken is ERC20 {
  uint8 private immutable _dec;

  constructor(string memory n, string memory s, uint8 d) ERC20(n, s) {
    _dec = d;
  }

  function decimals() public view override returns (uint8) {
    return _dec;
  }

  function mint(address to, uint256 a) external {
    _mint(to, a);
  }

  function burn(address from, uint256 a) external {
    _burn(from, a);
  }
}

contract FxMockVE {
  mapping(address => uint256) public balanceOf;
  uint256 public totalSupply;

  function set(address a, uint256 b) external {
    totalSupply = totalSupply - balanceOf[a] + b;
    balanceOf[a] = b;
  }
}

contract FxMockVeHelper {
  FxMockVE public immutable ve;

  constructor(FxMockVE _ve) {
    ve = _ve;
  }

  function totalSupply(uint256) external view returns (uint256) {
    return ve.totalSupply();
  }

  function balanceOf(address a, uint256) external view returns (uint256) {
    return ve.balanceOf(a);
  }

  function checkpoint(address) external {}

  function checkpoint(address, uint256) external {}
}

/// @dev Subset of IFxTreasury / IFxTreasuryV2 that the rebalance pools call.
contract FxMockPoolTreasury {
  address public baseToken;
  address public fToken;
  uint256 public collateralRatio = 1e18;
  uint256 public maxLiq = type(uint128).max;

  constructor(address b, address f) {
    baseToken = b;
    fToken = f;
  }

  function maxRedeemableFToken(uint256) external view returns (uint256, uint256) {
    return (0, maxLiq);
  }
}

/// @dev Market for the pools: burns fToken from the caller and pays 1 base per 1000 fToken to the recipient.
contract FxMockPoolMarket {
  FxMockToken public immutable base;
  FxMockToken public immutable f;

  constructor(FxMockToken b, FxMockToken _f) {
    base = b;
    f = _f;
  }

  function redeem(uint256 fIn, uint256, address recipient, uint256) external returns (uint256 out, uint256) {
    f.burn(msg.sender, fIn);
    out = fIn / 1000;
    base.mint(recipient, out);
  }

  function redeemFToken(uint256 fIn, address recipient, uint256) external returns (uint256 out, uint256) {
    f.burn(msg.sender, fIn);
    out = fIn / 1000;
    base.mint(recipient, out);
  }
}

contract FxMockOracleV2 {
  bool public isValid = true;
  uint256 public price = 2000e18;

  function set(bool v, uint256 p) external {
    isValid = v;
    price = p;
  }

  function getPrice() external view returns (bool, uint256, uint256, uint256) {
    return (isValid, price, price, price);
  }
}

contract FxMockCrvUSDAmm {
  uint256 public get_rate_mul = 1e18;

  function set(uint256 v) external {
    get_rate_mul = v;
  }
}

contract FxMockRegistry {
  function totalSupply() external pure returns (uint256) {
    return 1; // pools non-empty -> no reserve-pool bonus path
  }
}

contract FxMockSplitter {
  function split(address) external {}
}

contract FxMockRateProvider {
  uint256 public getRate = 1e18;

  function set(uint256 r) external {
    getRate = r;
  }
}

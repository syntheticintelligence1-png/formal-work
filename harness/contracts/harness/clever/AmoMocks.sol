// SPDX-License-Identifier: MIT
pragma solidity =0.8.20;

interface IMT { function transfer(address,uint256) external returns (bool); function transferFrom(address,address,uint256) external returns (bool); function balanceOf(address) external view returns (uint256); function mint(address,uint256) external; function totalSupply() external view returns (uint256); }

/// Curve factory plain 2-pool stand-in: reports stableswap parameters to AMOMath, executes 1:1
/// (exchange(dx) returns dx, add_liquidity mints sum of amounts). Only the in-bundle control flow
/// of the AMO is under test; exchange(0) returning 0 matches the Curve reference in the
/// non-reverting half of states (models/out_t11.txt, T11e).
contract MockCurvePool {
  address[2] public coinsArr;
  uint256[2] public bal;
  address public lp;
  constructor(address c0, address c1, address _lp) { coinsArr[0] = c0; coinsArr[1] = c1; lp = _lp; }
  function seed(uint256 b0, uint256 b1) external { bal[0] = b0; bal[1] = b1; IMT(lp).mint(address(this), b0 + b1); }
  function coins(uint256 i) external view returns (address) { return coinsArr[i]; }
  function balances(uint256 i) external view returns (uint256) { return bal[i]; }
  function A_precise() external pure returns (uint256) { return 10000; }
  function fee() external pure returns (uint256) { return 4000000; }
  function add_liquidity(uint256[2] memory a, uint256) external returns (uint256) {
    require(a[0] + a[1] > 0, "curve: assert D1 > D0");
    if (a[0] > 0) IMT(coinsArr[0]).transferFrom(msg.sender, address(this), a[0]);
    if (a[1] > 0) IMT(coinsArr[1]).transferFrom(msg.sender, address(this), a[1]);
    bal[0] += a[0]; bal[1] += a[1];
    IMT(lp).mint(msg.sender, a[0] + a[1]);
    return a[0] + a[1];
  }
  function exchange(int128 i, int128 j, uint256 dx, uint256, address r) external returns (uint256) {
    if (dx > 0) IMT(coinsArr[uint128(i)]).transferFrom(msg.sender, address(this), dx);
    bal[uint128(i)] += dx; bal[uint128(j)] -= dx;
    if (dx > 0) IMT(coinsArr[uint128(j)]).transfer(r, dx);
    return dx;
  }
  function remove_liquidity_one_coin(uint256, int128, uint256) external pure returns (uint256) { revert("unused"); }
}

/// ICLeverAMOStrategy stand-in holding LP 1:1.
contract MockAMOStrategy {
  address public lp;
  constructor(address _lp) { lp = _lp; }
  function name() external pure returns (string memory) { return "mock"; }
  function strategyBalance() external view returns (uint256) { return IMT(lp).balanceOf(address(this)); }
  function deposit(address, uint256 a) external pure { require(a > 0, "strategy: deposit zero"); }
  function withdraw(address r, uint256 a) external { if (a > 0) IMT(lp).transfer(r, a); }
  function harvest(address, address) external pure returns (uint256) { return 0; }
  function updateRewards(address[] memory) external {}
  function prepareMigrate(address) external {}
  function finishMigrate(address) external {}
}

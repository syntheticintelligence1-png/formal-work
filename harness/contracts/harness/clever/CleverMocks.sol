// SPDX-License-Identifier: MIT
pragma solidity =0.8.20;

/// Minimal ERC20 usable via hardhat_setCode at a fixed address (no constructor state needed).
contract CleverMockToken {
  mapping(address => uint256) public balanceOf;
  mapping(address => mapping(address => uint256)) public allowance;
  uint256 public totalSupply;
  uint8 internal dec; // 0 => 18 (so code etched at a fixed address reports 18)

  function setDecimals(uint8 d) external { dec = d; }
  function decimals() external view returns (uint8) { return dec == 0 ? 18 : dec; }
  function name() external pure returns (string memory) { return "Mock"; }
  function symbol() external pure returns (string memory) { return "MOCK"; }

  function mint(address to, uint256 a) external { balanceOf[to] += a; totalSupply += a; }
  function burn(uint256 a) external { require(balanceOf[msg.sender] >= a, "ERC20: burn amount exceeds balance"); balanceOf[msg.sender] -= a; totalSupply -= a; }
  function burnFrom(address f, uint256 a) external {
    require(allowance[f][msg.sender] >= a, "ERC20: burn amount exceeds allowance");
    allowance[f][msg.sender] -= a;
    require(balanceOf[f] >= a, "ERC20: burn amount exceeds balance");
    balanceOf[f] -= a; totalSupply -= a;
  }
  function approve(address s, uint256 a) external returns (bool) { allowance[msg.sender][s] = a; return true; }
  function transfer(address to, uint256 a) external returns (bool) { _t(msg.sender, to, a); return true; }
  function transferFrom(address f, address to, uint256 a) external returns (bool) {
    require(allowance[f][msg.sender] >= a, "ERC20: transfer amount exceeds allowance");
    allowance[f][msg.sender] -= a; _t(f, to, a); return true;
  }
  function _t(address f, address to, uint256 a) internal {
    require(balanceOf[f] >= a, "ERC20: transfer amount exceeds balance");
    balanceOf[f] -= a; balanceOf[to] += a;
  }
}

interface IERC20m { function transfer(address,uint256) external returns (bool); function transferFrom(address,address,uint256) external returns (bool); function balanceOf(address) external view returns (uint256); }

/// cvxRewardPool stand-in, etched at CVX_REWARD_POOL (0xCF50...). Stake/withdraw 1:1, no rewards.
contract MockCvxRewardPool {
  address constant CVX = 0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B;
  mapping(address => uint256) public balanceOf;
  function stake(uint256 a) external { IERC20m(CVX).transferFrom(msg.sender, address(this), a); balanceOf[msg.sender] += a; }
  function withdraw(uint256 a, bool) external { require(balanceOf[msg.sender] >= a, "pool: withdraw"); balanceOf[msg.sender] -= a; IERC20m(CVX).transfer(msg.sender, a); }
  function getReward(bool) external {}
  function getReward(address, bool, bool) external {}
  function earned(address) external pure returns (uint256) { return 0; }
}

/// ICLeverYieldStrategy stand-in (L4168-L4250): underlying == yield token, price 1e18.
contract MockYieldStrategy {
  address public underlyingToken;
  constructor(address u) { underlyingToken = u; }
  function yieldToken() external view returns (address) { return underlyingToken; }
  function underlyingPrice() external pure returns (uint256) { return 1e18; }
  function totalUnderlyingToken() public view returns (uint256) { return IERC20m(underlyingToken).balanceOf(address(this)); }
  function totalYieldToken() external view returns (uint256) { return totalUnderlyingToken(); }
  function deposit(address, uint256 a, bool) external pure returns (uint256) { return a; }
  function withdraw(address r, uint256 a, bool) external returns (uint256) { IERC20m(underlyingToken).transfer(r, a); return a; }
}

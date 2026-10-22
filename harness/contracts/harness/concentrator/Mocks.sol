// SPDX-License-Identifier: MIT
// Mocks for external venues (environment actions with stated contracts; see REPORT.md section 5).
pragma solidity =0.8.20;

contract MockERC20 {
  mapping(address => uint256) public balanceOf;
  mapping(address => mapping(address => uint256)) public allowance;
  uint256 public totalSupply;

  function decimals() external pure returns (uint8) {
    return 18;
  }

  function mint(address to, uint256 amt) public {
    balanceOf[to] += amt;
    totalSupply += amt;
  }

  function approve(address s, uint256 a) external returns (bool) {
    allowance[msg.sender][s] = a;
    return true;
  }

  function transfer(address to, uint256 a) external returns (bool) {
    balanceOf[msg.sender] -= a;
    balanceOf[to] += a;
    return true;
  }

  function transferFrom(address f, address to, uint256 a) external returns (bool) {
    uint256 al = allowance[f][msg.sender];
    if (al != type(uint256).max) allowance[f][msg.sender] = al - a;
    balanceOf[f] -= a;
    balanceOf[to] += a;
    return true;
  }
}

/// IWrapper_SdCrvCompounder (L1203-L1252) abstraction: custody counter per depositor, zero-amount guards as in
/// ConcentratorStakeDAOGaugeWrapper (L628, L629, L735).
contract MockSdWrapper {
  MockERC20 public immutable sdCRV;
  mapping(address => uint256) public balanceOf;
  mapping(address => address) public rewardReceiver;
  address[] internal tokens;

  constructor(address _sdCRV) {
    sdCRV = MockERC20(_sdCRV);
  }

  function getActiveRewardTokens() external view returns (address[] memory) {
    return tokens;
  }

  function deposit(uint256 amount, address receiver) external {
    require(amount > 0, "ErrorDepositZeroAssets");
    sdCRV.transferFrom(msg.sender, address(this), amount);
    balanceOf[receiver] += amount;
  }

  function withdraw(uint256 amount, address receiver) external {
    require(amount > 0, "ErrorWithdrawZeroAssets");
    require(amount <= balanceOf[msg.sender], "ErrorInsufficientStakedToken");
    balanceOf[msg.sender] -= amount;
    sdCRV.transfer(receiver, amount);
  }

  function setRewardReceiver(address r) external {
    rewardReceiver[msg.sender] = r;
  }

  function claim(address, address) external {}
}

/// Convex Booster at the constant BOOSTER address (installed with hardhat_setCode).
contract MockBooster {
  struct PoolInfo {
    address lptoken;
    address token;
    address gauge;
    address crvRewards;
    address stash;
    bool shutdown;
  }
  mapping(uint256 => PoolInfo) internal pools;

  function setPool(uint256 pid, address lp, address rewards) external {
    pools[pid] = PoolInfo(lp, address(0), address(0), rewards, address(0), false);
  }

  function poolInfo(uint256 pid) external view returns (PoolInfo memory) {
    return pools[pid];
  }

  function deposit(uint256 pid, uint256 amount, bool) external returns (bool) {
    PoolInfo memory p = pools[pid];
    MockERC20(p.lptoken).transferFrom(msg.sender, p.crvRewards, amount);
    MockRewardPool(p.crvRewards).stakeFor(msg.sender, amount);
    return true;
  }
}

/// Convex BaseRewardPool abstraction. A-CVX-PERM: getReward(account, claimExtras) is callable by anyone for anyone.
contract MockRewardPool {
  MockERC20 public immutable lp;
  MockERC20 public immutable crv;
  MockERC20 public immutable fxs;
  mapping(address => uint256) public balanceOf;
  mapping(address => uint256) public earnedCRV;
  mapping(address => uint256) public earnedFXS;

  constructor(address _lp, address _crv, address _fxs) {
    lp = MockERC20(_lp);
    crv = MockERC20(_crv);
    fxs = MockERC20(_fxs);
  }

  function stakeFor(address a, uint256 x) external returns (bool) {
    balanceOf[a] += x;
    return true;
  }

  function accrue(address a, uint256 c, uint256 f) external {
    earnedCRV[a] += c;
    earnedFXS[a] += f;
  }

  function getReward() external returns (bool) {
    return _getReward(msg.sender);
  }

  function getReward(address a, bool) external returns (bool) {
    return _getReward(a);
  }

  function _getReward(address a) internal returns (bool) {
    uint256 c = earnedCRV[a];
    earnedCRV[a] = 0;
    if (c > 0) crv.mint(a, c);
    uint256 f = earnedFXS[a];
    earnedFXS[a] = 0;
    if (f > 0) fxs.mint(a, f);
    return true;
  }

  function withdrawAndUnwrap(uint256 x, bool) external returns (bool) {
    balanceOf[msg.sender] -= x;
    lp.transfer(msg.sender, x);
    return true;
  }
}

/// IZap abstraction (A-ZAP): input already transferred to the zap; output minted/sent to msg.sender at a fixed price.
contract MockZap {
  mapping(address => mapping(address => uint256)) public price;

  function setPrice(address f, address t, uint256 p) external {
    price[f][t] = p;
  }

  function zap(address f, uint256 a, address t, uint256 minOut) external payable returns (uint256 out) {
    out = (a * price[f][t]) / 1e18;
    require(out >= minOut, "zap: slippage");
    if (t == address(0)) {
      (bool ok, ) = msg.sender.call{ value: out }("");
      require(ok, "zap: eth");
    } else {
      MockERC20(t).mint(msg.sender, out);
    }
  }

  receive() external payable {}
}

/// aFXS abstraction (A-AFXS): share token; 1 share = KC/1e18 asset (real cvxFXS, a different address than FXS).
contract MockAFXS is MockERC20 {
  MockERC20 public immutable fxs;
  MockERC20 public immutable cvxfxs;
  uint256 public constant KC = 1.2e18;

  constructor(address _fxs, address _cvxfxs) {
    fxs = MockERC20(_fxs);
    cvxfxs = MockERC20(_cvxfxs);
  }

  function depositWithFXS(uint256 a, address r, uint256) external returns (uint256 s) {
    fxs.transferFrom(msg.sender, address(this), a);
    s = (a * 1e18) / KC;
    mint(r, s);
  }

  function deposit(uint256 a, address r) external returns (uint256 s) {
    cvxfxs.transferFrom(msg.sender, address(this), a);
    s = (a * 1e18) / KC;
    mint(r, s);
  }

  function redeem(uint256 s, address r, address o) external returns (uint256 a) {
    require(msg.sender == o && s > 0, "redeem");
    balanceOf[o] -= s;
    totalSupply -= s;
    a = (s * KC) / 1e18;
    cvxfxs.mint(r, a);
  }
}

/// Curve-style gauge (ICurveGauge subset used by the wrapper).
contract MockGauge {
  address public staking_token;
  address[] internal rewards;

  constructor(address _st) {
    staking_token = _st;
  }

  function addReward(address t) external {
    rewards.push(t);
  }

  function reward_count() external view returns (uint256) {
    return rewards.length;
  }

  function reward_tokens(uint256 i) external view returns (address) {
    return rewards[i];
  }
}

/// IConcentratorStakeDAOLocker abstraction: deposit returns the staking-token balance it holds (cross-validation value).
contract MockLocker {
  function deposit(address, address token) external returns (uint256) {
    return MockERC20(token).balanceOf(address(this));
  }

  function withdraw(address, address token, uint256 amount, address recipient) external {
    if (amount > 0) MockERC20(token).transfer(recipient, amount);
  }

  function claimRewards(address, address[] calldata) external returns (uint256[] memory a) {}
}

/// Legacy vault at the constant 0x2b3e... address (installed with hardhat_setCode).
contract MockLegacyVault {
  struct LockedBalance {
    uint128 amount;
    uint128 expireAt;
  }
  mapping(address => uint256) public balanceOf;
  uint256 public totalSupply;

  function set(address a, uint256 b, uint256 ts) external {
    balanceOf[a] = b;
    totalSupply = ts;
  }

  function getUserLocks(address) external pure returns (LockedBalance[] memory locks) {
    locks = new LockedBalance[](0);
  }
}

/// StakeDAOBribeClaimer replacement (immutable constructor argument of the wrapper).
/// A-LOCK: the locker forwards exactly claims[i].amount of claims[i].token to the receiver.
contract MockBribeClaimer {
  struct claimParam {
    address token;
    uint256 index;
    uint256 amount;
    bytes32[] merkleProof;
  }

  function claim(claimParam[] memory claims, address receiver) external {
    for (uint256 i = 0; i < claims.length; i++) {
      if (claims[i].amount > 0) MockERC20(claims[i].token).mint(receiver, claims[i].amount);
    }
  }
}

/// ITokenConverter abstraction (A-CONV): `encoding` indexes a route table; consumes amountIn of tokenIn held by the
/// converter, mints amountIn*price/1e18 of tokenOut to recipient; amountIn == 0 returns 0.
contract MockConverter {
  struct Route {
    address tin;
    address tout;
    uint256 price;
  }
  mapping(uint256 => Route) public routes;
  address public constant SINK = address(0xdead);

  function setRoute(uint256 id, address tin, address tout, uint256 p) external {
    routes[id] = Route(tin, tout, p);
  }

  function convert(uint256 encoding, uint256 amountIn, address recipient) external payable returns (uint256 out) {
    if (amountIn == 0) return 0;
    Route memory r = routes[encoding];
    MockERC20(r.tin).transfer(SINK, amountIn);
    out = (amountIn * r.price) / 1e18;
    MockERC20(r.tout).mint(recipient, out);
  }
}

/// IConcentratorCompounder subset used by ConcentratorCompounderStash (L2350, L2359, L2386, L2456, L2464, L2467, L2472).
contract MockCompounder {
  address public asset;
  address public harvester;
  address public converter;
  address public treasury;
  uint256 public totalRewards;

  constructor(address _asset, address _harvester, address _converter, address _treasury) {
    asset = _asset;
    harvester = _harvester;
    converter = _converter;
    treasury = _treasury;
  }

  function getHarvesterRatio() external pure returns (uint256) {
    return 0;
  }

  function getExpenseRatio() external pure returns (uint256) {
    return 0;
  }

  function depositReward(uint256 amount) external {
    MockERC20(asset).transferFrom(msg.sender, address(this), amount);
    totalRewards += amount;
  }
}

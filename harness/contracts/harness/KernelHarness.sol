// SPDX-License-Identifier: MIT
pragma solidity =0.8.20;

import { ERC20 } from "@openzeppelin/contracts-v4/token/ERC20/ERC20.sol";

import { MultipleRewardAccumulator } from "../bundle/common/rewards/accumulator/MultipleRewardAccumulator.sol";
import { LinearMultipleRewardDistributor } from "../bundle/common/rewards/distributor/LinearMultipleRewardDistributor.sol";
import { LinearReward } from "../bundle/common/rewards/distributor/LinearReward.sol";

contract MockToken is ERC20 {
  constructor(string memory n) ERC20(n, n) {}

  function mint(address to, uint256 amount) external {
    _mint(to, amount);
  }
}

/// @dev Minimal staking instantiation of the K3 kernel. `stake`/`unstake` discharge O3a/O3b/O3c by construction;
/// `stakeWithoutCheckpoint` deliberately violates O3a (used only for the relaxation experiment).
contract KernelMRA is MultipleRewardAccumulator {
  mapping(address => uint256) public shareOf;
  uint256 public totalShare;

  constructor(uint40 _periodLength) LinearMultipleRewardDistributor(_periodLength) {}

  function initialize() external initializer {
    __MultipleRewardAccumulator_init();
    _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
    _grantRole(REWARD_MANAGER_ROLE, msg.sender);
  }

  function stake(uint256 amount) external {
    _checkpoint(msg.sender);
    shareOf[msg.sender] += amount;
    totalShare += amount;
  }

  function unstake(uint256 amount) external {
    _checkpoint(msg.sender);
    shareOf[msg.sender] -= amount;
    totalShare -= amount;
  }

  function stakeWithoutCheckpoint(uint256 amount) external {
    shareOf[msg.sender] += amount;
    totalShare += amount;
  }

  function _getTotalPoolShare() internal view override returns (uint256) {
    return totalShare;
  }

  function _getUserPoolShare(address _account) internal view override returns (uint256) {
    return shareOf[_account];
  }
}

/// @dev Direct exposure of the K1 library transformation for precondition-violation experiments.
contract LinearRewardProbe {
  using LinearReward for LinearReward.RewardData;

  LinearReward.RewardData public data;

  function set(uint96 queued, uint80 rate, uint40 lastUpdate, uint40 finishAt) external {
    data = LinearReward.RewardData(queued, rate, lastUpdate, finishAt);
  }

  function increase(uint256 periodLength, uint256 amount) external {
    LinearReward.RewardData memory d = data;
    d.increase(periodLength, amount);
    data = d;
  }

  function pending() external view returns (uint256, uint256) {
    return data.pending();
  }
}

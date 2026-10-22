// SPDX-License-Identifier: MIT
pragma solidity =0.8.20;

/// @dev Gauge-wrapper stand-in for SdCrvCompounder: records the per-account reward receiver
/// (MultipleRewardAccumulator.setRewardReceiver semantics, L2140) and pays `claim(account)` to it.
contract IRWrapper {
  mapping(address => address) public rewardReceiver;
  mapping(address => uint256) public accrued;

  function setRewardReceiver(address r) external {
    rewardReceiver[msg.sender] = r;
  }

  function accrue(address account, uint256 a) external {
    accrued[account] += a;
  }

  /// third-party claim pays the stored receiver (L2168-L2172, L2244-L2248)
  function claim(address account) external returns (address to, uint256 a) {
    to = rewardReceiver[account] == address(0) ? account : rewardReceiver[account];
    a = accrued[account];
    accrued[account] = 0;
  }
}

/// @dev Minimal ERC20 surface for the constant token addresses touched by initializeV2 (installed with hardhat_setCode).
contract IRToken {
  mapping(address => mapping(address => uint256)) public allowance;

  function approve(address s, uint256 a) external returns (bool) {
    allowance[msg.sender][s] = a;
    return true;
  }
}

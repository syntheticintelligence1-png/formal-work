// SPDX-License-Identifier: MIT
// Thin harness subclasses: they add NO logic, only an initializer entry point that the bundle omits
// (SdCrvCompounder has no initializer calling AladdinCompounder._initialize in this bundle).
pragma solidity ^0.7.6;
pragma abicoder v2;

import "../../bundle/concentrator/stakedao/sdcrv/SdCrvCompounder.sol";
import "../../bundle/concentrator/fxs/AladdinFXSConvexVault.sol";

contract SdCrvCompounderHarness is SdCrvCompounder {
  constructor(address _legacyVault, address _wrapper) SdCrvCompounder(_legacyVault, _wrapper) {}

  function init() external initializer {
    _initialize("Aladdin sdCRV", "asdCRV");
  }

  function totalAssetsStoredX() external view returns (uint256) {
    return totalAssetsStored;
  }
}

contract FXSVaultHarness is AladdinFXSConvexVault {
  function zapAsRewardTokenX(address[] memory tokens, uint256[] memory amounts) external returns (uint256) {
    return _zapAsRewardToken(tokens, amounts);
  }
}

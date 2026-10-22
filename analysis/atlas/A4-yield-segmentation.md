# Atlas 4 — Yield-point segmentation (atomicity lens)

Each row is a mutating action that writes storage **after** a non-static external call whose callee is not a fixed venue (YP = address from policy storage, Yext = address returned by another call, YU = user-supplied, ? = computed).

The *worst callee class* is the least trusted callee preceding the write. `lock` shows whether a `nonReentrant` guard covers the action. A guard blocks write-reentrancy into the same lock domain only; it does not block cross-contract reentrancy or read-only reentrancy.

| Contract | Action | Access | Lock | Worst callee class → writes after it |
|---|---|---|---|---|
| AladdinCRV | `depositAllWithCRV` | open | Y | YP → _balances, _totalSupply |
| AladdinCRV | `depositWithCRV` | open | Y | YP → _balances, _totalSupply |
| AladdinCRV | `harvest` | cond[harvester] | Y | YP → _balances, _totalSupply |
| AladdinCRV | `withdraw` | open | Y | YP → _balances, _totalSupply |
| AladdinCRV | `withdrawAll` | open | Y | YP → _balances, _totalSupply |
| AladdinCRVConvexVault | `deposit` | open | Y | YP → poolInfo, userInfo |
| AladdinCRVConvexVault | `deposit` | open | Y | YP → poolInfo, userInfo |
| AladdinCRVConvexVault | `depositAll` | open | Y | YP → poolInfo, userInfo |
| AladdinCRVConvexVault | `depositAll` | open | Y | YP → poolInfo, userInfo |
| AladdinCRVConvexVault | `harvest` | cond[harvester] | Y | ? → poolInfo |
| AladdinCRVConvexVault | `withdrawAllAndClaim` | open | Y | YP → userInfo |
| AladdinCRVConvexVault | `withdrawAllAndZap` | open | Y | YP → poolInfo, userInfo |
| AladdinCRVConvexVault | `withdrawAndClaim` | open | Y | YP → userInfo |
| AladdinCRVConvexVault | `withdrawAndZap` | open | Y | YP → poolInfo, userInfo |
| AladdinCRVConvexVault | `zapAllAndDeposit` | open | Y | YU → poolInfo, userInfo; YP → poolInfo, userInfo |
| AladdinCRVConvexVault | `zapAllAndDeposit` | open | Y | YU → poolInfo, userInfo; YP → poolInfo, userInfo |
| AladdinCRVConvexVault | `zapAndDeposit` | open | Y | YU → poolInfo, userInfo; YP → poolInfo, userInfo |
| AladdinCRVConvexVault | `zapAndDeposit` | open | Y | YU → poolInfo, userInfo; YP → poolInfo, userInfo |
| AladdinCVX | `harvest` | cond[harvester] | N | YP → rewardPerShare |
| AladdinCVX | `unlock` | open | N | YP → _balances, _totalSupply, accountRewards |
| AladdinCVX | `withdraw` | open | N | YP → _balances, _totalSupply, accountRewards |
| AladdinCVX | `withdrawToBase` | open | N | YP → _balances, _totalSupply, accountRewards |
| AladdinFXSConvexVault | `deposit` | open | Y | YP → poolInfo, userInfo |
| AladdinFXSConvexVault | `harvest` | cond[harvester] | Y | ? → poolInfo, rewardInfo |
| BoostableRebalancePool | `deposit` | open | N | YP → _balances, _totalSupply, boostCheckpoint, epochToExponentToRewardSnapshot, gauge, numTotalSupplyHistory … |
| BoostableRebalancePool | `depositReward` | gated[body] | N | YU → epochToExponentToRewardSnapshot, rewardData |
| BoostableRebalancePool | `liquidate` | gated[onlyRole] | N | YP → _totalSupply, epochToExponentToRewardSnapshot, lastAssetLossError, numTotalSupplyHistory, rewardData, totalSupplyHistory |
| CLeverCVXLocker | `harvest` | open | N | ? → accRewardPerShare |
| CLeverCVXLocker | `harvestPaladinLikeBribes` | gated[onlyKeeper] | N | YU → accRewardPerShare |
| CLeverCVXLocker | `harvestUniversalRewardsDistributorBribes` | gated[onlyKeeper] | N | YU → accRewardPerShare, universalRewardsDistributorClaimed |
| CLeverCVXLocker | `harvestVotiumLikeBribes` | gated[onlyKeeper] | N | YU → accRewardPerShare |
| CLeverCVXLocker | `repay` | open | N | YP → totalDebtGlobal, userInfo |
| ConcentratorSdCrvGaugeWrapper | `depositReward` | gated[body] | N | YU → rewardData, rewardSnapshot |
| ConcentratorSdCrvGaugeWrapper | `harvest` | open | Y | ? → rewardData, rewardSnapshot |
| ConcentratorSdCrvGaugeWrapper | `harvestBribes` | open | Y | ? → rewardData, rewardSnapshot |
| ConcentratorSdCrvGaugeWrapper | `initialize` | init | N | ? → _initializing, _roles, activeRewardTokens, balanceOf, stash, totalSupply |
| Furnace | `deposit` | open | N | YP → accUnrealisedFraction, distributeIndex, lastPaidOffDistributeIndex, rewardInfo, totalRealised, totalUnrealised … |
| Furnace | `depositFor` | open | N | YP → accUnrealisedFraction, distributeIndex, lastPaidOffDistributeIndex, rewardInfo, totalRealised, totalUnrealised … |
| Furnace | `exit` | open | N | YP → totalRealised, userInfo |
| Furnace | `harvest` | gated[onlyWhitelisted] | N | YP → accUnrealisedFraction, distributeIndex, lastPaidOffDistributeIndex, rewardInfo, totalRealised, totalUnrealised |
| MetaFurnace | `deposit` | open | N | YP → furnaceInfo, rewardInfo, userInfo |
| MetaFurnace | `exit` | open | N | YP → furnaceInfo, userInfo |
| MetaFurnace | `harvest` | open | N | YP → furnaceInfo, rewardInfo |
| MetaFurnace | `migrateStrategy` | gated[onlyOwner] | N | YU → yieldInfo |
| SdCrvCompounder | `deposit` | open | Y | ? → _balances, _totalSupply, totalAssetsStored |
| SdCrvCompounder | `harvest` | cond[harvester] | Y | ? → _balances, _totalSupply, rewardInfo, totalAssetsStored |
| SdCrvCompounder | `mint` | open | Y | ? → _balances, _totalSupply, totalAssetsStored |
| ShareableRebalancePool | `deposit` | gated[body] | N | YP → _balances, _totalSupply, boostCheckpoint, epochToExponentToRewardSnapshot, gauge, numTotalSupplyHistory … |
| ShareableRebalancePool | `depositReward` | gated[body] | N | YU → epochToExponentToRewardSnapshot, rewardData |
| ShareableRebalancePool | `liquidate` | gated[onlyRole] | N | YP → _totalSupply, epochToExponentToRewardSnapshot, lastAssetLossError, numTotalSupplyHistory, rewardData, totalSupplyHistory |
| ShareableRebalancePoolV2 | `deposit` | gated[body] | N | YP → _balances, _totalSupply, boostCheckpoint, epochToExponentToRewardSnapshot, gauge, numTotalSupplyHistory … |
| ShareableRebalancePoolV2 | `depositReward` | gated[body] | N | YU → epochToExponentToRewardSnapshot, rewardData |
| ShareableRebalancePoolV2 | `liquidate` | gated[onlyRole] | N | YP → _totalSupply, epochToExponentToRewardSnapshot, lastAssetLossError, numTotalSupplyHistory, rewardData, totalSupplyHistory |
| TreasuryWithFundingCost | `redeem` | gated[onlyRole] | N | YP → strategyUnderlying |
| WrappedTokenTreasuryV2 | `redeem` | gated[onlyRole] | N | YP → strategyUnderlying |

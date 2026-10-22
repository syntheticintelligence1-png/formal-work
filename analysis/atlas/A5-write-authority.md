# Atlas 5 — Write-authority partition of storage (mechanized strata boundary)

SBD defines the policy stratum 𝒫 by write authority. A storage variable is in 𝒫 iff **no** open or `cond` action writes it, i.e. it is written only by gated actions or initializers. All other variables are dynamic (𝒞-shadow / ℒ / ℐ / 𝒯).

Constants and immutables (𝒫₀) never appear because they are never written.

This partition is computed, not asserted. A variable that the specification treats as policy but that appears in the dynamic column is a **policy leak**: an unprivileged path writes a policy-like variable.

## 𝒫 — written only by gated or initializer actions (102)

`AccessControl._roles`, `AccessControlUpgradeable._roles`, `AladdinCRV.harvestBountyPercentage`, `AladdinCRV.platform`, `AladdinCRV.platformFeePercentage`, `AladdinCRV.withdrawFeePercentage`, `AladdinCRV.zap`, `AladdinCRVConvexVault.aladdinCRV`, `AladdinCRVConvexVault.migrator`, `AladdinCRVConvexVault.platform`, `AladdinCRVConvexVault.zap`, `AladdinCVX.strategy`, `AladdinCVX.zap`, `AladdinCompounder.feeInfo`, `AladdinFXSConvexVault.aladdinFXS`, `AladdinFXSConvexVault.zap`, `BoostableRebalancePool.asset`, `BoostableRebalancePool.baseToken`, `BoostableRebalancePool.lastAssetLossError`, `BoostableRebalancePool.liquidatableCollateralRatio`, `BoostableRebalancePool.market`, `BoostableRebalancePool.treasury`, `BoostableRebalancePool.wrapper`, `CLeverAMOBase.bountyPercentage`, `CLeverAMOBase.config`, `CLeverAMOBase.initialRatio`, `CLeverAMOBase.lockPeriod`, `CLeverAMOBase.minimumDeposit`, `CLeverAMOBase.platform`, `CLeverAMOBase.platformPercentage`, `CLeverCVXLocker.approvedTargets`, `CLeverCVXLocker.harvestBountyPercentage`, `CLeverCVXLocker.isKeeper`, `CLeverCVXLocker.manualSwapRewardToken`, `CLeverCVXLocker.platform`, `CLeverCVXLocker.platformFeePercentage`, `CLeverCVXLocker.repayFeePercentage`, `CLeverCVXLocker.reserveRate`, `CLeverCVXLocker.rewardTokens`, `CLeverCVXLocker.stakePercentage`, `CLeverCVXLocker.stakeThreshold`, `CLeverCVXLocker.universalRewardsDistributorClaimed`, `CLeverCVXLocker.verifier`, `CLeverCVXLocker.zap`, `ConcentratorBaseV2._miscData`, `ConcentratorBaseV2.converter`, `ConcentratorBaseV2.harvester`, `ConcentratorBaseV2.treasury`, `ConcentratorConvexVault.platform`, `ConcentratorStakeDAOGaugeWrapper.stash`, `CrvUSDBorrowRateAdapter.amm`, `CrvUSDBorrowRateAdapter.fundingCostScale`, `ERC20Upgradeable._decimals`, `ERC20Upgradeable._name`, `ERC20Upgradeable._symbol`, `FeeCustomization.<assembly-slot>`, `Furnace.clevCVX`, `Furnace.governor`, `Furnace.harvestBountyPercentage`, `Furnace.isWhitelisted`, `Furnace.platform`, `Furnace.platformFeePercentage`, `Furnace.stakePercentage`, `Furnace.stakeThreshold`, `Furnace.zap`, `Initializable._initialized`, `Initializable._initializing`, `LinearMultipleRewardDistributor.distributors`, `LinearMultipleRewardDistributor.historicalRewardTokens`, `MarketV2.fxUSD`, `MarketV2.marketConfigData`, `MarketV2.mintFeeData`, `MarketV2.platform`, `MarketV2.redeemFeeData`, `MarketV2.registry`, `MarketV2.reservePool`, `MetaFurnace.baseToken`, `MetaFurnace.debtToken`, `MetaFurnace.feeInfo`, `MetaFurnace.isWhitelisted`, `MetaFurnace.yieldInfo`, `Ownable._owner`, `OwnableUpgradeable._owner`, `RewardClaimable.rewards`, `SdCrvCompounder.zap`, `ShareableRebalancePool.asset`, `ShareableRebalancePool.baseToken`, `ShareableRebalancePool.isStakerAllowed`, `ShareableRebalancePool.lastAssetLossError`, `ShareableRebalancePool.liquidatableCollateralRatio`, `ShareableRebalancePool.market`, `ShareableRebalancePool.treasury`, `ShareableRebalancePool.wrapper`, `TreasuryV2._miscData`, `TreasuryV2.baseTokenCap`, `TreasuryV2.platform`, `TreasuryV2.priceOracle`, `TreasuryV2.rebalancePoolSplitter`, `TreasuryV2.referenceBaseTokenPrice`, `TreasuryV2.strategy`, `TreasuryV2.strategyUnderlying`, `WrappedTokenTreasuryV2.rateProvider`

## Dynamic — written by at least one open or `cond` action (63)

| Variable | Open writers (sample) | Gated writers (sample) |
|---|---|---|
| `AladdinCRVConvexVault.poolInfo` | AladdinCRVConvexVault.deposit, AladdinCRVConvexVault.depositAll, AladdinCRVConvexVault.harvest … | AladdinCRVConvexVault.addPool, AladdinCRVConvexVault.pausePoolDeposit … |
| `AladdinCRVConvexVault.userInfo` | AladdinCRVConvexVault.claim, AladdinCRVConvexVault.claimAll, AladdinCRVConvexVault.deposit … |  |
| `AladdinCompounder.rewardInfo` | SdCrvCompounder.checkpoint, SdCrvCompounder.deposit, SdCrvCompounder.depositWithCRV … | SdCrvCompounder.depositReward, SdCrvCompounder.updateRewardPeriodLength |
| `AladdinCompounder.totalAssetsStored` | SdCrvCompounder.checkpoint, SdCrvCompounder.deposit, SdCrvCompounder.depositWithCRV … | SdCrvCompounder.depositReward |
| `BoostableRebalancePool._balances` | BoostableRebalancePool.checkpoint, BoostableRebalancePool.claim, BoostableRebalancePool.claimHistorical … | BoostableRebalancePool.liquidate |
| `BoostableRebalancePool._totalSupply` | BoostableRebalancePool.deposit, BoostableRebalancePool.withdraw | BoostableRebalancePool.liquidate |
| `BoostableRebalancePool.boostCheckpoint` | BoostableRebalancePool.checkpoint, BoostableRebalancePool.claim, BoostableRebalancePool.claimHistorical … | BoostableRebalancePool.liquidate |
| `BoostableRebalancePool.gauge` | BoostableRebalancePool.checkpoint, BoostableRebalancePool.claim, BoostableRebalancePool.claimHistorical … | BoostableRebalancePool.liquidate |
| `BoostableRebalancePool.numTotalSupplyHistory` | BoostableRebalancePool.deposit, BoostableRebalancePool.withdraw | BoostableRebalancePool.liquidate |
| `BoostableRebalancePool.totalSupplyHistory` | BoostableRebalancePool.deposit, BoostableRebalancePool.withdraw | BoostableRebalancePool.liquidate |
| `CLeverAMOBase.locks` | AladdinCVX.deposit, AladdinCVX.unlock |  |
| `CLeverAMOBase.nextIndex` | AladdinCVX.unlock |  |
| `CLeverAMOBase.pendingBaseToken` | AladdinCVX.checkpoint, AladdinCVX.donate, AladdinCVX.unlock … | AladdinCVX.rebalance |
| `CLeverCVXLocker.accRewardPerShare` | CLeverCVXLocker.donate, CLeverCVXLocker.harvest | CLeverCVXLocker.harvestPaladinLikeBribes, CLeverCVXLocker.harvestUniversalRewardsDistributorBribes … |
| `CLeverCVXLocker.pendingUnlocked` | CLeverCVXLocker.unlock | CLeverCVXLocker.processUnlockableCVX |
| `CLeverCVXLocker.totalDebtGlobal` | CLeverCVXLocker.borrow, CLeverCVXLocker.deposit, CLeverCVXLocker.repay … |  |
| `CLeverCVXLocker.totalLockedGlobal` | CLeverCVXLocker.deposit, CLeverCVXLocker.unlock |  |
| `CLeverCVXLocker.totalPendingUnlockGlobal` | CLeverCVXLocker.unlock | CLeverCVXLocker.processUnlockableCVX |
| `CLeverCVXLocker.totalUnlockedGlobal` | CLeverCVXLocker.withdrawUnlocked | CLeverCVXLocker.processUnlockableCVX |
| `CLeverCVXLocker.userInfo` | CLeverCVXLocker.borrow, CLeverCVXLocker.deposit, CLeverCVXLocker.repay … |  |
| `ConcentratorConvexVault.poolInfo` | AladdinFXSConvexVault.claim, AladdinFXSConvexVault.claimAll, AladdinFXSConvexVault.deposit … | AladdinFXSConvexVault.addPool, AladdinFXSConvexVault.pausePoolDeposit … |
| `ConcentratorConvexVault.rewardInfo` | AladdinFXSConvexVault.claim, AladdinFXSConvexVault.claimAll, AladdinFXSConvexVault.deposit … | AladdinFXSConvexVault.addPool, AladdinFXSConvexVault.updateRewardPeriod |
| `ConcentratorConvexVault.userInfo` | AladdinFXSConvexVault.approve, AladdinFXSConvexVault.claim, AladdinFXSConvexVault.claimAll … |  |
| `ConcentratorStakeDAOGaugeWrapper.balanceOf` | ConcentratorSdCrvGaugeWrapper.deposit, ConcentratorSdCrvGaugeWrapper.depositWithCRV, ConcentratorSdCrvGaugeWrapper.depositWithGauge … |  |
| `ConcentratorStakeDAOGaugeWrapper.totalSupply` | ConcentratorSdCrvGaugeWrapper.deposit, ConcentratorSdCrvGaugeWrapper.depositWithCRV, ConcentratorSdCrvGaugeWrapper.depositWithGauge … |  |
| `CrvUSDBorrowRateAdapter.borrowRateSnapshot` | TreasuryWithFundingCost.harvest | TreasuryWithFundingCost.initializeProtocol |
| `ERC20Upgradeable._allowances` | AladdinCRV.approve, AladdinCRV.decreaseAllowance, AladdinCRV.increaseAllowance … |  |
| `ERC20Upgradeable._balances` | AladdinCRV.deposit, AladdinCRV.depositAll, AladdinCRV.depositAllWithCRV … |  |
| `ERC20Upgradeable._totalSupply` | AladdinCRV.deposit, AladdinCRV.depositAll, AladdinCRV.depositAllWithCRV … |  |
| `Furnace.accUnrealisedFraction` | Furnace.claim, Furnace.deposit, Furnace.depositFor … | Furnace.distribute, Furnace.harvest |
| `Furnace.distributeIndex` | Furnace.claim, Furnace.deposit, Furnace.depositFor … | Furnace.distribute, Furnace.harvest |
| `Furnace.lastPaidOffDistributeIndex` | Furnace.claim, Furnace.deposit, Furnace.depositFor … | Furnace.distribute, Furnace.harvest |
| `Furnace.rewardInfo` | Furnace.claim, Furnace.deposit, Furnace.depositFor … | Furnace.distribute, Furnace.harvest … |
| `Furnace.totalRealised` | Furnace.claim, Furnace.deposit, Furnace.depositFor … | Furnace.distribute, Furnace.harvest |
| `Furnace.totalUnrealised` | Furnace.claim, Furnace.deposit, Furnace.depositFor … | Furnace.distribute, Furnace.harvest |
| `Furnace.userInfo` | Furnace.claim, Furnace.deposit, Furnace.depositFor … |  |
| `LinearMultipleRewardDistributor.activeRewardTokens` | ConcentratorSdCrvGaugeWrapper.syncActiveRewardTokens | BoostableRebalancePool.registerRewardToken, BoostableRebalancePool.unregisterRewardToken … |
| `LinearMultipleRewardDistributor.rewardData` | BoostableRebalancePool.checkpoint, BoostableRebalancePool.claim, BoostableRebalancePool.claimHistorical … | BoostableRebalancePool.depositReward, BoostableRebalancePool.liquidate … |
| `MetaFurnace.furnaceInfo` | MetaFurnace.claim, MetaFurnace.deposit, MetaFurnace.exit … | MetaFurnace.distribute |
| `MetaFurnace.rewardInfo` | MetaFurnace.claim, MetaFurnace.deposit, MetaFurnace.exit … | MetaFurnace.distribute, MetaFurnace.updatePeriodLength |
| `MetaFurnace.userInfo` | MetaFurnace.claim, MetaFurnace.deposit, MetaFurnace.exit … | MetaFurnace.fixStatus |
| `MultipleRewardAccumulator.rewardReceiver` | ConcentratorSdCrvGaugeWrapper.setRewardReceiver |  |
| `MultipleRewardAccumulator.rewardSnapshot` | ConcentratorSdCrvGaugeWrapper.checkpoint, ConcentratorSdCrvGaugeWrapper.claim, ConcentratorSdCrvGaugeWrapper.claimHistorical … | ConcentratorSdCrvGaugeWrapper.depositReward |
| `MultipleRewardAccumulator.userRewardSnapshot` | ConcentratorSdCrvGaugeWrapper.checkpoint, ConcentratorSdCrvGaugeWrapper.claim, ConcentratorSdCrvGaugeWrapper.claimHistorical … |  |
| `MultipleRewardCompoundingAccumulator.epochToExponentToRewardSnapshot` | BoostableRebalancePool.checkpoint, BoostableRebalancePool.claim, BoostableRebalancePool.claimHistorical … | BoostableRebalancePool.depositReward, BoostableRebalancePool.liquidate … |
| `MultipleRewardCompoundingAccumulator.rewardReceiver` | BoostableRebalancePool.setRewardReceiver, ShareableRebalancePool.setRewardReceiver, ShareableRebalancePoolV2.setRewardReceiver |  |
| `MultipleRewardCompoundingAccumulator.userRewardSnapshot` | BoostableRebalancePool.checkpoint, BoostableRebalancePool.claim, BoostableRebalancePool.claimHistorical … | BoostableRebalancePool.liquidate, ShareableRebalancePool.acceptSharedVote … |
| `RewardClaimable.accountRewards` | AladdinCVX.checkpointUser, AladdinCVX.claim, AladdinCVX.transfer … |  |
| `RewardClaimable.rewardPerShare` | AladdinCVX.harvest |  |
| `SdCRVLocker.locks` | SdCrvCompounder.withdrawExpired |  |
| `SdCRVLocker.nextLockIndex` | SdCrvCompounder.withdrawExpired |  |
| `SdCrvCompounder.stash` | SdCrvCompounder.initializeV2 | SdCrvCompounder.updateStash |
| `ShareableRebalancePool._balances` | ShareableRebalancePool.checkpoint, ShareableRebalancePool.claim, ShareableRebalancePool.claimHistorical … | ShareableRebalancePool.acceptSharedVote, ShareableRebalancePool.deposit … |
| `ShareableRebalancePool._totalSupply` | ShareableRebalancePool.withdraw, ShareableRebalancePoolV2.withdraw | ShareableRebalancePool.deposit, ShareableRebalancePool.liquidate … |
| `ShareableRebalancePool.boostCheckpoint` | ShareableRebalancePool.checkpoint, ShareableRebalancePool.claim, ShareableRebalancePool.claimHistorical … | ShareableRebalancePool.acceptSharedVote, ShareableRebalancePool.deposit … |
| `ShareableRebalancePool.gauge` | ShareableRebalancePool.checkpoint, ShareableRebalancePool.claim, ShareableRebalancePool.claimHistorical … | ShareableRebalancePool.acceptSharedVote, ShareableRebalancePool.deposit … |
| `ShareableRebalancePool.getStakerVoteOwner` | ShareableRebalancePool.rejectSharedVote, ShareableRebalancePoolV2.rejectSharedVote | ShareableRebalancePool.acceptSharedVote, ShareableRebalancePool.toggleVoteSharing … |
| `ShareableRebalancePool.numTotalSupplyHistory` | ShareableRebalancePool.withdraw, ShareableRebalancePoolV2.withdraw | ShareableRebalancePool.deposit, ShareableRebalancePool.liquidate … |
| `ShareableRebalancePool.totalSupplyHistory` | ShareableRebalancePool.withdraw, ShareableRebalancePoolV2.withdraw | ShareableRebalancePool.deposit, ShareableRebalancePool.liquidate … |
| `ShareableRebalancePool.voteOwnerBalances` | ShareableRebalancePool.checkpoint, ShareableRebalancePool.claim, ShareableRebalancePool.claimHistorical … | ShareableRebalancePool.acceptSharedVote, ShareableRebalancePool.deposit … |
| `ShareableRebalancePool.voteOwnerHistoryBalances` | ShareableRebalancePool.checkpoint, ShareableRebalancePool.claim, ShareableRebalancePool.claimHistorical … | ShareableRebalancePool.acceptSharedVote, ShareableRebalancePool.deposit … |
| `TreasuryV2.emaLeverageRatio` | TreasuryWithFundingCost.harvest, WrappedTokenTreasuryV2.harvest | TreasuryWithFundingCost.initializeProtocol, TreasuryWithFundingCost.mintFToken … |
| `TreasuryV2.totalBaseToken` | TreasuryWithFundingCost.harvest | TreasuryWithFundingCost.initializeProtocol, TreasuryWithFundingCost.mintFToken … |

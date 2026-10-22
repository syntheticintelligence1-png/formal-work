# Atlas 3 — Balance-differential reads (B1 sites)

Each row is a `balanceOf(address(this))` read reachable from a mutating entry function. Kinds:

- **D** (differential): before/after a call.
- **A** (absolute): the whole balance is taken as an amount.
- **V** (valuation): the balance enters a price or total.
- **C** (cap/sourcing): the balance only bounds or sources a payout.

B1 hazard rule: an **A** or **V** read on a custody cell that backs two or more logical pools (|κ⁻¹(c)| ≥ 2), reachable at rank R, is an aliasing-absorption counterexample at rank R.

Mechanically found sites: **74**. Sites reachable from open or `cond` actions: **49**. Each of these carries a manual verdict.

| Bundle line | Reach | Kind | Token(s) | Reached from | Verdict |
|---|---|---|---|---|---|
| L157 | gated | — | _token, index | ConcentratorCompounderStash.process, ConcentratorCompounderStash.processBatch | gated-only site (R2+/R4); see subsystem report |
| L694 | open | A | reward_tokens | ConcentratorSdCrvGaugeWrapper.initialize, ConcentratorSdCrvGaugeWrapper.syncActiveRewardTokens | New gauge reward token: whole balance notified as reward. Donations become rewards (benign). Aliasing would need reward token == a principal token held here; the wrapper forwards principal to the locker [C]. |
| L1423 | open | D | index | SdCrvCompounder.harvest | Before-snapshot for the claim window at L1426–L1427. Tokens outside `getActiveRewardTokens()` are not counted (see 02-concentrator). |
| L1430 | open | D | index | SdCrvCompounder.harvest | After-read of the same window. |
| L2384 | gated | — | _token | ConcentratorCompounderStash.process | gated-only site (R2+/R4); see subsystem report |
| L2419 | gated | — | index | ConcentratorCompounderStash.processBatch | gated-only site (R2+/R4); see subsystem report |
| L3449 | gated | — | index | StakeDAOGaugeWrapperStash.withdrawTokens | gated-only site (R2+/R4); see subsystem report |
| L4461 | open | V | Furnace.CVX | Furnace.deposit, Furnace.depositFor, Furnace.distribute (+1) | `totalCVXInPool`: custody enters the realisation price. Donations are absorbed into pending distribution (see 03-clever). |
| L4463 | open | V | Furnace.CVX_REWARD_POOL | Furnace.deposit, Furnace.depositFor, Furnace.distribute (+1) | Same valuation: staked CVX part. |
| L4547 | gated | — | Furnace.CVXCRV | Furnace.harvest | gated-only site (R2+/R4); see subsystem report |
| L4781 | open | C | Furnace.CVX | Furnace.claim, Furnace.exit | Liquidity sourcing: withdraw the shortfall from the reward pool. Safe. |
| L4821 | gated | — | Furnace.CVX_REWARD_POOL | Furnace.distribute, Furnace.harvest | gated-only site (R2+/R4); see subsystem report |
| L5079 | open | V | MetaFurnace.baseToken | MetaFurnace.deposit, MetaFurnace.distribute, MetaFurnace.harvest | `totalBaseTokenInPool` uses SafeMath `.sub(_leftover)`. Reverts when leftover > balance (exit-liveness, 03-clever T07). |
| L5386 | open | C | MetaFurnace.baseToken | MetaFurnace.claim, MetaFurnace.exit | Liquidity sourcing from the strategy. Safe. |
| L7324 | open | C | MarketV2.baseToken | MarketV2.redeemFToken, MarketWithFundingCost.redeemFToken | `min(balance, baseOut)` cap after treasury redeem. Can only reduce the payout. Safe. |
| L7374 | open | C | MarketV2.baseToken | MarketV2.redeemXToken, MarketWithFundingCost.redeemXToken | Same cap for xToken redeem. |
| L9099 | open | D | CLeverAMOBase.baseToken | AladdinCVX.checkpoint, AladdinCVX.harvest, AladdinCVX.rebalance (+3) | Furnace claim window. Safe. |
| L9101 | open | D | CLeverAMOBase.baseToken | AladdinCVX.checkpoint, AladdinCVX.harvest, AladdinCVX.rebalance (+3) | Furnace claim window. Safe. |
| L9122 | open | D | RewardClaimable.rewards[] | AladdinCVX.harvest | Strategy-harvest window (Y^𝒫 strategy). Safe if the strategy is honest [R4]. |
| L9130 | open | D | RewardClaimable.rewards[] | AladdinCVX.harvest | Same window: rewardPerShare += Δ/totalSupply. |
| L9538 | open | V | TreasuryV2.baseToken | WrappedTokenTreasuryV2.harvest | `harvestable = balance − wrapped(totalBaseToken)`. A donation becomes distributable reward, giving an R1 reward-injection capability (feeds the K1 schedule, 01-kernel K1-I3). |
| L9771 | gated | — | TreasuryV2.baseToken | TreasuryWithFundingCost.initializeProtocol, WrappedTokenTreasuryV2.initializeProtocol | gated-only site (R2+/R4); see subsystem report |
| L9863 | gated | — | TreasuryV2.baseToken | TreasuryWithFundingCost.redeem, WrappedTokenTreasuryV2.redeem | gated-only site (R2+/R4); see subsystem report |
| L9870 | gated | — | TreasuryV2.baseToken | TreasuryWithFundingCost.redeem, WrappedTokenTreasuryV2.redeem | gated-only site (R2+/R4); see subsystem report |
| L10399 | open | V | AladdinCRV.CVXCRV_STAKING | AladdinCRV.deposit, AladdinCRV.depositAll, AladdinCRV.depositAllWithCRV (+4) | `totalUnderlying` = staking balance. `stakeFor(aCRV)` donation inflates the share price, enabling first-depositor inflation (02-concentrator). |
| L10434 | open | D | AladdinCRV.CVXCRV | AladdinCRV.deposit, AladdinCRV.depositAll | Transfer-in measurement (fee-on-transfer tolerant). Safe. |
| L10436 | open | D | AladdinCRV.CVXCRV | AladdinCRV.deposit, AladdinCRV.depositAll | Same. |
| L10453 | open | D | AladdinCRV.CRV | AladdinCRV.depositAllWithCRV, AladdinCRV.depositWithCRV | Same (CRV). |
| L10455 | open | D | AladdinCRV.CRV | AladdinCRV.depositAllWithCRV, AladdinCRV.depositWithCRV | Same (CRV). |
| L10572 | gated | — | 0xA7f552078dcC247C2684336020c03648500C6d9F | AladdinCRV.claimEPS | gated-only site (R2+/R4); see subsystem report |
| L10609 | open | A | AladdinCRV.CVXCRV | AladdinCRV.withdraw, AladdinCRV.withdrawAll | Last withdrawer receives the whole cvxCRV balance (by design; absorbs donations). |
| L10656 | open | A | AladdinCRV.CVX | AladdinCRV.harvest, AladdinCRV.withdraw, AladdinCRV.withdrawAll | Harvest sweeps the whole CVX balance. |
| L10658 | open | A | AladdinCRV.THREE_CRV | AladdinCRV.harvest, AladdinCRV.withdraw, AladdinCRV.withdrawAll | Harvest sweeps the whole 3CRV balance. |
| L10662 | open | A | AladdinCRV.CRV | AladdinCRV.harvest, AladdinCRV.withdraw, AladdinCRV.withdrawAll | Harvest sweeps the whole CRV balance. |
| L10665 | open | A | AladdinCRV.CVXCRV | AladdinCRV.harvest, AladdinCRV.withdraw, AladdinCRV.withdrawAll | Harvest output = whole cvxCRV balance. |
| L11105 | open | D | ConcentratorConvexVault.poolInfo.lpToken | AladdinFXSConvexVault.deposit | LP transfer-in measurement. Safe. |
| L11107 | open | D | ConcentratorConvexVault.poolInfo.lpToken | AladdinFXSConvexVault.deposit | Same. |
| L11212 | open | A | index | AladdinFXSConvexVault.harvest | **Cross-pool absorption.** Absolute reward-token balances are attributed to pool `_pid` after `getReward` for that pool only. Any account can push another pool's Convex rewards into the vault first (`getReward(vault, true)` is permissionless on Convex) [B1, R1]. |
| L11997 | open | D | AladdinCRVConvexVault.poolInfo.lpToken | AladdinCRVConvexVault.deposit, AladdinCRVConvexVault.depositAll, AladdinCRVConvexVault.zapAllAndDeposit (+1) | LP transfer-in measurement. Safe. |
| L11999 | open | D | AladdinCRVConvexVault.poolInfo.lpToken | AladdinCRVConvexVault.deposit, AladdinCRVConvexVault.depositAll, AladdinCRVConvexVault.zapAllAndDeposit (+1) | Same. |
| L12062 | open | D | AladdinCRVConvexVault.poolInfo.lpToken | AladdinCRVConvexVault.zapAllAndDeposit, AladdinCRVConvexVault.zapAndDeposit | Zap-and-deposit LP measurement. |
| L12064 | open | D | AladdinCRVConvexVault.poolInfo.lpToken | AladdinCRVConvexVault.zapAllAndDeposit, AladdinCRVConvexVault.zapAndDeposit | Same. |
| L12208 | open | D | _token | AladdinCRVConvexVault.withdrawAllAndZap, AladdinCRVConvexVault.withdrawAndZap | Withdraw-and-zap output measurement. |
| L12210 | open | D | _token | AladdinCRVConvexVault.withdrawAllAndZap, AladdinCRVConvexVault.withdrawAndZap | Same. |
| L12289 | open | A | _token | AladdinCRVConvexVault.harvest | **Cross-pool absorption** in AladdinCRVConvexVault.harvest: absolute reward-token balances. L12283 also takes the vault's whole ETH balance [B1, R1 push + R1/R2 harvest]. |
| L12300 | open | A | AladdinCRVConvexVault.CRV | AladdinCRVConvexVault.harvest | Absolute CRV balance attributed to `_pid`. |
| L12586 | open | D | AladdinCRVConvexVault.CVXCRV | AladdinCRVConvexVault.harvest | CRV→cvxCRV swap measurement. |
| L12594 | open | D | AladdinCRVConvexVault.CVXCRV | AladdinCRVConvexVault.harvest | Same. |
| L13257 | gated | — | CLeverCVXLocker.CVX | CLeverCVXLocker.processUnlockableCVX | gated-only site (R2+/R4); see subsystem report |
| L13258 | gated | — | CLeverCVXLocker.CVX_REWARD_POOL | CLeverCVXLocker.processUnlockableCVX | gated-only site (R2+/R4); see subsystem report |
| L13388 | open | C | CLeverCVXLocker.CVX | CLeverCVXLocker.withdrawUnlocked | Liquidity sourcing from the CVX reward pool. Safe. |
| L13487 | open | D | index | CLeverCVXLocker.harvest | Locker/reward-pool getReward window. Safe. |
| L13497 | open | D | index | CLeverCVXLocker.harvest | Same. |
| L13677 | gated | — | CLeverCVXLocker.CVX | CLeverCVXLocker.processUnlockableCVX | gated-only site (R2+/R4); see subsystem report |
| L13679 | gated | — | CLeverCVXLocker.CVX | CLeverCVXLocker.processUnlockableCVX | gated-only site (R2+/R4); see subsystem report |
| L13873 | gated | — | index | CLeverCVXLocker.withdrawManualSwapRewardTokens | gated-only site (R2+/R4); see subsystem report |
| L14029 | gated | — | CLeverCVXLocker.WETH | CLeverCVXLocker.harvestPaladinLikeBribes, CLeverCVXLocker.harvestUniversalRewardsDistributorBribes, CLeverCVXLocker.harvestVotiumLikeBribes | gated-only site (R2+/R4); see subsystem report |
| L14048 | gated | — | CLeverCVXLocker.WETH | CLeverCVXLocker.harvestPaladinLikeBribes, CLeverCVXLocker.harvestUniversalRewardsDistributorBribes, CLeverCVXLocker.harvestVotiumLikeBribes | gated-only site (R2+/R4); see subsystem report |
| L14054 | gated | — | CLeverCVXLocker.CVX | CLeverCVXLocker.harvestPaladinLikeBribes, CLeverCVXLocker.harvestUniversalRewardsDistributorBribes, CLeverCVXLocker.harvestVotiumLikeBribes | gated-only site (R2+/R4); see subsystem report |
| L14057 | gated | — | CLeverCVXLocker.CVX | CLeverCVXLocker.harvestPaladinLikeBribes, CLeverCVXLocker.harvestUniversalRewardsDistributorBribes, CLeverCVXLocker.harvestVotiumLikeBribes | gated-only site (R2+/R4); see subsystem report |
| L14079 | open | V | CLeverCVXLocker.CVX_REWARD_POOL | CLeverCVXLocker.donate, CLeverCVXLocker.harvest, CLeverCVXLocker.harvestPaladinLikeBribes (+2) | Stake-percentage rebalancing; no claim depends on it. Safe. |
| L14080 | open | V | CLeverCVXLocker.CVX | CLeverCVXLocker.donate, CLeverCVXLocker.harvest, CLeverCVXLocker.harvestPaladinLikeBribes (+2) | Same. |
| L14721 | gated | — | ShareableRebalancePool.asset | ShareableRebalancePoolV2.liquidate | gated-only site (R2+/R4); see subsystem report |
| L14729 | gated | — | ShareableRebalancePool.asset | ShareableRebalancePoolV2.liquidate | gated-only site (R2+/R4); see subsystem report |
| L15130 | gated | — | ShareableRebalancePool.asset | ShareableRebalancePool.liquidate | gated-only site (R2+/R4); see subsystem report |
| L15138 | gated | — | ShareableRebalancePool.asset | ShareableRebalancePool.liquidate | gated-only site (R2+/R4); see subsystem report |
| L15265 | open | D | ShareableRebalancePool.fxn | ShareableRebalancePool.acceptSharedVote, ShareableRebalancePool.checkpoint, ShareableRebalancePool.claim (+17) | FXN gauge-mint window. The measurement is safe, but the subsequent `_notifyReward` at L15269 precedes accrual: **K1-Pre1 violated** (01-kernel K1-F2). |
| L15267 | open | D | ShareableRebalancePool.fxn | ShareableRebalancePool.acceptSharedVote, ShareableRebalancePool.checkpoint, ShareableRebalancePool.claim (+17) | Same. |
| L16237 | gated | — | BoostableRebalancePool.asset | BoostableRebalancePool.liquidate | gated-only site (R2+/R4); see subsystem report |
| L16245 | gated | — | BoostableRebalancePool.asset | BoostableRebalancePool.liquidate | gated-only site (R2+/R4); see subsystem report |
| L16302 | open | D | BoostableRebalancePool.fxn | BoostableRebalancePool.checkpoint, BoostableRebalancePool.claim, BoostableRebalancePool.claimHistorical (+3) | FXN gauge-mint window. `_notifyReward` at L16306 precedes accrual at L16309: **K1-Pre1 violated** (01-kernel K1-F2). |
| L16304 | open | D | BoostableRebalancePool.fxn | BoostableRebalancePool.checkpoint, BoostableRebalancePool.claim, BoostableRebalancePool.claimHistorical (+3) | Same. |
| L17188 | open | D | MarketV2.baseToken | MarketWithFundingCost.mintFToken, MarketWithFundingCost.mintXToken, MarketWithFundingCost.redeemFToken (+1) | Funding-cost harvest window; the bounty goes to the platform. Safe. |
| L17190 | open | D | MarketV2.baseToken | MarketWithFundingCost.mintFToken, MarketWithFundingCost.mintXToken, MarketWithFundingCost.redeemFToken (+1) | Same. |

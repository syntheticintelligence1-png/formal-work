# Atlas 1 — Action census (mechanized)

Source: `harness/tools/footprint.py`, which walks solc ASTs from the Hardhat build-info. It covers every external or public **mutating** entry function of every concrete bundle contract, with inherited functions resolved through the contract's C3 linearization.

## Column definitions

| Column | Meaning |
|---|---|
| `open` | No sender gate on any path |
| `cond` | Gated only when `harvester ≠ 0`, via `ensureCallerIsHarvester` (L862). With the harvester unset, the action is effectively `open`. |
| `gated` | A modifier or body compares the sender with storage, or performs a role check |
| `clock` | Samples `block.timestamp` |
| `yield` | Has at least one non-static external call |
| `W-after-Y⁺` | Writes storage after a yield point whose callee is policy-, user- or externally-derived (YP, YU, Yext, ?) |

| Contract | Mutating actions | open | cond | gated | init | clock | yield | W-after-Y⁺ | locked (`nonReentrant`) |
|---|---|---|---|---|---|---|---|---|---|
| AladdinCRV | 22 | 12 | 1 | 8 | 1 | 0 | 8 | 5 | 7 |
| AladdinCRVConvexVault | 31 | 16 | 1 | 13 | 1 | 0 | 16 | 13 | 16 |
| AladdinCVX | 26 | 13 | 1 | 11 | 1 | 2 | 11 | 4 | 0 |
| AladdinFXSConvexVault | 21 | 6 | 1 | 13 | 1 | 5 | 6 | 2 | 5 |
| BoostableRebalancePool | 20 | 9 | 0 | 10 | 1 | 12 | 10 | 3 | 6 |
| CLeverCVXLocker | 26 | 8 | 0 | 18 | 0 | 4 | 12 | 5 | 0 |
| ConcentratorCompounderStash | 4 | 0 | 0 | 4 | 0 | 0 | 2 | 0 | 0 |
| ConcentratorSdCrvGaugeWrapper | 30 | 15 | 0 | 14 | 1 | 17 | 14 | 4 | 13 |
| Furnace | 21 | 7 | 0 | 13 | 1 | 9 | 8 | 4 | 0 |
| MarketV2 | 19 | 4 | 0 | 14 | 1 | 0 | 4 | 0 | 4 |
| MarketWithFundingCost | 19 | 4 | 0 | 14 | 1 | 0 | 4 | 0 | 4 |
| MetaFurnace | 17 | 7 | 0 | 9 | 1 | 8 | 8 | 4 | 0 |
| SdCrvCompounder | 26 | 16 | 1 | 9 | 0 | 11 | 12 | 3 | 7 |
| ShareableRebalancePool | 24 | 9 | 0 | 14 | 1 | 16 | 14 | 3 | 6 |
| ShareableRebalancePoolV2 | 24 | 9 | 0 | 14 | 1 | 16 | 14 | 3 | 6 |
| StakeDAOBribeClaimer | 4 | 0 | 0 | 4 | 0 | 0 | 1 | 0 | 0 |
| StakeDAOGaugeWrapperStash | 1 | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 0 |
| TreasuryWithFundingCost | 21 | 1 | 0 | 19 | 1 | 7 | 6 | 1 | 0 |
| WrappedTokenTreasuryV2 | 21 | 1 | 0 | 19 | 1 | 7 | 6 | 1 | 0 |
| **Σ** | **377** | **137** | **5** | **221** | **14** | **114** | **157** | **55** | **74** |

## Approximations

- Branches are concatenated, so every reported write and call is *possible* on some path. Absence is exact; presence is an over-approximation.
- Loops are walked once.
- Calls through function-typed values are not followed.
- Sender gating is detected from evidence: `msg.sender`/`_msgSender()` compared with storage, a bool storage mapping indexed by sender, or `hasRole`/`_checkRole`/`_checkOwner`.

# 02 — Concentrator subsystem: SBD analysis

**Scope.**

| Area | Contracts |
|---|---|
| StakeDAO side | `ConcentratorStakeDAOGaugeWrapper` (L490) + `ConcentratorSdCrvGaugeWrapper` (L3763, `periodLength = 7 days`, L3827); stashes L133, L2309, L3402; `StakeDAOBribeClaimer` (L3957) |
| Compounders | `AladdinCompounder` (L2748) + `SdCrvCompounder` (L1182); `SdCRVLocker` (L2606) |
| Convex side | `AladdinCRV` (L10312); `ConcentratorConvexVault` (L10833) + `AladdinFXSConvexVault` (L17736); `AladdinCRVConvexVault` (L11795) |
| Shared | `ConcentratorBase`/`V2` (L808, L953); kernels K1–K3, K5, K6 (obligation discharge only) |

Terminology follows `00-sbd-framework.md`.

**Provenance.**

- The Concentrator analysis agent produced the primary analysis.
- The coordinator **re-executed every bytecode trace (h1–h4)** in the repository harness. The output hashes are byte-identical to the agent's workspace.
- The coordinator re-read the cited lines for each finding below.
- Traces are under `harness/scripts/concentrator/`, mocks under `harness/contracts/harness/concentrator/`, and Python models with their recorded outputs under `harness/models/concentrator/`.
- The only additions to bundle contracts are two harness subclasses:
  - `SdCrvCompounderHarness.init()`, because the bundle's `SdCrvCompounder` has no initializer;
  - `FXSVaultHarness.zapAsRewardTokenX()`, which exposes an internal function.

---

## 1. Abstraction statement

### Wiring

- `SdCrvCompounder` → `wrapper` (immutable, L1297) → `locker` (L544) → StakeDAO gauge.
- The wrapper sends extra rewards to its `stash` (L583).
- `SdCrvCompounder` has its own `stash` (L1307), which calls `depositReward(uint256)` (L1482). That stash's code is not in the bundle.
- `ConcentratorCompounderStash` cannot serve as that stash. It requires `harvester()`, `converter()`, `treasury()` and the fee-ratio getters on its compounder (L2350, L2386, L2456–L2467), and `SdCrvCompounder` implements none of them.
- `AladdinFXSConvexVault` → aFXS (not in the bundle). `AladdinCRVConvexVault` → `AladdinCRV`.

### Environment model

- External venues (Convex, StakeDAO, Curve, zap, converter) are nondeterministic environment actions with stated contracts (§4).
- ERC20 tokens are standard: no transfer fee, no hooks.
- Transactions are atomic (revert = identity).
- Time is monotone between transactions.

### Omitted

- CLever and f(x): no in-scope contract calls them.
- `AladdinCRV.claimEPS`: BSC-only, R4.

### Additional terms (defined before use)

| Term | Definition |
|---|---|
| **Vest** | `rate·Δ`, with `Δ = now − L` if `now ≤ F`, else `(F − L)⁺` (as at L2851–L2857) |
| **Unv** | `rate·(F − max(now, L))⁺` |
| **Ghost share** | `g = totalSupply − Σ_u balanceOf[u] > 0` in an accumulator that integrates against `totalSupply` |
| **Cross-pool absorption** | Aliasing absorption between the reward pools of different `pid`s that share a cell `(τ, vault)` |
| **Empty interval** | A maximal time interval in which the share supply is 0 while `rate > 0` |
| **Re-activation** | A token moving from the historical set back to the active set by a path other than `registerRewardToken` |

---

## 2. State space (persistent; stratum assignment)

`atlas/A5-write-authority.md` gives the mechanically computed 𝒫 / dynamic partition for these contracts. Two variables the specification treats as policy are written by unprivileged paths: `activeRewardTokens`, via `syncActiveRewardTokens`, and `SdCrvCompounder.stash`, via `initializeV2`. These are the **policy leaks** behind CONC-14 and CONC-12.

### Gauge wrapper (`ConcentratorSdCrvGaugeWrapper` with K1/K2/K3)

| Variable | Type / domain / init | Stratum | Line |
|---|---|---|---|
| `gauge`, `stakingToken`, `locker`, `delegation`, `bribeClaimer` | immutable | 𝒫₀ | L538–L547, L3816 |
| `SDT`, `CRV`, `sdCRV`, `SD_VE_CRV`, `DEPOSITOR`, `CURVE_POOL` | constant | 𝒫₀ | L535, L3801–L3813 |
| `periodLength` | uint40, 7 days | 𝒫₀ | L3582, L3827 |
| `totalSupply` | uint256; init = `legacy.totalSupply()` | ℒ | L554, L3852 |
| `balanceOf[u]` | uint256; asdCRV init = `legacy.balanceOf(asdCRV)` | ℒ | L557, L3851 |
| `stash` | address, written once | 𝒫 | L560, L583 |
| `treasury`, `harvester` (=0), `converter` | address | 𝒫 | L1001–L1007 |
| `_miscData` | bytes32: four 30-bit fields at offsets 0/30/60/90 | 𝒫 | L1024, L532 |
| `distributors[τ]` | address | 𝒫 | L3589 |
| `activeRewardTokens` | set; init = gauge tokens ∪ {stakingToken}; **R1-extensible (L685)** | 𝒫 (leaky) | L3595, L3844 |
| `historicalRewardTokens` | set | 𝒫 | L3598 |
| `rewardData[τ]` | K1 state | ℒ / 𝒯 | L3592 |
| `rewardSnapshot[τ].integral` | uint192 | ℐ | L2100 |
| `userRewardSnapshot[u][τ]` | {pending, claimed: uint128; checkpoint.integral: uint192} | ℒ + ℐ | L2105 |

Custody cells: `bal(τ, wrapper)`; `gauge.balanceOf(locker)`, which is **shared with the legacy vault**; `bal(τ, stash)`.

### Compounder (`SdCrvCompounder` ∘ `AladdinCompounder` ∘ `SdCRVLocker` ∘ `FeeCustomization` ∘ `ConcentratorBase`)

| Variable | Domain | Stratum | Line |
|---|---|---|---|
| `legacyVault`, `wrapper`; token constants | | 𝒫₀ | L1275–L1297 |
| `zap` | address | 𝒫 | L1304 |
| `stash` | 0 until `initializeV2` | 𝒫 (leaky) | L1307 |
| ERC20 `TS` (totalSupply), balances, allowances | | ℒ | OZ 3.4 |
| `feeInfo` {platform, platformPercentage ≤ 2e8, bountyPercentage ≤ 1e8, withdrawPercentage ≤ 1e8} | | 𝒫 | L2808–L2817, L3037–L3040 |
| `rewardInfo.periodLength` (P) | uint32, **unguarded, 0 allowed** | 𝒫 | L2825, L3049 |
| `rewardInfo.rate`, `lastUpdate` (L), `finishAt` (F) | uint128 / uint48 / uint48 | 𝒯 | L2822–L2827 |
| `totalAssetsStored` (TAS) | uint256 | ℒ | L2837 |
| fee customization | ≤ 1e8 (L3059) | 𝒫 | L4031 |
| `harvester` | 0 ⇒ anyone may harvest | 𝒫 | L834–L866 |
| `locks[u][i]`, `nextLockIndex[u]` | | ℒ | L2641–L2644 |

Custody cells: `W := wrapper.balanceOf[compounder]`; `bal(sdCRV, compounder)` backing the legacy locks (L3858).

### `AladdinCRV`

- ℒ: ERC20 balances and supply.
- 𝒫: `zap`, `platform`, three fees (L10359–L10368).
- 𝒫₀: constants (L10344–L10356).
- **The custody balance is read directly as the ledger total.** `totalUnderlying()` = `CVXCRV_STAKING.balanceOf(aCRV)` (L10397–L10400). See `atlas/A3` row L10399.

### `ConcentratorConvexVault` + `AladdinFXSConvexVault`

- Per pool:
  - ℒ: `totalUnderlying`, `totalShare`;
  - ℐ: `accRewardPerShare`;
  - 𝒫: `lpToken`, `crvRewards`, fees, pause flags, `convexRewardTokens` (L10920–L10945).
- Per-pool `rewardInfo`: `rate`, `lastUpdate`, `finishAt` are 𝒯; `periodLength` is 𝒫 (L10908–L10918).
- Per user: shares and rewards are ℒ; `rewardPerSharePaid` is ℐ (L10947–L10956).
- **Constants `FXS = cvxFXS = 0x3432B6A6…` (L17756, L17760).**
- Custody:
  - principal: `crvRewards_p.balanceOf(vault)`;
  - rewards: `bal(aFXS, vault)`, **shared by all pools**;
  - transient: `bal(τ, vault)`, **shared by all pools**.

### `AladdinCRVConvexVault`

- The same per-pool and per-user fields, without per-pool `rewardInfo` (L11837–L11871).
- 𝒫: `aladdinCRV`, `zap`, `platform`, `migrator`.

---

## 3. Action footprints (summary)

The complete mechanized footprints are in `atlas/A1`–`A4` and `atlas/footprint.json`. Only the specification-relevant structure is listed here.

### Gauge wrapper

| Action | Guard | Effect | Notes |
|---|---|---|---|
| `deposit*` (L600 …) | amount ≠ 0 (L735) | `_checkpoint(receiver)` → balance and supply += | locked; yields Y⁰ |
| `withdraw` (L622) | | `_checkpoint(owner)` → balance and supply −= | `locker.withdraw` last |
| `harvest` (L644) | **open** | `_checkpoint(0)` → stash BDR (D) → fees → `_notifyReward` | |
| **`harvestBribes`** (L3869) | **open**; locked | SDT: fees, then **`_notifyReward(SDT, …)` (L3891) with no prior `_distributePendingReward`** | |
| **`syncActiveRewardTokens`** (L685) | **open**; **unlocked** | adds gauge tokens to `active`; **absolute BDR** of the new token's balance → `_notifyReward` (L694–L696) | |
| `checkpoint`, `claim*`, `claimHistorical*` | K3 guards | pending zeroed before transfer | locked |
| `depositReward` (K2, L3650) | distributor only | accrue → notify | **unlocked** |

### Stashes

| Action | Guard | Effect |
|---|---|---|
| `StakeDAOGaugeWrapperStash.withdrawTokens` | sender = wrapper (L3444) | whole-balance send |
| `ConcentratorCompounderStash.process` / `processBatch` | sender = `compounder.harvester()`; if that is 0, nobody (L2350) | `_transfer` (absolute BDR, L157) → `_convert` → `_distribute` → `depositReward` |

### Compounder

| Action | Effect | Notes |
|---|---|---|
| `deposit` (L2940), `mint` (L2953), `depositWithCRV`, `depositWithSdVeCRV` | `_distributePendingReward` → pull → wrapper deposit → `_mintShare`: shares = a if TAS = 0, else ⌊a·TS/TAS⌋; TAS += a | locked |
| `depositWithGauge` (L1352) | as above | **unlocked**; Y⁰ only |
| `withdraw` (L2964) | shares = ⌊a·TS/TA⌋, scaled by 1e9/(1e9 − fee) if a < TA | |
| `redeem` (L2997) | | |
| `_withdraw` (L1546) | amount = ⌊s·TAS/TS⌋, **no fee**; burn; TAS −= amount; `wrapper.withdraw` | |
| `harvest` (L1408) | claims (D, L1421–L1430) → zap with **minOut 0** → mint fee shares → `_notifyHarvestedReward` | `cond[harvester]` |
| `depositReward` (L1482) | | stash only; unlocked |
| `initializeV2` (L1318) | | **no access control** |
| `updateRewardPeriodLength` (L3049) | | **unguarded; 0 allowed** |

### `AladdinCRV`

- `deposit` (L10432) is D-measured (L10434–L10436). Shares = ⌊a·TS/U⌋ with `U = totalUnderlying()`, which is the V-read at L10399.
- The last withdrawer takes the whole balance (L10609).
- `harvest` sweeps absolute balances with minOut 0 (L10656–L10665).

### Convex vaults

- All mutators of `ConcentratorConvexVault` are locked. In `AladdinCRVConvexVault`, `deposit` (L11982) is unlocked, but its `_deposit` (L12475) is locked.
- `harvest(pid)`:
  - `ConcentratorConvexVault` (L11195): `getReward` for `pid`, then reads the **absolute vault balance** of each listed token (L11209–L11213).
  - `AladdinCRVConvexVault`: the same pattern, **plus the whole ETH balance (L12283) and the whole CRV balance (L12300)**.
- `claim` (`_claim`):
  - FXS vault: yields to aFXS `redeem` (Y^𝒫), the zap (Y^𝒫), and either an ETH send to **`msg.sender`** (L17827) or a transfer of the user-chosen token.
  - CRV vault: L12201–L12206.
- `migrate` (L12138) checks neither the pause flag nor the fee.

---

## 4. Specification (invariants as predicates)

### Compounder (AC)

| ID | Predicate | Source |
|---|---|---|
| AC-1 | `W ≥ TAS + Vest + Unv` (B5/B1) | implicit; "the value is correct" L1459, L1530, L1553 |
| AC-2 | `TS = 0 ⇒ TAS = 0` | implicit; `_mintShare` relies on it (L1533) |
| AC-3 | `deposit(a)` loses less than one share's worth | ERC-4626 NatSpec L1706–L1711 |
| AC-4 | preview bounds and closeness | ERC-4626 NatSpec L1701–L1772 |
| AC-5 | `withdraw` and `mint` are exact; `max*` return the true limit | ERC-4626 |
| AC-6 | non-last exit: delivered = gross·(1 − f), and the fee stays in the pool | L2932–L2933, L2978–L2981 |
| AC-7 | flow property and CII (B3) | framework |
| AC-8 | policy writes are prospective (B4) | framework |
| AC-9 | exit is always possible | framework |
| AC-10 | the divisor at L2980 is > 0 (K6) | L2980 |
| AC-11 | `bal(sdCRV, compounder)` ≥ open legacy locks | L1572 |
| AC-12 | `_notifyHarvestedReward` is preceded by a Vest credit | L3116 |

### Gauge wrapper (GW)

| ID | Predicate |
|---|---|
| GW-1 | O3a |
| GW-2 | O3b |
| GW-3 | O3c |
| GW-4 | O3d: principal and reward custody never overlap |
| GW-5 | K1-Pre1 holds at every `_notifyReward` |
| GW-6 | ∀τ: `bal(τ, wrapper) ≥ Σ claimable + distributable + undistributed + queued` |
| GW-7 | `active ∩ historical = ∅`; `active` grows only through R3 or initialization (L3675, L3681) |
| GW-8 | locker gauge balance ≥ Σ `balanceOf` |
| GW-9 | expense + harvester + booster ≤ 1e9 (needed by the unchecked subtraction at L679) |
| GW-10 | K5 |
| GW-11 | CII up to a quantized defect |

### Stashes (ST)

- **ST-1**: each stash cell backs exactly one logical pool.
- **ST-2**: `processBatch` conserves value as its NatSpec says (L2394–L2404).
- **ST-3**: access control holds.

### Convex vaults (CV, AV) and `AladdinCRV` (AR)

| ID | Predicate | Source |
|---|---|---|
| CV-1 | per-pool rounding has polarity ≤ 0 | framework |
| CV-2 | every share change is preceded by `_updateRewards(p, u)` | framework |
| **CV-3 / AV-1** | `harvest(p)` credits pool `p` only with `p`'s own rewards | framework |
| **CV-4** | `_claim` pays only from the claimant's own reward cell; the vault's FXS balance is unchanged | framework |
| **CV-5** | the ETH claim pays `_amountOut` to the recipient | L11557–L11562, L12773–L12784 |
| CV-6 | period changes are prospective | framework |
| CV-7 | `bal(aFXS, vault) ≥ Σ pending + Vest + Unv` (B5) | framework |
| CV-8 | principal is backed | framework |
| CV-9 | exits are live | framework |
| AV-2 | aCRV gluing | framework |
| AV-3 | every exit respects the pause flag and the fee | L12446–L12453 |
| **AR-1** | no deposit is diluted by third-party inflation of `U` | framework |
| AR-2 | the withdraw fee stays staked | L10613–L10615 |
| AT-1 | atomicity across Y^U yields | framework |

---

## 5. Assumption ledger

| ID | Assumption | Tag | Relaxation and consequence |
|---|---|---|---|
| A-ERC20 | No fee-on-transfer, no hooks | [C] L3671 | Fee-on-transfer breaks GW-6 |
| A-WRAP | The wrapper credits exactly what it returns | [E] L600–L751, L3903–L3952 | — |
| A-LOCK | The StakeDAO locker forwards exactly `claims[i].amount` | [L] | Over-notification (CONC-18) |
| A-SDVE | `sdveCRV` locks 1:1 | [C] L1624 | Any shortfall is drawn from the sdCRV reward cell (CONC-19) |
| A-LEGACY | At wrapper initialization, `legacy.totalSupply = legacy.balanceOf(asdCRV)` | [L] | Ghost shares (CONC-07) |
| A-GAUGE-LIST | Gauges never remove reward tokens | [L] | Makes CONC-14 permanent |
| A-CVX-PERM | Convex `BaseRewardPool.getReward(account, bool)` is permissionless; the bundle's interface (L10248) lists only `getReward()` | [L] | Enables the R1 trigger of CONC-09 and CONC-02 |
| A-CVX-STAKEFOR | Convex `stakeFor` is permissionless | [L] (TODO at L10398) | CONC-10 |
| A-ZAP | The zap converts at market price | [L] | MEV (CONC-11) |
| A-CONV | The converter consumes exactly `amountIn` already held; zero input returns 0 or reverts | [C] L224–L306 | CONC-13 becomes liveness-only if zero input reverts |
| A-AFXS | aFXS redeems into real cvxFXS (≠ FXS) | [L] | CONC-02 |
| A-HARV | `harvester ≠ 0` | [L] (L865) | CONC-11; the rank of harvest-dependent items drops to R1 |
| A-P | `rewardInfo.periodLength ≠ 0` | [L] (0 is a documented mode, L2824) | CONC-06 |
| A-INIT | `initializeV2` is atomic with the upgrade | [L] | CONC-12 |
| A-FEE-CUST | No customized fee is above the default | [L] | RG-9 |

---

## 6. Abstract transition system

```
S   = S_GW × S_GS × S_CS × S_AC × S_AR × S_CV × S_AV × Env
Env = (now, venue balances, venue accrual, bribe merkle entitlements, all token cells, zap/converter prices, aFXS state)
S0  = post-initialization states, including the wrapper's legacy initialization (L3849–L3852)
Act = user actions
    ∪ permissionless keeper actions {GW.harvest, GW.harvestBribes, GW.syncActiveRewardTokens, AC.checkpoint, harvest if harvester = 0}
    ∪ R2 {stash.process*}
    ∪ R3 {register/unregister/updateDistributor}
    ∪ R4 setters
    ∪ Env {tick, accrue, poke (permissionless venue getReward), donate, reprice}
→   = each action is the atomic relation given by its footprint (§3, atlas)
```

Revert is the identity. Reentrancy is admitted only at Y^U callees.

**Abstracted:** price impact, gas, venue internals.

---

## 7. Counterexample search per invariant

**PE-c** = Proven-executed, re-executed by the coordinator.

### Compounder

**AC-1. Holds, with a surplus.** Every increase of TAS or of the stream follows an equal wrapper credit:

- L1518→L1520, L1360→L1362, L1380→L1382, L1402→L1404;
- L1448/L1452→L1473/L1477;
- L1488→L1490.

`W` decreases only at L1563, together with TAS at L1561. All floors favour the protocol.

- Minimal assumption: A-WRAP. Relaxation: an under-crediting wrapper gives `W < TAS`.

**AC-2. FAILS when P = 0 (CONC-06).** PE-c, `h1.P0`.

1. TS = 0, TAS = 0, P = 0. The stash calls `depositReward(10e18)`, which takes the P = 0 branch (L3121): TAS = 10e18.
2. Alice deposits 100e18. TAS ≠ 0, so shares = ⌊100e18·0/10e18⌋ = **0**. Now TAS = 110e18, TS = 0.
3. Alice's `redeem` reverts: "asdCRV: withdraw zero share".

A fee-charging harvest into an empty vault reverts instead ("invalid opcode", a division by zero).

**AC-3 and AC-7. FAIL across an empty interval (CONC-08).** PE-c, `h1.S3`. P = 7d, rate = 1157407407407407.

1. At +1d, Alice redeems everything and receives 1099999999999999964800. TS = TAS = 0. While TAS = 0, `_distributePendingReward` does nothing, so `lastUpdate` stays frozen (L3103–L3108).
2. At +3d, Mallory deposits 1 wei and receives 1 share. `totalAssets()` = 199999999999999929601, and `previewDeposit(150e18)` = 0.
3. At +3d+1s, the victim deposits 150e18 and receives **0 shares**. TAS = 350001157407407337008.
4. Mallory redeems her 1 share and receives **350002314814814744415**. The victim's `redeem(MAX)` reverts.

*Variant.* A `depositReward` during the empty interval sets `lastUpdate = now` without crediting anything. This orphans `rate·1d` = 100000000000000067200, so AC-12 fails as well.

**AC-4, AC-5, AC-6. FAIL (CONC-04, CONC-05).** PE-c, `h1.S2`, `h1.mint`.

- Fee 5%, TS = 200e18, TAS = 210e18: `previewRedeem(10e18)` = 9975000000000000000, but `redeem(10e18)` delivers 10500000000000000000.
- `withdraw(10e18)` burns 10025062656641604009 shares and delivers 10526315789473684209.
- `withdraw(type(uint256).max)` reverts ("insufficient owner shares"), while `redeem(MAX)` succeeds.
- With TS = 2, TAS = 3: `mint(1)` pulls 1 wei and mints **0** shares.
- `maxWithdraw` and `maxRedeem` return 2²⁵⁶−1 (L2900–L2920).
- The cause of AC-6 failing: `_withdraw` never applies `getFeeRate` (L1546–L1568).

**AC-8. FAILS at R4 (CONC-15).** PE-c, `h1.S4`.

| | Bob `previewRedeem` | Bob `redeem` | Alice `redeem` at +10d |
|---|---|---|---|
| P → 0 at +1d, restored at +10d | 1099999999999999964800 | 1000000000000000000000 | 1699999999999999753600 |
| Same, with `settle*` before the write | 1099999999999999964800 | 1049999999999999982400 | 1649999999999999771200 |

The frozen stream is credited retroactively to whoever holds shares at restoration. Changes between two non-zero periods are prospective (proved).

**AC-10. Holds.** The only writer of a custom fee is L3061, bounded at L3059, so the divisor is at least 9e8. With the library bound of 1e9 (L4036), the divisor could be 0 (`m06`).

**AC-11. Holds under A-LEGACY.** Harvest measures sdCRV by difference (L1421–L1430), and `_lockToken` is never called (L2693).

### Gauge wrapper

**GW-1 (O3a). Holds by lock coverage.**

- Balances change at L634 after L631, at L746 after L737 (with only Y⁰ `locker.deposit` in between), and at L3851 during initialization.
- Every reward-integrating entry point is locked, except `depositReward` (L3650) and `syncActiveRewardTokens`.
- Relaxation (Rv + R3): a venue that is also a distributor re-enters `depositReward` during L740.

**GW-2 (O3b). Holds.** Supply changes at L635, L747 and L3852, each after `_distributePendingReward` (L2211).

**GW-3 (O3c). Holds after initialization only under A-LEGACY (CONC-07, PL).** With a ghost share `g`, a fraction `g/totalSupply` of every distribution is orphaned (L2294 divides by `totalSupply`).

**GW-4 (O3d). Violated syntactically, no B1 consequence.**

- The staking token is a registered reward token (L3844).
- Principal moves only to and from the locker (L605, L616, L3922, L3927, L638).
- The wrapper holds sdCRV only between L3945 and L3948, under lock.
- Relaxation (A-SDVE): if the lock delivers less than 1:1, L3948 draws on the reward cell (CONC-19).

**GW-5 (K1-Pre1). FAILS at L3891 (CONC-01).** PE-c, `h3.A`.

1. At T₀, `harvestBribes` notifies 70e18 SDT: rate = 115740740740740, finishAt = T₀ + 7d.
2. Nothing happens until T₀ + 8d. Then `harvestBribes` notifies another 70e18. This is branch β1 of `LinearReward.increase`, entered **without accrual**, so the first 7-day stream is never integrated.
3. At T₀ + 15d:

| | Alice claims | asdCRV claims | SDT left in the wrapper |
|---|---|---|---|
| No checkpoint before the second bribe | 35000000000000078000 | 35000000000000078000 | **69999999999999844000** (orphaned) |
| Control: one checkpoint before the second bribe | 69999999999999854000 | 69999999999999854000 | 292000 |

*Case B (β2).* A 40e18 bribe at +3d re-streams the vested part. A holder who exits at that moment receives 0, against 14999999999999904000 in the control.

This is the **same kernel-obligation failure** as `01-kernel.md` K1-F2, in a different subsystem (§9, law L2).

**GW-6 and GW-7. FAIL (CONC-14).** PE-c, `h3.B`.

1. At T₀, 70e18 SDT is notified.
2. At +8d, a checkpoint runs, then the R3 manager calls `unregisterRewardToken(SDT)`. It succeeds because `queued = 291200 < P`. SDT moves to `historical`, and its 70e18 custody now backs historical claims.
3. **Mallory (R1)** calls `syncActiveRewardTokens()`. The gauge still lists SDT, so `activeRewardTokens.add(SDT)` returns true. SDT is **not removed from `historical`**, and its whole balance of 70e18 is **re-notified** (L694–L696).
4. At +16d: claimable is 69999999999999854000 each. The total, 139999999999999708000, is twice the 70e18 custody.
5. Alice's `claim()` succeeds. `claim(asdCRV)` and `claimHistorical(asdCRV, [SDT])` both revert (`panic 0x11`).

The atlas predicted this structurally. `atlas/A5` lists `activeRewardTokens` as a *policy leak* (written by the open `syncActiveRewardTokens`), and `atlas/A3` row L694 shows the absolute BDR.

**GW-8 and GW-9. Hold.** For GW-9: 5e8 + 1e8 + 2e8 = 8e8 < 1e9.

**GW-10. Holds** (`m06`). Relaxation: writing `2³⁰ + 7` corrupts the neighbouring field (12344 → 12345).

**GW-11. Holds, quantized.** The K1 re-extension shapes the stream but conserves it.

### Stashes

**ST-1. Holds.** The stash cells are single-pool. The BDRs at L157, L2384, L2419 and L3449 absorb nothing.

**ST-2. FAILS (CONC-13, R2).** PE-c, `h4`. The stash holds 100e18 SDT. Call `processBatch([SDT], [[SDT→WETH]], WETH, [WETH→asset], keeper, 0)`:

- `_transfer` moves 100e18 SDT to the converter.
- `_convert` is called with amount **0**, because the running total `_assets` is passed instead of `_amount` (L2424, L2426). It returns 0.
- The final route is skipped, and `depositReward(0)` is called.

Result: 100e18 SDT is stranded in the converter. With `minAsset = 1` the call reverts `InsufficientHarvestedAssets()`. The control `process(SDT, …)` delivers 100e18. Two further defects are present:

- the intermediate-token test is inverted (L2423);
- an asset entry overwrites `_assets` (L2419).

**ST-3. Holds** (`CallerNotHarvester()`).

### Convex vaults

**CV-1 and CV-2. Hold** (floors at L11029, L11410, L11538, L11386; `_updateRewards` at L11100, L11139).

**CV-3 and AV-1. FAIL (CONC-09).** PE-c, `h2.cross-pool`.

| | `pendingReward(0, alice)` | `pendingReward(1, bob)` |
|---|---|---|
| No push | 50e18 | 50e18 |
| Mallory first calls `crvRewards_1.getReward(vault, true)` (R1) | **100e18** | **0** |

`AladdinCRVConvexVault` behaves the same (`m03`: 100e18 / 0). In addition, its `harvest` sweeps the vault's whole ETH balance (L12283) and whole CRV balance (L12300). See `atlas/A3` rows L11212, L12289, L12300.

**CV-4. FAILS (CONC-02, B1 type aliasing).** PE-c, `h2.alias`.

- With no FXS in the vault, `claim` reverts for every `claimAsToken ∉ {aFXS}`: FXS, real cvxFXS, USDC and ETH.
  - The code redeems aFXS into **real** cvxFXS, then transfers the `cvxFXS` constant, **which is FXS** (L17818, L17830).
- After R1 pushes pool 2's 150e18 FXS into the vault:
  - Alice's claim as FXS pays her **120e18 FXS out of pool 2's rewards**.
  - The vault is left with 30e18 FXS and **120e18 stranded real cvxFXS**.
  - A later `harvest(2)` gives Carol 25e18 aFXS instead of 125e18.
- Dead code in `_zapAsRewardToken`: the cvxFXS branch and the `aFXS.deposit` path (L17850–L17851, L17862–L17866). In the trace, 10e18 FXS is pulled and 0 real cvxFXS.

**CV-5. FAILS (CONC-03).** PE-c.

- With no ETH in the vault, the claim reverts ("transfer ETH failed").
- With 200 ETH in the vault, the claim returns 120000000000000000, but sends **100e18 wei** (the `_amount` in aFXS units) to **`msg.sender`** and 0 to the recipient.

Compare `AladdinCRVConvexVault`, which is correct (L12201–L12206, L10638–L10643).

**CV-6. FAILS at R4 (CONC-15).** P → 0 at +1d; Alice exits at +2d with 0 rewards. P restored at +10d; Carol receives 699999999999999753600. With a settle first: 49999999999999982400 / 649999999999999771200.

**CV-7. Holds.** Observation O-1: a pool with no shares skips its stream, because L11407 still advances `lastUpdate`. In the trace, 200e18 of 700e18 was orphaned.

**AV-3. FAILS at R4 (CONC-17).** `migrate` checks neither the pause flag nor the fee.

### `AladdinCRV`

**AR-1. FAILS (CONC-10, R1 on an empty vault).** PE in a model only (`m05`).

1. Mallory deposits 1 wei and receives 1 share.
2. Mallory calls `stakeFor(aCRV, 1000e18)` on Convex, a donation into the V-read at L10399.
3. The victim deposits 999e18 and receives **0 shares**.
4. Mallory's last-share exit returns 1999000000000000000001.

With a 1500e18 victim deposit, the victim loses 249999999999999999999.

### Atomicity

**AT-1. Holds.** Every Y^U yield is either the last step under the lock (L10642, L12205, L17827, L17830, and the K3 claim after zeroing), or sits where only `_updateRewards` has run (`zapAndDeposit`). In the latter case the LP balance base at L12062 is read after the user token call.

### Exit-liveness summary

| Exit | Status |
|---|---|
| Wrapper principal | live |
| Wrapper claims in the CONC-14 state | dead |
| `SdCrvCompounder.withdraw(max)` with fee > 0 | dead |
| Deposits in the CONC-06 state | locked forever |
| FXS-vault claims other than aFXS | dead (CONC-02) |
| FXS-vault ETH claim | wrong recipient and amount (CONC-03) |

---

## 8. Refinement gaps (observable traces)

| ID | Observable gap | Direction | Specification source |
|---|---|---|---|
| RG-1 | `previewRedeem(10e18)` = 9.975e18 < `redeem` = 10.5e18 | Impl ⊄ Spec | ERC-4626 "as close to"; L1757–L1760 |
| RG-2 | `withdraw(a)` delivers ≠ a: 10.526e18 for a = 10e18 (fee 5%); 1 for a = 2 (fee 0) | Impl ⊄ Spec | ERC-4626 "exactly assets" |
| RG-3 | `mint(1)` mints 0 shares | Impl ⊄ Spec | ERC-4626 "exactly shares" |
| RG-4 | `maxWithdraw` = 2²⁵⁶−1, while `withdraw(max)` reverts | Impl ⊄ Spec | ERC-4626 "MUST NOT be higher" |
| RG-5 | `previewDeposit` = 0 while `deposit` mints the full amount (TS = 0) | Impl ⊄ Spec | ERC-4626 |
| RG-6 | `previewRedeem` > `redeem` after P → 0 | Impl ⊄ Spec | ERC-4626 "no more than" |
| RG-7 | With P = 0 mid-stream, the remaining stream is never distributed | Spec ⊄ Impl (liveness) | L2824, L10912 |
| RG-8 | `SdCrvCompounder` keeps no withdraw fee for remaining holders | Impl ⊄ Spec | L2932–L2933, L2978–L2981 |
| RG-9 | `previewWithdraw` < shares burned under a per-user fee above the default (PD) | Impl ⊄ Spec | ERC-4626 "no fewer than" |
| RG-10 | The ETH claim pays the wrong address and amount | Impl ⊄ Spec | L11557–L11562, L12773–L12784 |
| RG-11 | Claims in tokens revert when the vault holds no FXS | Spec ⊄ Impl | as RG-10 |
| RG-12 | `processBatch` delivers 0 or reverts | Spec ⊄ Impl | L2394–L2404 |
| RG-13 | An unprivileged account re-activates an unregistered token | Impl ⊄ Spec | L3675 `onlyRole`; L3484–L3487 |
| RG-14 | `migrate` exits a paused pool without paying the fee | Impl ⊄ Spec | L12446–L12453, L12523–L12526 |
| RG-15 | Documentation: the `_miscData` "MSB" comment (L1013–L1023) disagrees with offset 0 (L988); `MAX_HARVESTER_RATIO = 1e8 // 20%` is 10% (L982) | — | NatSpec |

---

## 9. Findings table

Confidence values:

- **PE-c**: Proven-executed on bundle bytecode, re-executed by the coordinator.
- **PE-m**: executed Python model only.
- **PD**: Proven-derived.
- **PL**: Plausible.

| ID | Bridge | Invariant violated | Rank | Trace | Required assumption [tag] → relaxation | Gap | Conf. | Lines |
|---|---|---|---|---|---|---|---|---|
| CONC-01 | B2 / K1-Pre1, B3 | GW-5 | R0 (R1 picks timing) | §7 GW-5 | a checkpoint before every bribe notify [L] → quiet period ≥ P | Σ claims < Σ notified; orphaned custody | PE-c | L3869–L3891, L350–L379 |
| CONC-02 | B1 type aliasing | CV-4 | R0 (revert) / R1 (cross-pool payout) | §7 CV-4 | FXS ≠ cvxFXS [violated by constants] | RG-11; cross-pool payout | PE-c | L17756, L17760, L17815–L17830, L17848–L17866 |
| CONC-03 | Exit / spec | CV-5 | R0 | §7 CV-5 | — | RG-10 | PE-c | L17825–L17828 |
| CONC-04 | Refinement / exit | AC-5, AC-6, AC-9 | R0 | §7 AC-4/5 | withdraw fee = 0 [L] | RG-1, RG-2, RG-4, RG-8 | PE-c | L1546–L1568, L2905–L2994 |
| CONC-05 | Refinement | AC-5 | R0 | §7 | — | RG-2, RG-3, RG-4 (polarity ≤ 0) | PE-c | L2895–L2960 |
| CONC-06 | B1 / ℒ (pole) | AC-2 | R0 (with P = 0) | §7 AC-2 | A-P [L] | deposits locked | PE-c | L3120–L3121, L1533–L1534 |
| CONC-07 | B2 / O3c | GW-3 | R0 (deployment) | derived | A-LEGACY [L] | K3 guarantee | PL | L3849–L3852, L2294 |
| CONC-08 | B3 / CII + B1 (pole) | AC-3, AC-7, AC-12 | R1 | §7 AC-3 | no empty interval [L] | RG-5; zero-share mint | PE-c | L3092–L3112, L1527–L1538 |
| CONC-09 | B1 cross-pool absorption | CV-3, AV-1 | R1 push + honest harvest | §7 CV-3 | A-CVX-PERM relaxed | per-pool accounting | PE-c (vault); trigger PL | L11206–L11215, L12279–L12300 |
| CONC-10 | B1 (V-read) + pole | AR-1 | R1 (empty vault) | §7 AR-1 | A-CVX-STAKEFOR relaxed | L10779–L10783 | PE-m | L10397–L10400, L10577–L10596 |
| CONC-11 | MEV | harvest output ≈ market value | R1 when harvester = 0 | derived | A-HARV [L] | — | PL | L862–L866, L1438, L1444, L10656–L10660, L12293, L12298, L17854 |
| CONC-12 | 𝒫 leak | only the owner sets the stash and receiver | R1 (deployment window) | `harness/scripts/concentrator/initv2_race.js` | A-INIT [L] | RG (spec: `updateStash` is owner-only) | **PE-c** (coordinator) | L1318–L1327, L1561–L1569 |
| CONC-13 | B1 | ST-2 | R2 | §7 ST-2 | — | RG-12 | PE-c | L2405–L2436, L156–L161 |
| CONC-14 | B1 + 𝒫 leak | GW-6, GW-7 | R3 + R1 | §7 GW-6 | no unregister of a gauge-listed token that backs claims | RG-13 | PE-c | L685–L700, L3703–L3718, L3681 |
| CONC-15 | B4 | AC-8, CV-6 | R4 | §7 AC-8 | owner settles first [L] | RG-6, RG-7 | PE-c | L3049–L3053, L3092, L11330–L11336, L11399 |
| CONC-16 | B1 configuration | CV-3, CV-7 | R4 | `h2.duplicate` | reward list has no duplicates and excludes the reward token [L] | — | PE-c / PD | L11209–L11215, L11341–L11346 |
| CONC-17 | 𝒫 / exit | AV-3 | R4 enables, R1 executes | derived | migrator unset while pauses are in force [L] | RG-14 | PD | L12138–L12172 |
| CONC-18 | B1 | GW-6 | Rv | derived | A-LOCK | — | PL | L3870–L3891 |
| CONC-19 | B1 / O3d | GW-4 | Rv | derived | A-SDVE [C] | — | PL | L3940–L3951, L3844 |

### Refuted or re-scoped seed hypotheses (proofs of absence)

| Seed | Outcome |
|---|---|
| S1 | A double count requires a duplicated list entry (R4). The dead branches, the `_claim` aliasing and the ETH branch are confirmed. |
| S2 | Confirmed. The ERC-4626 inequality holds; closeness does not. |
| S3 | Confirmed. The capture is documented in comments; the zero-share mints are not. |
| S4 | Confirmed at R4. Retroactive crediting unless the period is never restored. Non-zero → non-zero changes are prospective. |
| S5 | O3a/O3b discharged by lock coverage; O3c conditional (CONC-07); O3d syntactically violated but harmless; stash BDRs are single-pool. |
| S6 | Per-pool B2 is exact; the B5 gluing (aFXS / aCRV) holds; a new B1 issue was found (CONC-09). |

### Kernel discharge

| Kernel | Status in this subsystem |
|---|---|
| K1-Pre1 | Fails only at L3891 |
| K2 | `syncActiveRewardTokens` is a second, unprivileged registration path (CONC-14). O2a is not applicable (P = 7d). |
| K3 | O3a and O3b discharged; O3c conditional; O3d harmless |
| K5, K6 | Discharged |

---

## 10. Bridge matrix

| Contract | B1 | B2 | B3 | B4 | B5 | Atomicity | Exit-liveness |
|---|---|---|---|---|---|---|---|
| Gauge wrapper (+K1/K2/K3) | ✗ CONC-14; Rv CONC-18/19 | ✗ CONC-01; O3c CONC-07 | ✗ CONC-01 (β2) | ✓ | ✓ | ✓ | claims ✗ in the CONC-14 state |
| StakeDAOGaugeWrapperStash | ✓ | n.a. | n.a. | n.a. | n.a. | ✓ | n.a. |
| ConcentratorCompounderStash | ✗ CONC-13 | n.a. | n.a. | n.a. | n.a. | ✓ | n.a. |
| AladdinCompounder ∘ SdCrvCompounder | ✗ CONC-06/08 | ✓ | ✗ CONC-08 | ✗ CONC-15 (R4) | ✓ (surplus) | ✓ | ✗ CONC-04/06; CONC-12 |
| AladdinCRV | ✗ CONC-10 | n.a. | ✓ | ✓ | n.a. | ✓ | ✓ (depends on A-ZAP) |
| ConcentratorConvexVault + AladdinFXSConvexVault | ✗ CONC-09, CONC-02 | ✓ | ✓ (O-1) | ✗ CONC-15 (R4) | ✓ | ✓ | claims ✗ CONC-02/03 |
| AladdinCRVConvexVault | ✗ CONC-09 | ✓ | n.a. | ✓ | ✓ | ✓ | ✓; CONC-17 |

### Observations (not findings)

- **O-1.** A vault pool's stream is orphaned while the pool has no shares.
- **O-2.** Wrapper rewards for the compounder arrive by two R1-selectable routes with different fees: `harvest` (L1458–L1477), or a third-party `claim` → stash → `depositReward`. No user loses.
- **O-3.** `harvest` on an empty vault or pool divides by zero (L1465, L11538, L12322). Only harvest liveness is affected.

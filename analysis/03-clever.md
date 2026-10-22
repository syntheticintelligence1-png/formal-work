# 03 — CLever subsystem: SBD analysis

**Scope.**

| Contract | Line |
|---|---|
| `Furnace` | L4272 |
| `MetaFurnace` | L4890 |
| `RewardClaimable` | L6869 |
| `CLeverAMOBase` | L8304 |
| `AladdinCVX` | L8848 |
| `AMOMath` | L9982 |
| `CLeverCVXLocker` | L12944 |
| `ConcentratorBase` (as used by the AMO) | L808 |

All files are `^0.7.6` (L4276, L4894, L6873, L8308, L8852, L9986, L12948, L812). That has two consequences:

- Plain arithmetic **wraps**. SafeMath applies only where `.add/.sub/.mul` is written.
- `CLeverAMOBase`, `AladdinCVX` and `AMOMath` import no SafeMath at all.

No in-scope contract has a reentrancy guard.

Terminology follows `00-sbd-framework.md`.

**Provenance.**

- The CLever analysis agent produced the primary analysis.
- The coordinator re-executed all four bytecode traces (`harness/scripts/clever/h1_furnace.js`, `h3_metafurnace.js`, `h4_amo_paidoff.js`, `h5_amo_furnace_freeze.js`). Outputs are identical to the agent's recordings, apart from absolute timestamps.
- The coordinator re-derived the CL-06 mechanism from source (§7, I-F10).
- Exact-integer Python models are in `harness/models/clever/`:
  - experiments `t01`–`t17`;
  - shared modules `solsem.py`, `furnace_model.py`, `locker_model.py`, `amo_model.py`, `amo_port.py`;
  - recorded outputs `out_*.txt`.
- Mocks are in `harness/contracts/harness/clever/`. `MockToken` was renamed to `CleverMockToken` to avoid an artifact-name clash.

---

## 1. Abstraction statement

**Modelled exactly**, with integer semantics:

- Furnace and MetaFurnace ledger, index and tempo (L4432–L4885, L5046–L5499);
- locker ledger and schedule (L13283–L13703, L13917–L14130);
- AMOMath (L10005–L10169) and `_searchSplit` (L9148–L9182);
- AMO `unlock`, `withdraw`, `_checkpoint` and `_convertFromBaseToken`.

**Environment**, as contracts in §5:

- CvxLockerV2 and cvxRewardPool;
- zap;
- a Curve plain 2-pool, using the Vyper-semantics reference `CurvePlain2`, which agrees with AMOMath to within 1 wei (T11a);
- yield and AMO strategies;
- bribe distributors;
- clevCVX.

**Omitted:** zap internals, Merkle validation, EIP-1271 semantics, the voting surrogate, MetaCLever (not in the bundle).

**Time:** monotone, with 12 s slots (A-G1). Today, 2026-10-22, is Convex epoch 2964.

**New terms:**

- `TU` = `totalUnrealised` and `TR` = `totalRealised` (Furnace).
- `acc` = `accUnrealisedFraction`, a 2¹²⁸ fixed-point product. The **code 0 means 1.0** (L4329–L4331).
- `TLG`, `TPUG`, `TUG`, `TDG` are the locker's global locked, pending-unlock, unlocked and debt totals.

---

## 2. State space

`atlas/A5` gives the mechanical 𝒫 / dynamic partition.

### Furnace

| Variable | Type / domain / init | Stratum | Line |
|---|---|---|---|
| `governor`, `isWhitelisted`, `stakePercentage` ≤ 1e9, `stakeThreshold`, `zap`, `platformFeePercentage` ≤ 5e8, `harvestBountyPercentage` ≤ 1e8, `platform` | | 𝒫 | L4344–L4373, L4609 |
| `rewardInfo.periodLength` P | uint32, governor-set | 𝒫 | L4381, L4663 |
| `clevCVX` | | 𝒫₀ | L4346 |
| TU, TR | uint128, 0 | ℒ | L4348, L4350 |
| `userInfo[u]` = (U_u, R_u) | uint128 | ℒ | L4334–L4336 |
| acc | uint128; 0 ≡ 1.0 | ℐ | L4329–L4331, L4352 |
| `distributeIndex` idx, `lastPaidOffDistributeIndex` lpo | uint64 | ℐ | L4354, L4356 |
| per-user p_u (uint192 holding a uint128), i_u (uint64) | | ℐ | L4338–L4340 |
| `ratePerSecond`, `lastUpdate`, `finishAt` | uint128 / uint48 / uint48 | 𝒯 | L4378–L4385 |
| CVX balance; cvxRewardPool stake; clevCVX balance; cvxCRV (transient) | | 𝒞 | L4311, L4544–L4549 |

Derived quantities:

- leftover = `(finishAt − now)·rate` (L4455–L4458);
- free CVX = `bal + staked − leftover − TR` (L4734).

### MetaFurnace

The structure is the same as Furnace, with these differences:

- The global ledger is `furnaceInfo` (L4956–L4967). `baseToken` and `debtToken` are 𝒫₀; base decimals ≤ 18 (L5037).
- `feeInfo` (L4970–L4977) is 𝒫.
- `yieldInfo` = {strategy, **percentage: uint16**, threshold: uint80} (L4980–L4987) is 𝒫.
- **The rate is stored in debt units** (L5412, L5420).
- 𝒞 = base balance + strategy underlying (L5083) + debt balance.

### RewardClaimable / AladdinCVX

- `rewards[]` is 𝒫₀ (L6897).
- `rewardPerShare` and per-account `rewardPerSharePaid` are ℐ (L6890, L6900).
- Per-account `pending` and ERC20 shares are ℒ (L6889, L9140).

### CLeverAMOBase / AladdinCVX

| Variable | Stratum | Line |
|---|---|---|
| base, debt, pool, LP, furnace (immutable); `baseIndex`, `debtIndex`, `initialRatio` | 𝒫₀ | L8367–L8379, L8875–L8878, L8405 |
| `config` (defaults commented out at L8468), `lockPeriod` = 1 day, `bountyPercentage`, `minimumDeposit` = 1e18, `platform`, `platformPercentage`, `zap`, `strategy`, `harvester` (0 ⇒ anyone, L8865) | 𝒫 | L8408–L8411, L8881–L8884 |
| `pendingBaseToken`, `locks[u][k].balance`, totalSupply, balances | ℒ | L8418, L8424 |
| `locks[u][k].unlockAt` | 𝒯 | — |
| `nextIndex` | ℐ | L8427 |
| base balance; `Furnace.getUserInfo(AMO)`; `strategyBalance()` | 𝒞 | L9020, L9026 |

### CLeverCVXLocker

| Variable | Stratum | Line |
|---|---|---|
| `clevCVX`, `furnace` (no setters; the initializer is commented out at L13120–L13147); drift constants and patch epochs | 𝒫₀ | L13011–L13015, L13714–L13761 |
| TLG, TPUG, TUG, TDG; per-user `totalDebt`, `rewards`, `totalLocked`, `totalUnlocked`, `epochLocked[17]`, `pendingUnlockList`; `pendingUnlocked[epoch]` | ℒ | L13024–L13076 |
| `accRewardPerShare`; per-user `rewardPerSharePaid`, `nextUnlockIndex`; `universalRewardsDistributorClaimed` | ℐ | L13072, L13112 |
| stake percentage and threshold; `reserveRate` ≤ 1e9; manual-swap list (CVX excluded, L13817); `zap`; fees; `platform`; keepers; `rewardTokens`; `verifier`; `approvedTargets` | 𝒫 | — |
| CVX balance; cvxRewardPool stake; CvxLockerV2 locks by expiry; reward, WETH and ETH balances | 𝒞 | — |

---

## 3. Action footprints (summary)

Mechanized footprints are in `atlas/A1`–`A4`. The atlas census shows:

- Furnace: 7 open actions, 9 clock-sampling actions.
- MetaFurnace: 7 open actions; `harvest` is **open**.
- CLeverCVXLocker: 8 open actions, 0 locks.
- AladdinCVX: 13 open actions + 1 `cond[harvester]`, 0 locks.

### Furnace internal operators

**U_Δ** (`_updatePendingDistribution`, L4672–L4687):

```
Δ := min(finishAt, now) − lastUpdate
if P > 0 ∧ Δ > 0:  lastUpdate := now;  reduce(Δ·rate)
```

The rate is **not** checked to be > 0.

**reduce(a)** (`_reduceGlobalDebt`, L4836–L4857). Always `idx++`. Then:

- if `a ≥ TU`: `TR += TU`, `TU := 0`, `acc := 0`, `lpo := idx`;
- else: `TU −= a`, `TR += a`, `acc := mul128(acc, toU128((TU − a)·2¹²⁸/TU))`.

**distribute** (L4798–L4816):

```
U_Δ
if P = 0:  reduce(a)
else:      rate := (a + leftover)/P   (rate := a/P when now ≥ finishAt)
           lastUpdate := now;  finishAt := now + P
```

### Actions

**Furnace**

- `deposit` / `depositFor` (L4471 / L4483): U_Δ → checkpoint → split `a` into a realised part `nr = min(free, a)` and an unrealised part `nu = a − nr`. Yield points: Y⁰ only.
- `withdraw` / `withdrawAll` (L4495 / L4504): **`TU := (TU − a) mod 2¹²⁸`** (L4766, unchecked, with the comment "never overflow here").
- `claim` (L4512): `TR.sub(R)` (L4778).
- `distribute` (L4530): whitelisted, requires `a > 0`.
- `harvest` (L4542): whitelisted; full-balance cvxCRV BDR (L4547); Y^𝒫 zap.
- `updatePendingDistribution` (L4578): permissionless poke.
- `updatePeriodLength` (L4663): governor; **does not settle first**.

**MetaFurnace**

- `totalBaseTokenInPool` = **`bal.sub(leftover_debt)`** + strategy (L5079–L5083). It is read by `deposit` (L5334) and `_distribute` (L5436).
- `distribute` (L5130): whitelisted, **no transfer, no `a > 0` check**.
- `harvest` (L5144): **permissionless**, Y^𝒫 `strategy.harvest`.
- `fixStatus` (L5261): the owner writes the user index `p_u`.

**AMO**

- `deposit` (L8519): requires `a ≥ minimumDeposit`.
- `unlock(min)` (L8540): `_checkpoint(unlocked)` (Furnace claim, Curve `add_liquidity`/`exchange` with **min 0**, Furnace deposit, LP to strategy), then shares = `min(d·S/(D−d), l·S/(L−l))` computed **unchecked** (L8575–L8576).
- `withdraw` (L8590) and `withdrawToBase` (L8619).
- `checkpoint` (L8679): **permissionless**.
- `donate` (L8684): permissionless, **no minimum**.
- `rebalance` (L8920): owner; checks the LP ratio before and the pool ratio after.
- `migrateStrategy` (L8990): sets the new strategy before calling the old one.

**Locker**

- `deposit` (L13283): `_updateReward` before the lock write.
- `unlock` (L13312): health check, then allocation over epochs e+1…e+17.
- `withdrawUnlocked` (L13373): **`TUG.sub`** (L13386).
- `repay` (L13401), `borrow` (L13435).
- **`donate`** (L13471): **permissionless**, calls `_distribute` → `Furnace.distribute(locker, a)` (L14076).
- `harvest` (L13482): permissionless; D-window BDR (L13486–L13497); zap with min 0.
- Bribe harvests (L13543 / L13580 / L13626): keeper only. Amounts are taken from keeper parameters (L14036–L14039); the approved target is called with an arbitrary spender.
- `processUnlockableCVX` (L13665): keeper only.
  - Runs `_fixLockDrift` (L13671).
  - Computes extra = `totalCVXInPool().sub(TUG)`, a BDR at L13674.
  - Calls `processExpiredLocks`.
  - Requires unlocked ≥ pending (L13686).
  - Relocks.

---

## 4. Specification (invariants as predicates)

### Furnace / MetaFurnace

| ID | Predicate | Source |
|---|---|---|
| I-F1 | `clevCVX.bal(F) ≥ TU + TR` | implicit; L4475, L4766–L4768, L4778–L4788 |
| I-F2 | `totalCVXInPool() ≥ TR` | required by L4734 |
| I-F3 | `Σ_u (U_u + R_u) = TU + TR` | L4699–L4719 |
| I-F4 (B2) | `α_u = getUserInfo(u)` (L4432) refines `M^E` with \|δ\| ≤ 1 wei per checkpoint and polarity π^R ≤ 0 | NatSpec L4313–L4325; "round up" at L4706 |
| **I-F5** | every `_withdraw(a)` has `a ≤ TU` | "never overflow here", L4766 / L5366 |
| I-F6 | `Σ_u α^R_u ≤ TR` | L4777 |
| I-F7 | `acc = 0` ⇒ no reduction since the last pay-off | L4329–L4331 |
| I-F8 | flow property `U_{s+t} = U_t ∘ U_s` | B3 |
| I-F9 | CII under permissionless poke, `distribute(ε)` and harvest timing | B3 |
| **I-F10** | `withdraw`, `claim` and `exit` are executable whenever `α_u ≠ 0` | IFurnace L5596–L5611 |
| I-F11 | `updatePeriodLength` is prospective | NatSpec L4660 / L5251 |
| I-MF12 | `totalBaseTokenInPool` is in base units and does not revert whenever `bal + strategy ≥ leftover` | L5069 |
| I-MF13 | the percentage can be set to any value ≤ 1e5 | L4983, L5196, L5199 |
| I-MF14 | every distributed amount was transferred in beforehand | L5552–L5554 [C] |

### AMO

| ID | Predicate | Source |
|---|---|---|
| I-A1 (B5) | `_depositDebtToken(d)` increases `getUserInfo(AMO).unrealised` by exactly `d` | implicit in L8571–L8576 |
| I-A2 | `unlock` mints `min(d/D_pre, l/L_pre)·S`, and the shares are > 0 for a deposit ≥ `minimumDeposit` | L6753–L6756 |
| I-A3 | `withdraw` and `withdrawToBase` are executable | L6758–L6783 |
| I-A4 | `minLPRatio ≤ ratio() ≤ maxLPRatio` | L8337–L8340, L8387–L8390 |
| I-A5 | after `rebalance`, the pool ratio is within its target | L8972–L8973 |
| I-A6 | conversions are slippage-bounded | implicit |
| I-A7 | O3a–O3d hold for `RewardClaimable` | framework |
| I-A8 | `base.bal ≥ Σ locks + pending` | implicit |

### Locker

| ID | Predicate | Source |
|---|---|---|
| I-L1 | `TLG + TPUG ≤` Convex-locked CVX | L13059 |
| **I-L2** | `TUG ≤ bal + staked` | L13060 |
| **I-L3** | `Σ_u` matured unlocks `≤ TUG` | required by L13386 |
| I-L4 | `Σ totalLocked = TLG`; `Σ_r epochLocked_u[r] = totalLocked_u` | implicit |
| I-L5 | `Σ debt = TDG` | L13061 |
| I-L6 | each epoch with pending > 0 is processed exactly once | L13660–L13664 |
| I-L7 | the Convex release at epoch e is ≥ `pendingUnlocked[e]` | comment at L13686 |
| I-L8 | the health condition holds after `unlock` and `borrow` | L14111–L14130 |
| I-L9 (B2) | each user's credits ≤ that user's eager credits, and Σ credits ≤ Σ distributed | framework |
| I-L10 | CII with respect to harvest timing | framework |
| I-L11 | `harvest` counts exactly its own rewards | L13486–L13497 |
| I-L12 | the bribe `_amountCVX` equals the CVX actually received | L14036–L14037 |

---

## 5. Assumption ledger

| ID | Assumption | Tag | Relaxation → finding |
|---|---|---|---|
| A-F1 | Furnace P > 0 | [L] | P = 0 → CL-10 instead of CL-06/CL-09 |
| A-F2 | the locker is whitelisted in the Furnace (L4530, L14076) | [E by necessity] | otherwise every locker harvest reverts |
| A-F3 | the zap returns the amount actually delivered (L4550, L13500) | [C] | over-reporting → fees paid from realised backing (R4/Rv) |
| A-F4 | cvxRewardPool stake and withdraw are 1:1 | [L] | — |
| A-F6 | `acc ≫ U·m` between pay-offs | [L] | dust-level I-F6 failure |
| **A-F7** | every distribution has `amount + leftover ≥ P` wei | [L] | **CL-06** |
| A-M1 | `MetaFurnace.distribute` is pre-funded with `a > 0` (L5552–L5554) | [C] | CL-20 |
| A-M2 | `strategy.harvest` transfers the amount it reports | [L] | — |
| A-M3 | base decimals = 18, or P = 0 | [L] | CL-03 |
| A-A1 | the Furnace is never fully paid off while AMO shares exist | [L] | CL-02 |
| A-A2 | the Curve pool matches the reference; `assert D1 > D0`; `exchange(0)` reverts or returns 0 | [L] | CL-14 |
| A-A3 | the strategy deposit is > 0 (L8259); `strategyBalance` is 1:1 LP | [C] | — |
| A-A4 | `rewards[]` contains none of base, debt or LP | [L] | aliasing absorption of locked base |
| A-A5 / A-HARV | `harvester ≠ 0` | [L] | rank of harvest-dependent items drops to R1 |
| A-A6 | accrued base per checkpoint ≪ pool depth | [L] | CL-11 |
| A-L1 | the keeper processes every epoch (L13660) | [C] | CL-17 |
| A-L2 | a CvxLockerV2 lock at epoch e expires at e+17; `processExpiredLocks` reverts when nothing has expired | [C] | — |
| A-L3 | CvxLockerV2 / cvxRewardPool `getReward(account, …, stake)` are permissionless | [L] | CL-08 |
| A-L4 | third parties may claim bribes on the locker's behalf (L13560, L13605, L14164) | [C] | CL-07 |
| A-L5 | the keeper supplies honest amounts, calldata and spender | [L] | CL-19 |
| A-L6 | zap min-out is 0 (L13500, L13504) | [C] | CL-15 |
| A-L7 | `reserveRate` is never lowered | [L] | CL-23 |
| A-L8 | patch preconditions: CVX balance ≥ 3173e18 at epoch 2958; TUG ≥ each subtraction; each patch epoch processed exactly once | [L] | CL-18 |
| A-T1 | CVX, clevCVX, LP and base are hook-free ERC20s | [L] | R1 reentrancy (no guards exist) |
| A-G1 | 12 s slots; R1 can land a transaction in a chosen block | [L] | — |

---

## 6. Abstract transition system

```
S   = S_F × S_MF × S_AMO × S_L × Env
S_F = (TU, TR, acc, idx, lpo, {U, R, p, i}_u, rate, P, lastUpdate, finishAt; bal_CVX, staked, bal_clev)
S_MF  analogous, plus strategy underlying and scale
S_AMO = (S, {shares}, {locks}, pending, rps, {pending, paid}_u, F.userInfo[AMO], strategy LP, bal_base)
S_L   = (TLG, TPUG, TUG, TDG, acc, per-user tuple, pendingUnlocked[·], bal_CVX, staked, ConvexLocks: epoch ↦ amount)
Env   = (now, Curve(b0, b1, supply, A, fee), venue states, external balances)
S0  = all ledgers 0, acc = 0 (≡ 1.0), venues empty, P configured
Act = R1  every permissionless entry point; Curve swaps; ERC20 transfers; third-party Convex getReward/kick;
          distributor claims made on the locker's behalf
      R2  processUnlockableCVX; bribe harvests; whitelisted Furnace distribute/harvest
      R3  MetaFurnace.distribute
      R4  setters
      Env tick(Δt); epoch release; strategy yield; Rv deviations
→   = the footprint relations of §3, applied atomically; revert = identity
```

The Curve pool is abstracted as `CurvePlain2`, which agrees with AMOMath to within 1 wei.

---

## 7. Counterexample search per invariant

Confidence:

- **[bc-c]**: bundle bytecode, re-executed by the coordinator.
- **[py]**: exact-integer model.

**I-F1. Holds.** Conservation is exact in every action. A wrap of TU (CL-01) affects the ledger only.

**I-F2. Holds for a fixed P.** distribute adds `P·⌊(a + lo)/P⌋ ≤ a + lo`; U_Δ moves `min(rate·Δ, TU)`; claims reduce TR and balance equally. Relaxation: R4 toggling P (CL-21).

**I-F3. Holds** modulo 2¹²⁸ after a wrap.

**I-F4. Quantized in the sane regime, structural at the boundaries** [py T04].

- Sane regime: δ^U per reduction ∈ [−2, +1) wei, with mostly positive sign (599 positive vs 116 negative for `distribute`, 337 vs 35 for a poke). Deposit, withdraw and claim have δ ≡ 0.
- Structural failures: in the wrapped regime (up to 7.99e17) and when `acc` underflows (CL-16).

**I-F5. FAILS (CL-01).** [py T02a] shortest trace:

| Step | Action | Resulting state |
|---|---|---|
| 1 | `deposit(8)` | TU = 8 |
| 2 | `distribute(4)` | TU = 4, acc = 2¹²⁷, α = (5, 3) |
| 3 | `withdrawAll` | **TU = 2¹²⁸ − 1** |

The two-user version on bytecode [bc-c H2]:

1. Alice deposits 1e18 and Bob 2e18, then `distribute(1e18)`. The per-user unrealised amounts are 666666666666666667 and 1333333333333333334: **each rounded up** (L4707–L4712). Their sum exceeds TU = 2e18 by 1.
2. Both exit. TU = **340282366920938463463374607431768211455 = 2¹²⁸ − 1**, TR = 1.
3. Carol's `deposit(10e18)` reverts `Furnace: overflow`.
4. After `distribute(1000e18)`, Carol can deposit. A further `distribute(1000e18)` realises **29 wei** for her. The Furnace holds 2000e18 + 1 CVX, of which only 29 wei can be claimed by any user.

The wrap occurred in 200 of 200 random honest traces.

**I-F6. Holds empirically** [py T15]: 0 violations in 33 495 states, under A-F6.

**I-F7. FAILS (CL-16)** [py T03]. Distributions of 2⁶⁵ − 1 and then 2⁶⁵ drive `acc` to 0 **without** bumping `lpo`. User A's α is reset to 2⁶⁵; the stale user V's view and `withdrawAll` revert `Furnace: overflow`.

**I-F8. Holds** [py T05a]. The maximum `D(s, t)` is 0 wei for TU, TR and α over 200 random partitions. The flow property is exact.

**I-F9. FAILS (CL-09, CL-10).**

- [py T05b]: a daily `donate(1)` leaves a realisation shortfall of 33.99% at day 7 and 1.34% at day 28.
- [py T05c]: a late depositor captures 126 263 473 109 261 598 715 wei, against 246 400 wei without the pokes.
- [py T06a] (P = 0): just-in-time capture of 5000e18 out of a 10000e18 harvest.

**I-F10. FAILS (CL-06).** [bc-c H1] trace (Furnace with P = 7 days):

| Step | Action | Result |
|---|---|---|
| 1 | Alice deposits 1000e18, Bob 500e18; keeper `distribute(100e18)` | rate = 165343915343915 |
| 2 | permissionless pokes at +3d and at +8d (the second after `finishAt`) | ok |
| 3 | **attacker calls `CLeverCVXLocker.donate(1)`** (permissionless, L13471 → L14076) | `rate = ⌊1/P⌋ = 0` (L4806); `lastUpdate = now`; `finishAt = now + P`; TU = 1400000000000000208000 |
| 4 | 12 s later: `withdrawAll`, `claim`, `exit`, `deposit`, keeper `distribute(100e18)`, `updatePendingDistribution` | **all revert `Furnace: overflow`** |
| 5 | at +1 year | still reverts |
| 6 | governor `updatePeriodLength(0)`; then `withdrawAll` | ok |
| 7 | re-enable 7 days; then Bob's `exit` | reverts again |

*Mechanism, re-derived by the coordinator:*

- U_Δ calls `reduce(Δ·rate)` whenever Δ > 0 (L4680–L4684), whatever the rate.
- With rate = 0 and TU > 0, `reduce(0)` takes the `else` branch and computes `_toU128((TU − 0)·2¹²⁸/TU) = _toU128(2¹²⁸)`. This fails the `require` at L4861 (L4854).
- `lastUpdate` can never advance, because every update reverts. So `Δ = min(finishAt, now) − lastUpdate > 0` holds forever.

*Coordinator note on rank.* The precondition is `amount + leftover < P` wei at a distribution while TU > 0. `donate(1)` reaches it deterministically (**R1**). An honest dust distribution (`0 < amount < P` after `finishAt`) also reaches it. That is **R0** but non-generic. A same-block distribution with amount ≥ P repairs the state before Δ > 0 accrues.

*Propagation* [bc-c H5]: the AMO's `checkpoint`, `withdraw`, `withdrawToBase` and `harvest` revert `Furnace: overflow`. So do the locker's `harvest`, `donate` and Furnace-side borrows.

**I-F11. FAILS at R4 (CL-21)** [py T06b]:

| | Back-runner realises | Alice credited |
|---|---|---|
| settle first | 600e18 | 100e18 |
| no settlement | 700e18 | 0 |

**I-MF12. FAILS (CL-03, CL-04).**

- [bc-c H3a]: contract balance 241253842592592677515 plus strategy 458745000000000161478 is ≥ the leftover, yet the view reverts because it subtracts **before** it adds (L5079–L5083). `deposit` and `distribute` revert (SafeMath).
- [bc-c H3b/c], base with 6 decimals: the rate is 1157407407407407 in **debt** units, while the base balance is 700000000. The view and deposits revert, and with a strategy set, `distribute` reverts too.

**I-MF13. FAILS (CL-25)** [bc-c H3]. `percentage` is `uint16`, so setting 1e5 fails with an ABI out-of-bounds error.

**I-A1. FAILS (CL-02).** A paid-off Furnace realises new deposits immediately from free CVX (L4738–L4747).

**I-A2. FAILS (CL-02, CL-12).**

- [bc-c H4]: Alice's `unlock(0)` mints **0 shares**. Her 1000e18 CVX is absorbed: debtOut = 2, debtBal = 0, and the unchecked difference at L8575 wraps.
- [py T17]: when the attacker holds the whole supply of 1 share, the victim receives 0 shares and the attacker withdraws 1501.6e18 LP plus 1501.6e18 debt.

**I-A3. FAILS.**

- CL-02 [bc-c H4]: `withdraw`, `withdrawToBase`, `checkpoint` and `rebalance` each hit `invalid opcode` (division by zero at L9067) or `Furnace.withdraw(0)` (L9094 → L4496). The dust variant fails at `curve: assert D1 > D0`.
- CL-06 propagation (H5).
- CL-14 (T11c).

**I-A4. FAILS (CL-05)**, derived. Realisation lowers D while re-conversion targets the current L/D (L9050, L9175). The ratio bounds are checked only as a precondition of `rebalance` (L8931).

**I-A5. Holds [E]** (L8972–L8973).

**I-A6. FAILS (CL-11)** [py T14]. Attacker P&L (CVX) for accrued base B, pool depth 1M/1.2M:

| B \ A | 10 | 50 | 100 | 200 |
|---|---|---|---|---|
| 5 000 | −0.30 | −1.32 | −1.46 | −1.53 |
| 20 000 | **+466.63** | −0.49 | −1.04 | −1.32 |
| 50 000 | +1511.19 | +151.77 | −0.22 | −0.91 |
| 100 000 | +3257.50 | +536.27 | +157.08 | −0.24 |
| 200 000 | +6826.48 | +1325.37 | +556.96 | +165.12 |

**I-A7. Holds.**

- O3a is discharged by `_beforeTokenTransfer`, which checkpoints `from` and `to` (L9010–L9017).
- O3b does not apply (rewards arrive as lump sums).
- O3c is the ERC20 identity.
- O3d holds under A-A4.

**I-A8. Holds.** The claim is a D-read (L9099–L9101).

**I-L2 / I-L3. FAIL (CL-07)** [py T09].

1. Carol has 500e18 unlocked; TUG = 500e18.
2. R1 claims a 200e18 CVX bribe on the locker's behalf. The weekly `processUnlockableCVX` relocks it as "extra" (BDR at L13674).
3. The keeper's `harvestVotiumLikeBribes([CVX, 200e18])` runs with `isClaimed = true`. It trusts the amount parameter (L14036–L14037) and sends 200e18 of **users' unlocked CVX** to the Furnace.
4. Now TUG = 500e18 > CVX = 300e18. Carol's `withdrawUnlocked` reverts, and next week's `processUnlockableCVX` reverts (SafeMath).

**I-L3 / I-L6 / I-L7. FAIL (CL-17)** [py T08].

1. The keeper skips epoch e₀+17.
2. At e₀+18 the Convex lock is relocked to e₀+35. Alice withdraws 100e18, which drains Carol's share; Carol reverts.
3. At e₀+34, `processExpiredLocks` reverts "no exp locks", so Eve reverts too.
4. `pendingUnlocked` {17: 100e18, 34: 100e18} is never consumed. The drift recurs every 17 epochs.

**I-L6. The patch is fragile (CL-18)** [py T16, ledger model built from the comment values]:

| Missed epoch | Effect on TUG − entitlement |
|---|---|
| 2972 | final −99 018.71 CVX: a **109 018.71 CVX shortfall** |
| 2970 | +76 458.07 idle |
| 2971 | +27 616.21 idle |
| 2974 | +90 797.89 idle |
| 2958 (failed) | epochs 2970 and 2971 revert |

The upcoming patch epochs 2970–2975 fall on **2026-12-03 … 2027-01-07**.

**I-L4, I-L5, I-L8. Hold [E].**

**I-L9. Holds.** Polarity π ≤ 0 by flooring (L13925, L14069); the uint192 cast at L13928 is unreachable.

**I-L10. FAILS (CL-13)** [py T10]. A deposit just before the permissionless `harvest` captures 5000e18 out of 10000e18, at the price of a 17-week lock.

**I-L11. FAILS (CL-08), Plausible.** It depends on A-L3: permissionless `getReward(locker, stake)` can strand rewards outside the D-window, or stake them into cvxCRV, which the locker cannot exit.

**I-L12. FAILS** under CL-07 and CL-19.

### Refuted hypotheses (proofs of absence)

- The U_Δ flow property is exact.
- Every TU change is preceded by a poke, so CII holds for deposit and withdraw.
- Claim-side `Σα^R ≤ TR` holds (under A-F6).
- With a fixed P, CVX backing ≥ TR.
- clevCVX custody = TU + TR exactly.
- AMOMath matches the Curve plain pool to within 1 wei, and the split search is monotone.
- The locker's reward accumulator satisfies O3a and O3c with π ≤ 0; its uint192 cast is unreachable.
- The pending-unlock list stays monotone.
- No R1-reachable reentrancy: there are no guards, but no R1-controlled callee runs code.
- The CL-06 freeze is impossible with P = 0, and is repaired by a same-block distribution of at least P.
- The AMO conversion sandwich is unprofitable at small B.

---

## 8. Refinement gaps

| ID | Observable trace | Direction | Specification source |
|---|---|---|---|
| RG1 | after `donate(1)`, every Furnace exit reverts | Spec ⊄ Impl | IFurnace L5596–L5611 |
| RG2 | TU wraps to 2¹²⁸ − 1 on honest full exit | Impl ⊄ Spec | "never overflow here", L4766 / L5366 |
| RG3 | after `acc` underflows, users' realisation is reverted | Impl ⊄ Spec | NatSpec formula L4313–L4325 |
| RG4 | `updatePeriodLength` acts immediately and retroactively | Impl ⊄ Spec | L4660 / L5251 |
| RG5 | base decimals < 18 ⇒ deposits revert | Spec ⊄ Impl | L5037 |
| RG6 | the view reverts although the total funds suffice | Spec ⊄ Impl | L5069 |
| RG7 | a percentage ≤ 1e5 cannot be set | Spec ⊄ Impl | L4983, L5196 |
| RG8 | AMO `withdraw` reverts | Spec ⊄ Impl | ICLeverAMO L6758–L6783 |
| RG9 | `unlock` mints 0 shares | Impl ⊄ Spec | L6664–L6669, L6753 |
| RG10 | `ratio()` leaves the configured range | Impl ⊄ Spec | L8337–L8340 |
| RG11 | TUG > custody | Impl ⊄ Spec | L13060 |
| RG12 | one missed week cannot be recovered without an upgrade | Spec ⊄ Impl | L13660–L13664 |
| RG13 | processing after a third-party bribe claim double-counts | Impl ⊄ Spec | L13560 |

---

## 9. Findings table

| ID | Bridge | Invariant | Rank | Assumption [tag] → relaxation | Gap | Conf. | Key lines |
|---|---|---|---|---|---|---|---|
| CL-01 | B2 + intra-stratum (unchecked) | I-F5 | **R0**; R1 can force it when TU is its own | Σα^U ≤ TU at exits [L] → per-user round-up | RG2 | bc-c (H2), py (T02) | L4707–L4712, L4766, L5366 |
| CL-02 | B5 / exit-liveness | I-A1–I-A3 | R0 given TU = 0 | A-A1 [L] | RG8, RG9 | bc-c (H4), py (T12) | L4734–L4747, L9050, L9067, L9094, L4496, L8575 |
| CL-03 | B1 (units) / exit-liveness | I-MF12 | R0 (configuration) | A-M3 [L] | RG5 | bc-c (H3b/c) | L5075, L5079, L5412, L5420, L5436 |
| CL-04 | B1 / exit-liveness | I-MF12 | R0 | — | RG6 | bc-c (H3a) | L5079–L5083, L5386–L5395 |
| CL-05 | refinement | I-A4 | R0 / R4 | — | RG10 | PD | L8931, L9050, L9175 |
| **CL-06** | B3 / exit-liveness / B5 | I-F10 | **R1** (`donate(1)`); R0 non-generic | A-F7 [L] | RG1 | **bc-c (H1, H5)**, py (T01); mechanism re-derived | L13471, L14076, L4806, L4813–L4814, L4680–L4684, L4854, L4861 |
| CL-07 | B1 aliasing (BDR at L13674) | I-L2, I-L3 | R1 + honest R2 | A-L4 [C] | RG11, RG13 | py (T09) | L13561, L14036–L14037, L13674, L13695–L13701, L13386 |
| CL-08 | B1 / BDR | I-L11 | R1 | A-L3 [L] | — | PL | L13486–L13497, L12937, L4151–L4155 |
| CL-09 | B3 CII (re-extension) | I-F9 | R1 | — | — | py (T05) | L4805–L4814, L13471 |
| CL-10 | B3 CII (P = 0, JIT) | I-F9 | R1 | A-F1 relaxed | — | py (T06a) | L4802–L4803, L13482, L5144 |
| CL-11 | atomicity / B3 (MEV) | I-A6 | R1 | A-A6 [L] | — | py (T14) | L8679, L8772–L8786, L9057–L9064 |
| CL-12 | B1/B2 at the pole | I-A2 | R1 (low reachability) | — | RG9 | py (T17) | L8575–L8579, L8684 |
| CL-13 | B3 CII (JIT) | I-L10 | R1 | — | — | py (T10) | L13300, L13304, L14068–L14070 |
| CL-14 | exit-liveness | I-A3 | R1 | A-A2 [L] | RG8 | py (T11c); bytecode with a Curve mock (H4); PL for real Curve | L8684, L9159–L9181, L9057 |
| CL-15 | atomicity (MEV) | — | R1 | A-L6 [C] | — | PL | L13500–L13507 |
| CL-16 | B2 structural | I-F7, I-F10 | R1 (low) | — | RG3 | py (T03) | L4866–L4870, L4878–L4880, L4707 |
| CL-17 | B3 / B5 | I-L3, I-L6, I-L7 | R2 | A-L1, A-L2 [C] | RG12 | py (T08) | L13683–L13692, L13964, L13386 |
| CL-18 | B3 | I-L6 | R2 | A-L8 [L] | — | py (T16) | L13714–L13761 |
| CL-19 | trust | — | R2 | A-L5 [L] | — | PD | L13543–L14061 |
| CL-20 | trust | I-MF14 | R3 | A-M1 [C] | — | PD | L5130–L5138 |
| CL-21 | B4 | I-F11 | R4 (then an R1 back-run) | — | RG4 | py (T06b) | L4660, L4663, L5251 |
| CL-22 | B4 / ℐ | — | R4 | — | — | PD | L5261 (`fixStatus` writes user index) |
| CL-23 | B4 | I-L8 | R4 | A-L7 [L] | — | PD | L13862 |
| CL-24 | trust | — | R4 | — | — | PD | L13729 (patch sends 3173 CVX to `owner()`) |
| CL-25 | 𝒫 typing | I-MF13 | R4 | — | RG7 | bc-c (H3, ABI error) | L4984, L5198–L5199 |
| CL-26 | trust / atomicity | — | R4 | — | — | PD | L8996 (`migrateStrategy` order); EIP-1271 delegated to `verifier` |

---

## 10. Bridge matrix

| Contract | B1 | B2 | B3 | B4 | B5 | Atomicity | Exit-liveness |
|---|---|---|---|---|---|---|---|
| Furnace | ✓ under fixed P; owner-less TR after CL-01 | ✗ CL-01, CL-16 | flow ✓; CII ✗ CL-09, CL-10 | ✗ CL-21 | ✗ CL-06 propagation, CL-02 | ✓ for R1 | ✗ CL-06, CL-16 |
| MetaFurnace | ✗ CL-03, CL-20 | ✗ CL-01 analogue | ✗ CL-10 analogue (open harvest); CL-06 analogue (R3) | ✗ CL-21, CL-22 | n.a. (caller outside the bundle) | ✓ (strategy is R4) | ✗ CL-03, CL-04 |
| RewardClaimable | ✓ under A-A4 | ✓ | minor | ✓ | ✓ | ✓ | ✓ |
| CLeverAMOBase / AladdinCVX | ✓ | ✗ CL-12 | ✗ CL-11 | ✓ | ✗ CL-02 | ✗ CL-11; CL-26 (R4) | ✗ CL-02, CL-06, CL-14 |
| AMOMath | n.a. | formulas ✓ (T11a) | n.a. | n.a. | n.a. | n.a. | via CL-02, CL-14 |
| CLeverCVXLocker | ✗ CL-07, CL-08 | ✓ (π ≤ 0) | ✗ CL-13, CL-17, CL-18 | ✗ CL-23 | ✗ CL-17 (Convex), CL-06 (Furnace) | R2-only stale caches (L14029, L14054) | ✗ CL-07, CL-17, CL-18, CL-23 |

### Items to verify against deployment

1. Whether CvxLockerV2 `getReward(address, bool)` and cvxRewardPool `getReward(address, bool, bool)` are permissionless and include a stake path (CL-08).
2. The deployed Furnace P (P > 0 ⇒ CL-06 and CL-09; P = 0 ⇒ CL-10), and the harvest cadence relative to P.
3. On-chain execution of patch epochs 2957/2958, and keeper scheduling for epochs 2970–2975 (CL-18).
4. MetaFurnace base-token decimals, P and strategy percentage (CL-03, CL-04).
5. Real Curve behaviour for `assert D1 > D0` and `exchange(0)` (CL-14).
6. Whether the CLever Furnace TU can reach 0 (the CL-02 precondition).

# 01 — Kernel modules: assume-guarantee analysis (K1, K2, K3, K5, K6)

**Scope.** This document covers the shared library layer:

| ID | Module | Lines |
|---|---|---|
| K1 | `LinearReward` | L325–L400 |
| K2 | `LinearMultipleRewardDistributor` | L3566–L3759 |
| K3 | `MultipleRewardAccumulator` | L2048–L2305 |
| K5 | `WordCodec` | L20–L129 |
| K6 | `FeeCustomization` | L3996–L4110 |

K4 (`DecrementalFloatingPoint` + `MultipleRewardCompoundingAccumulator`) is analysed end-to-end with its only instantiations, the f(x) rebalance pools, in `04-fx.md`.

Terminology follows `00-sbd-framework.md`.

**Execution ground truth.** Every counterexample marked *Proven-executed* was run on the bundle's **unmodified** sources:

- Compilers: solc 0.7.6 and 0.8.20, optimizer at 200 runs.
- Libraries: OpenZeppelin 3.4.2 and 4.9.6, mapped to the bundle's `@openzeppelin/contracts{,-upgradeable}{,-v4}` import prefixes.
- Runtime: the Hardhat EVM. The full bundle (106 files, 149 compilation units including OpenZeppelin) compiles without modification.
- Harness: `../harness/contracts/harness/KernelHarness.sol` and scripts under `../harness/scripts/kernel/`. Both are reproduced below.

---

## K1 — `LinearReward`

### State space (one instance per reward token, stored by K2)

| Variable | Type | Domain | Init | Stratum |
|---|---|---|---|---|
| `queued` | uint96 | [0, 2⁹⁶) | 0 | ℒ — notified but not yet scheduled |
| `rate` | uint80 | [0, 2⁸⁰) | 0 | 𝒯 |
| `lastUpdate` | uint40 | timestamps | 0 | 𝒯 |
| `finishAt` | uint40 | timestamps | 0 | 𝒯 |

Every variable is persistent. Note that `increase` and `pending` operate on a memory copy; the caller persists the result.

### Actions

`increase(P, a)` (L350) is a pure state transformer that reads `now = block.timestamp`. Let `A₀ = a + queued`.

| Branch | Guard | Effect |
|---|---|---|
| β1 | `now ≥ finishAt` | `rate' = ⌊A₀/P⌋`, `queued' = A₀ − rate'·P`, `lastUpdate' = now`, `finishAt' = now + P` (L357–L362) |
| β2 | `now < finishAt ∧ 9·rate·(now − (finishAt − P)) ≤ 10·A₀` (L365–L367) | `A = A₀ + rate·(finishAt − lastUpdate)` (L369); then `rate' = ⌊A/P⌋`, `queued' = A − rate'·P`, `lastUpdate' = now`, `finishAt' = now + P` |
| β3 | otherwise | `queued' = A₀` (SafeCast to uint96, L377); everything else unchanged |

Implicit guards:

- SafeCast reverts on `rate ≥ 2⁸⁰` or (in β3) `A₀ ≥ 2⁹⁶`.
- L365 reverts if `finishAt − P > now`. This can only happen if `P` changed between calls.

`pending()` (L385) returns `(rate·e, rate·ℓ)` where:

- if `now > finishAt`: `e = (finishAt − lastUpdate)⁺` and `ℓ = 0`;
- otherwise: `e = now − lastUpdate` and `ℓ = finishAt − now`.

### Precondition (caller obligation)

**Pre1**: `lastUpdate = now` at entry to `increase`, or the caller has already credited `rate·(min(now, finishAt) − lastUpdate)⁺`.

### Invariants

**K1-I1 (mass conservation).** Define the not-yet-credited mass:

```
M(σ) = queued + rate·(finishAt − lastUpdate)⁺
```

Under Pre1, every `increase(P, a)` satisfies `M' = M + a` **exactly**. The rounding remainder is retained in `queued`.

*Proof.* In β1 and β2, `queued' + rate'·P = A` by construction.

- β1: Pre1 gives `lastUpdate = now ≥ finishAt`, so `M = queued` and `M' = A₀ = M + a`.
- β2: Pre1 gives `M = queued + rate·(finishAt − now)`, so `M' = A = M + a`.
- β3: `M' = A₀ + rate·(finishAt − lastUpdate) = M + a`. ∎

*Relaxation (Pre1 dropped, β1).* `M' = A₀`, so the mass `rate·(finishAt − lastUpdate)` is destroyed.

*Proven-executed* (`k1_probe.js`, rows B1):

```
B1 pre : queued=0 rate=1e12 lastUpdate=T finishAt=T+P | pending=(604800000000000000, 0)
         increase(P, 0) at T+P+200
B1 post: queued=0 rate=0 ...                          | pending=(0, 0)    -- 6.048e17 destroyed
```

*Relaxation (Pre1 dropped, β2).* The elapsed, un-credited part is **rolled** into the new period instead of destroyed (rows B2). So the outcome of a precondition violation depends on the branch.

*Discharge.* `LinearReward.increase` has exactly one caller, `K2._notifyReward` (L3733). K2 calls `_distributePendingReward()` (L3659) first, and that sets `lastUpdate = now` for every active token (L3746). Pre1 is therefore discharged **[E]**. `P` is `immutable` (L3582), so the L365 underflow is unreachable **[E]**.

**K1-I2 (eventual release; liveness).** The NatSpec at L342–L344 reads: *"The rewards will be only distributed when current period is end or the current increase or decrease no more than 10%."*

The implementation has **no time-triggered release**. Mass parked in `queued` by β3 is released only by a *later* `increase`.

*Counterexample — Proven-executed* (`k1_probe.js`, rows Q):

| Step | Action | `queued` | Distributable by day 30 |
|---|---|---|---|
| Q0 | `increase(700e18)` at T | 246400 (rounding) | — |
| Q1 | `increase(1e18)` at T+1d (β3, since 1e18 < 0.9·100e18) | 1e18 + 246400 | — |
| Q2 | no further notify, observed at T+30d | 1e18 + 246400 | 699.9999…e18; the 1e18 is never scheduled |

*Refinement gap (Spec ⊄ Impl, liveness).* The specification says queued rewards are distributed "when current period is end". The implementation distributes them only if the distributor notifies again after `finishAt`; `depositReward(token, 0)` suffices. **Required assumption [C]:** the distributor keeps notifying.

**K1-I3 (sampling-schedule invariance, B3).** The composition K2∘K1 is **not** checkpoint-insertion invariant with respect to *notify granularity*. Holding the inflow fixed, the β2 restart (`finishAt' = now + P`) re-spreads the remaining mass each time a notify happens.

*Experiment — Proven-executed* (`k1_schedule_defect.js`, causal pokes). P = 7d. 1400e18 arrives uniformly over days 0–14. The chunk accrued during `(iΔ, (i+1)Δ]` is notified at `(i+1)Δ`. Alice stakes 1e18 at day 0. Bob stakes 1e18 at day 14, after all inflow has arrived. Entitlements are measured at day 28:

| Notify schedule | Notifies | Period restarts | Alice | Bob |
|---|---|---|---|---|
| weekly (2 × 700) | 2 | 2 | 1050.006 | 349.994 |
| daily (14 × 100) | 14 | 14 | 1090.445 | 309.555 |
| 6-hourly (56 × 25) | 56 | 56 | 1095.671 | 304.329 |
| hourly (336) | 336 | 336 | 1097.090 | 302.910 |

*Schedule defect.* With identical inflow, the transfer between the two stakers ranges over **47.08e18**. That is 3.4 % of all rewards, or 13.5 % of Bob's entitlement. More frequent notifies favour stakers who are present early.

The eager reference machine credits each reward at its arrival time. It gives Bob **0**. Every schedule in the table gives Bob at least 302.9e18, because the design smooths by delay.

*Minimal rank.* The rank depends on who can cause a notify:

- **R3** (distributor) at kernel level.
- **R1** in an instantiation whose distributor is reachable from a permissionless action. One such route: `TreasuryV2.harvest()` (L9648, no access modifier) → `_distributedHarvestedRewards` → `_distributeRebalancePoolRewards` → `IFxRebalancePoolSplitter.split` (L9934–L9939). The splitter is outside the bundle, so that the splitter calls `depositReward` on the pools is an assumption **[C]**.
- `MarketWithFundingCost` additionally pokes `treasury.harvest()` on every market action (L17189).

Note that the poker chooses only the *timing*. The amounts are fixed by accrued yield.

**K1-I4 (bounds).**

- `rate < 2⁸⁰`: **[E]**, SafeCast.
- β1/β2 `queued' < P`: **[E]**, by arithmetic.
- β3 `queued < 2⁹⁶`: **[E]**, SafeCast, reverts.
- The `uint40` timestamp casts are unchecked. They overflow around the year 36 800. **[L]**, irrelevant.

---

## K2 — `LinearMultipleRewardDistributor`

### State space

| Variable | Type | Init | Stratum | Line |
|---|---|---|---|---|
| `periodLength` | uint40, immutable, ∈ {0} ∪ [1d, 28d] | ctor | 𝒫₀ | L3582, L3608 |
| `distributors[token]` | address | 0 | 𝒫 | L3589 |
| `rewardData[token]` | K1 state | 0 | ℒ/𝒯 | L3592 |
| `activeRewardTokens` | set | ∅ | 𝒫 | L3595 |
| `historicalRewardTokens` | set | ∅ | 𝒫 | L3598 |
| roles (`REWARD_MANAGER_ROLE`, admin) | AccessControl | ctor/init | 𝒫 | — |

### Actions

| Action | Guard | Effect | Yield points | Lock |
|---|---|---|---|---|
| `depositReward(t, a)` (L3650) | `t ∈ active ∧ sender = distributors[t]` (R3 or delegated) | transfer, then accrue all active tokens, then `increase` | `safeTransferFrom` (Y^𝒫; token chosen by R3) **before** accrual | none |
| `registerRewardToken` (L3675) | `REWARD_MANAGER_ROLE`, `t ∉ active` | `active ∪= {t}`, `historical ∖= {t}`; **`rewardData[t]` not reset** | — | — |
| `updateRewardDistributor` | `REWARD_MANAGER_ROLE`, `t ∈ active` | `distributors[t] := d` | — | — |
| `unregisterRewardToken` (L3703) | `REWARD_MANAGER_ROLE`, `t ∈ active`, `queued' + pending = 0`, where `queued' = 0` if `queued < P` (L3709–L3710) | `active ∖= {t}`, `historical ∪= {t}` | — | — |

### Findings

**K2-I1 (Pre1 discharge).** Holds **[E]**; see K1-I1.

**K2-F1 (O2a: queue trap at `periodLength = 0`). Latent, R0. Proven-executed.**

*Invariant.* `∀t: queued(t) > 0 ⇒ ◇ queued(t) = 0`. In words, every queued reward is eventually scheduled.

*Counterexample* (`k2_periodzero_trap.js`; instantiation constructed with `periodLength = 0`, which L3608 allows):

| Step | Action | Resulting state |
|---|---|---|
| s0 | — | S = 0, queued = 0, I = 0, bal = 0 |
| a1 | `depositReward(R, 100e18)` while S = 0 | queued = 100e18 (L3730 → L2288), bal = 100e18 |
| a2 | `alice.stake(10e18)` | S = 10e18, queued = 100e18 |
| a3 | `depositReward(R, 0)` | unchanged (`_accumulateReward(…, 0)` returns immediately) |
| a4 | `depositReward(R, 1e18)` | I = 1e17, claimable(alice) = 1e18, **queued = 100e18** |
| a5 | `alice.claim()` at +365d | bal = 100e18, claimable = 0, **queued = 100e18** |
| a6 | `unregisterRewardToken(R)` | **REVERT** `RewardDistributionNotFinished()` |

*Cause.* With `periodLength = 0`, the only reader of `queued` (`LinearReward.increase`) is never invoked (L3728–L3730). The unregister guard `queued < periodLength` (L3709) can never hold when `periodLength = 0`.

*Required assumption.* `periodLength > 0`, or total share > 0 at every deposit. Status **[L]**: all three in-bundle instantiations pass 7 days (L3827, L14972, L16058). No code prevents a future instantiation with 0.

*Refinement gap (Impl ⊄ Spec, conservation).* 100e18 is held in custody (𝒞) but is backed by no claim (ℒ).

**K2-F2 (fee-on-transfer relaxation). Rv/R3. Proven-derived.**

*Assumption.* The reward token transfers exactly `a` (`@dev Make sure no fee on transfer token is added as reward token`, L3671). Status **[C]**.

*Relaxation.* A token that delivers `a − f`. K2 still notifies `a` (L3661). Then `Σ claimable` exceeds custody by `f` per deposit, and the last claimant's `safeTransfer` reverts.

**K2-I2 (re-registration safety). Proof of absence.**

`registerRewardToken` does not reset `rewardData[t]`. This is still safe, for two reasons:

- Unregistration requires `rate·e = rate·ℓ = 0`, so either `rate = 0`, or `lastUpdate ≥ finishAt` at the time of unregistration. Hence `pending() = (0, 0)` at any later time.
- The residual `queued < P` that is ignored at unregistration (memory-only zeroing, L3709) stays in storage and stays backed. It is scheduled at the first `increase` after re-registration.

Minimal assumption set: K2's own guards **[E]**.

*Relaxation.* None within K2. Setting `periodLength = 0` instead triggers K2-F1.

**Atomicity (`depositReward`). Proof of absence.**

The yield point `safeTransferFrom` precedes every write. A callback at that point (for example an ERC-777 hook on a manager-chosen token) observes the pre-state, and every bridge invariant holds there. `depositReward` holds no lock. K3's `checkpoint`/`claim` take `nonReentrant`, and re-entering them from the hook runs on a consistent state. No atomicity gap.

---

## K3 — `MultipleRewardAccumulator`

### State space

| Variable | Type | Stratum | Line |
|---|---|---|---|
| `rewardReceiver[u]` | address | 𝒫 (user-owned) | L2095 |
| `rewardSnapshot[t] = {timestamp: uint64, integral: uint192}` | struct | ℐ | L2100 |
| `userRewardSnapshot[u][t] = {rewards: {pending: uint128, claimed: uint128}, checkpoint: {timestamp, integral}}` | struct | ℒ (pending, claimed) + ℐ (checkpoint) | L2105 |
| abstract `_getTotalPoolShare()`, `_getUserPoolShare(u)` | uint256 | ℒ of the instantiation | L2299–L2304 |

### Abstraction and reference machine

```
α_u(t) = pending_u + ⌊(I_t − I_{u,t}) · share_u / 1e18⌋        (claimable, L2124)
```

In the eager machine `M^E`, every accrual of `x` at total `S` credits each user `x·share_u/S`.

### Obligations

- **O3a**: `_checkpoint(u)` precedes every change of `share_u`.
- **O3b**: a global accrual precedes every change of `S`.
- **O3c**: `Σ_u share_u = S`.
- **O3d**: the custody cell of reward token t is not read differentially by any other action.

### Theorem K3-T1 (solvency, polarity ≤ 0). Proven-derived; sanity Proven-executed.

Under O3a–O3c and the K2 guards:

```
∀t:  Σ_u (claimed_u,t + α_u,t)  ≤  Σ_k x_k,t  ≤  deposits_t
```

*Proof.*

1. Accrual k adds `ΔI_k = ⌊x_k·1e18/S_k⌋ ≤ x_k·1e18/S_k` (L2294).
2. By O3b, `S_k` is the total in force during the accrual. By O3c, `S_k = Σ_u share_u(k)`.
3. By O3a, `share_u` is constant between consecutive checkpoints of `u`. So:

   ```
   α_u − pending_u = ⌊Σ_k ΔI_k·share_u / 1e18⌋ ≤ Σ_k ΔI_k·share_u / 1e18
   ```

4. Summing over u gives at most `Σ_k ΔI_k·S_k/1e18 ≤ Σ_k x_k`.
5. `pending` and `claimed` are only ever moved between, never created (L2262–L2276). ∎

*Defect class.* Quantized. The loss is less than 1 wei per user per checkpoint per token, plus less than `S/1e18` wei per accrual.

*Executed sanity check* (`k3_conservation_and_O3a.js`, run 1). Deposit 700e18; Σ claimable = 699 999 999 999 999 753 600. The surplus of 246 400 wei is the K1 rounding remainder held in `queued`. Both claims succeed, and the final custody is 246 400 wei.

### Relaxations: the polarity of the defect depends on *which* obligation is broken. Proven-executed

All three runs use the same trace. A stakes 10e18 at T. `depositReward(700e18)` at T+1, P = 7d. B adds 10e18 at mid-period. Then checkpoint and claim after the period ends.

| Relaxation | A | B | Σ claimable | δ_A, δ_B (vs `M^E`) | Polarity | Observable outcome |
|---|---|---|---|---|---|---|
| none (O3a–O3c hold) | 525e18 | 175e18 | 700e18 − 246400 | ≈ 0 | ≤ 0 | both claims succeed |
| O3a **and** O3b broken (share change with no checkpoint at all) | 350e18 | 350e18 | 700e18 − 246400 | −175e18, +175e18 | 0 (redistribution) | B takes half of A's first-half rewards |
| **O3a only** broken (global accrual done, user snapshot stale) | 525e18 | 525e18 | **1050e18** | 0, +350e18 | **> 0 (insolvency)** | A's `claim()` **reverts**: `ERC20: transfer amount exceeds balance` |

*Interpretation.* The commutation defect `δ` of a share-changing action is a function of the subset of obligations it violates:

- A missing *global* accrual mis-prices the past at the new total. This only **redistributes**.
- A missing *user* snapshot alone re-credits the past to the newcomer. This **creates liabilities**.

This is the decisive test for every instantiation of K3 (see `02-concentrator.md`): find each share-changing path, then classify it by the obligation subset it discharges.

### Further K3 items

**K3-F1 (forced checkpoint; quantized CII defect). R1. Proven-derived.**

`checkpoint(account)` (L2152) and `claim(account)` (L2168) are permissionless, and every checkpoint floors. A third party can therefore force at most 1 wei of loss per token per call on any account. The transfer destination is unchanged: `claim` for others may only pay `account` or its stored receiver (guard at L2169). The defect is bounded and quantized, with gas cost ≫ value.

**K3-F2 (silent truncation). [L].**

- `uint128(claimable)` at L2233 truncates if claimable ≥ 2¹²⁸.
- `uint192(...)` at L2294 truncates if the cumulative `Σ x·1e18/S ≥ 2¹⁹²`. At `S = 1` wei this needs `Σ x ≳ 6.3e39`, which is unreachable for any real token.
- `queued += uint96(x)` (L2288) silently truncates `x ≥ 2⁹⁶` before a checked add.

All three thresholds exceed realistic supplies.

Contrast with K4 (`04-fx.md`): there the same quantity is multiplied by `magnitude` ≤ 1e18 in **checked** uint192 arithmetic (L17151). That lowers the revert threshold to `x ≳ 6.3e21 · S / 1e18 · (1e18/m)`.

**K3-I1 (third-party claim commutes). Proof of absence.**

`claim(account, 0)` by any caller ≡ `claim(account, 0)` by the account itself. The destination is `rewardReceiver[account]` or `account` (L2244–L2248).

---

## K5 — `WordCodec`

`insertUint` (L23–L37) does not mask `value`. If `value ≥ 2^bitLength`, the bits above the field are OR-ed into neighbouring fields.

*Discharge.* Every in-bundle call site checks a bound before inserting, so K5 is discharged for those setters **[E]**:

- `updateBoosterRatio` (L708–L716), with `MAX_BOOSTER_RATIO = 2e8` (L529, L709).
- `updateExpenseRatio` / `updateHarvesterRatio` / `updateWithdrawFeePercentage` (L1101–L1138), with `MAX_*` checks before the 30-bit inserts.
- MarketV2 fee and ratio setters (L7409–L7551). Their bounds are discharged in `04-fx.md`.

All of these are **R4** setters, so any residual issue is a trust-boundary note only.

`decodeInt` (L72–L92) sign-extends correctly for `1 ≤ bitLength ≤ 255`. `insertInt` masks its input (L67).

## K6 — `FeeCustomization`

The customized rate is bounded to `[0, 1e9]` (L4036, **[E]**). The storage slot is `keccak(feeType, user ⊕ SALT)` (L4082–L4089); it does not collide with the sequential layout in practice.

A consumer that divides by `FEE_PRECISION − rate` would revert at `rate = 1e9`. `AladdinCompounder.setWithdrawFeeForUser` caps the rate at `MAX_WITHDRAW_FEE = 1e8`, so it cannot reach this. This is an R4 note only.

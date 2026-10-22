# SBD — Stratified Bridge Decomposition

Analysis protocol for `gigabundle.txt` (AladdinDAO Concentrator / CLever / f(x) Solidity sources, 17 881 lines, 106 files).

Citations use bundle line numbers: `L1234` means line 1234 of `gigabundle.txt`.

---

## 0. Why this decomposition

A per-contract or per-function decomposition follows the syntax of the code. SBD cuts the state space differently. First it splits the state into strata by *who can write a variable and how it evolves*. Then it uses the inter-stratum invariants ("bridges") as the analysis axes. Most accounting defects in index-based DeFi systems turn out to be failures of a *bridge*, not of a single function. Organising the search by bridge exposes defects that are spread over several functions or contracts.

---

## 1. Strata: a partition of the state space

Every persistent state variable `v` is assigned to exactly one stratum.

| Stratum | Symbol | Content | Who can write it |
|---|---|---|---|
| Custody | 𝒞 | Exogenous balances: `IERC20(t).balanceOf(this)`, the ETH balance, balances held by external venues for this contract (gauge / reward-pool / locker / strategy balances) | Only via yield points (external calls) or by the environment: donations, rebases, venue fees, slashing |
| Ledger | ℒ | Endogenous claim records: shares, `totalSupply`, `totalAssetsStored`, per-user deposits, debts and locks, stored per-user pending rewards, aggregate liabilities | The contract itself |
| Index | ℐ | History summaries that allow O(1) settlement: reward integrals, `accRewardPerShare`, products / epochs / exponents, and per-user snapshots of these | The contract itself |
| Tempo | 𝒯 | Schedule state: `lastUpdate`, `finishAt`, `rate`, `periodLength`, epoch and unlock times, EMA timestamps | The contract; evolves with `block.timestamp` |
| Policy | 𝒫 | Role- and owner-controlled parameters: fee rates; zap, converter, strategy, oracle, stash and treasury addresses; role sets; caps; pause flags. 𝒫₀ ⊂ 𝒫 holds immutables and constants | Privileged roles only (𝒫₀: nobody after construction) |

Transient variables (memory/stack) are not state. Report one only when it **caches a stratum value across a yield point**. That case is called a *stale cache across a yield point*.

The global system is the synchronous product of per-contract systems:

```
M = (S, S0, Act, →)
S   = Π_contracts (𝒞 × ℒ × ℐ × 𝒯 × 𝒫)  ×  Env
Env = block.timestamp, external venue states, oracle answers, other users' balances
```

The environment advances `block.timestamp` monotonically between transactions, never within one. It can also perform any action of an unprivileged account.

---

## 2. Action footprints

For every action `a` (external/public function, callback, or an internal step reachable from one), record:

- **guard** `g_a`: the preconditions. This means `require`/`revert`, modifiers, and implicit guards such as checked arithmetic in 0.8, SafeMath in 0.7, and SafeCast.
- **effect** `e_a`: the postcondition, as a relation between pre-state and post-state.
- **footprint**: the read and write sets in each stratum.
- **yield points** `Y_a`: the ordered external calls, each tagged with one of:
  - `Y⁰`: a fixed or immutable venue address (constant or immutable).
  - `Y^𝒫`: an address taken from the policy stratum (zap, converter, strategy, oracle).
  - `Y^U`: a user-influenced callee, such as an ETH send to `msg.sender`/receiver, a user-supplied token address, or a hook.
- **lock domain**: the reentrancy guard, if any, and which functions share that lock.
- **atomic segments** `s₀ y₁ s₁ … y_k s_k`: the stretches of code between consecutive yield points.

---

## 3. Bridges: the inter-stratum invariants (analysis axes)

### B1 — Backing (𝒞 ⊒ ℒ) and the custody map κ

A **logical pool** `p` is any ledger aggregate that must be backed by real tokens. Examples: the assets owed to all share holders, the pending rewards in token τ, protocol fees owed.

The **custody map** `κ(p) = (token, holder[, venue])` gives the physical cell that backs `p`.

The **backing invariant** is:

```
∀ cell c :  bal(c)  ≥  Σ_{p ∈ κ⁻¹(c)} Liab(p)
```

Hazards to look for:

- **Custody aliasing.** `|κ⁻¹(c)| ≥ 2`: two logical pools share one physical cell.
- **Balance-differential read (BDR).** An action derives an amount from `bal(c)`, or from `bal_after(c) − bal_before(c)`. When a BDR hits an aliased cell, other pools' value gets attributed to one pool. This is called *aliasing absorption*.
- **Type aliasing.** Two logical token identifiers (constants or variables) resolve to the same address. As a result, κ silently merges pools that the specification keeps apart.

### B2 — Lazy–eager refinement (ℐ realizes ℒ)

- **Reference machine `M^E`.** Every distribution or decay event immediately updates each user's entitlement pro rata. This costs O(n) per event and serves as the specification.
- **Abstraction `α`.** A map from the lazy state to the per-user entitlement vector. For example: `α_u = pending_u + share_u · (I − I_u) / PREC`.
- **Commutation defect.** `δ_a(σ) = α(a(σ)) − a^E(α(σ)) ∈ ℤ^Users`. Defects fall into three classes:
  - **exact**: `δ ≡ 0`.
  - **quantized**: `|δ_u| ≤ k` wei per action.
  - **structural**: unbounded.
- **Rounding polarity.** `π(a) = sign(Σ_u δ_u)`.
  - `π ≤ 0` is protocol-favoring (safe).
  - `π > 0` is liability-inflating, which makes the action an insolvency accumulator.

**Obligation discharge.** Every instantiation of a kernel module (§5) must discharge that module's obligations. Each undischarged obligation is a B2 finding.

### B3 — Sampling-schedule invariance (𝒯 → ℐ/ℒ)

Each time-driven update is modelled as a family of operators `U_Δ`, applied whenever an action samples the clock.

- **Flow (semigroup) property.** `U_{s+t} = U_t ∘ U_s`.
- **Schedule defect.** `D(s,t) = U_{s+t} − U_t ∘ U_s`.
- **CII (checkpoint-insertion invariance).** Insert any permissionless state-sampling action (checkpoint, poke, harvest, a zero-amount claim/deposit) at any point in a trace. This must not change any user's α-entitlement by more than a quantized defect.

A CII or flow violation means the outcome is **schedule-steerable**: whoever chooses the poke times can choose the distribution.

### B4 — Policy retroactivity (𝒫 → ℐ/ℒ)

A policy write `w` at time `t` is **prospective** iff, for all traces:

```
outcome(ρ · w · σ) = outcome(ρ · settle* · w · σ)
```

Here `settle*` means checkpointing every user and pool. Otherwise `w` is **retroactive**: it re-prices quantities that accrued before `t` but were not yet settled. Report each retroactive write together with the quantity it re-prices.

### B5 — Inter-contract gluing (ℒ_X ↔ ℒ_Y / 𝒞_Y)

Contract X sometimes keeps a record about contract Y. Examples: X's stored count of Y-shares, X's cached price of Y, X's notion of Y's total.

The **gluing equation** `G_{X,Y}` must hold at every yield point where either contract can observe the other. A violation is called **chart drift**.

### Atomicity lens: yield-point obligations

For each bridge invariant `J`, each action `a` and each yield point `y ∈ Y_a`: does `J` hold in the state at `y`?

If not, report an **atomicity gap**, with its segment index, when the callee class can do either of these:

- re-enter a mutating function that the same lock does not cover; or
- read a view function whose value depends on the broken `J` (read-only reentrancy).

### Exit liveness (Spec ⊄ Impl)

Find states in which the specification says a user can exit (withdraw, redeem, claim, unlock) but every implementation path reverts. Possible causes: underflow, a stale schedule, an external venue pause, a broken kernel precondition, or an ordering constraint.

---

## 4. Adversary-rank lattice

Each counterexample is tagged with the **minimal** rank that suffices:

| Rank | Actor | How a finding at this rank is classified |
|---|---|---|
| R0 | No adversary: honest interleavings reach the bad state | Specification defect |
| R1 | Any unprivileged account (EOA or contract); can donate, front-run/back-run, choose poke times | Vulnerability |
| R2 | Keeper / harvester role (semi-trusted) | Semi-trusted actor |
| R3 | Reward-distributor / reward-manager role | Semi-trusted actor |
| R4 | Owner / admin (trusted) | Reported only as a **trust-boundary gap**: something the spec or comments say cannot happen, but the code permits |
| Rv | External venue or oracle deviating from its assumed behaviour: price manipulation, fee-on-transfer, rebasing, pause, slippage, or a return value different from the assumed one | Environment deviation |

## 5. Assumption ledger tags

Every environmental assumption is tagged:

- **[E]**: enforced by the code (cite the line).
- **[C]**: convention — documented in a comment or interface, but not checked.
- **[L]**: luck — neither enforced nor documented. It holds only because of the current deployment or parameter values.

For each assumption, give the **relaxation** that yields a counterexample.

---

## 6. Kernel assume-guarantee interfaces (shared modules)

These modules are shared across subsystems. Each instantiation must discharge their obligations.

### K1 — `LinearReward.increase(data, P, amt)` (L350–L379)

Precondition, i.e. the caller's obligation:

- `data.lastUpdate == block.timestamp`, **or** the caller has already credited `rate·(min(now,finishAt) − lastUpdate)`.

If this does not hold, the two branches behave differently:

- When `now ≥ finishAt`, the un-accrued amount is overwritten, which **destroys** it.
- When `now < finishAt`, it is rolled into the new period (`rate·(finishAt − lastUpdate)`, L369).

Second precondition: `P` must be unchanged since the previous `increase`. Otherwise `block.timestamp − (finishAt − P)` (L365) can underflow and revert.

Guarantee: `Σ_t rate·Δt + queued = Σ amt`, up to fewer than `P` wei of rounding per call.

Re-extension rule (L367): a deposit made while `_distributed·9 ≤ amt·10` restarts a full period over `amt + remaining`. Near the start of a period `_distributed ≈ 0`, so **any** amount (even 1 wei) re-extends the period.

### K2 — `LinearMultipleRewardDistributor` (L3566–L3759)

- **Enforces K1** by calling `_distributePendingReward()` (L3659; body at L3739) before `_notifyReward` (L3661) in `depositReward` (L3650).
- `periodLength` is immutable (L3582); its domain is `0 ∪ [1 day, 28 days]` (L3608).
- **Obligation O2a.** When `periodLength == 0`, `_notifyReward` (L3728) calls `_accumulateReward` directly (L3730). `queued` is read only by `LinearReward.increase`, which is never called in this mode. So any amount that `_accumulateReward` *queues* (because total share is 0) is never consumed. It also blocks `unregisterRewardToken`: with `periodLength == 0`, the guard `queued < periodLength` is false, so `queued` is kept, and the check `queued + … > 0` reverts (L3709–L3710). The instantiation must therefore guarantee that total share is greater than 0 at every deposit made in this mode.
- **Re-registration.** `registerRewardToken` (L3675) does not reset `rewardData[token]`.

### K3 — `MultipleRewardAccumulator` (L2048–L2305)

Obligations on every instantiation:

- **O3a.** Every change of `_getUserPoolShare(u)` must be immediately preceded by `_checkpoint(u)`: in the same atomic segment, with no distribution in between.
- **O3b.** Every change of `_getTotalPoolShare()` must be preceded by `_distributePendingReward()`, so that pending linear rewards are integrated against the *old* total.
- **O3c.** `Σ_u _getUserPoolShare(u) == _getTotalPoolShare()`.
- **O3d.** The reward token must not be the staking token, and must not alias any other ledger. Otherwise, under B1, `safeTransfer` in `_claimSingle` draws on principal.

Guarantees:

- `claimable(u)` equals the eager sum `Σ_i r_i·u_{i−1}/s_{i−1}`, floored once per checkpoint. The polarity is ≤ 0.
- The integral is truncated to `uint192` (L2294), `pending` to `uint128`, and `queued += uint96(amount)` silently truncates `amount` (L2288).

### K4 — `MultipleRewardCompoundingAccumulator` (L16879–L17162) + `DecrementalFloatingPoint` (L16603–L16680)

Obligations:

- **O4a.** As O3a and O3b, with the product taken into account.
- **O4b.** The product update must be `prod.mul(scale)` with `scale = (s−d)/s·1e18 ≤ 1e18`, applied *after* a global checkpoint at the old total.
- **O4c.** `_getUserPoolShare(u)` returns `(prod at u's last checkpoint, u's compounded share)`, and the two must be consistent across exponent and epoch boundaries.
- **O4d.** Gains that span two or more exponent changes are truncated to two portions (L17043–L17046). This is by design; quantify the loss.

Risk point: in `DFP.mul` (L16659), the exponent branch (L16670–L16671) yields `magnitude = m·scale/1e9`. That is below `1e9` whenever `m·scale < 1e18`, and is `0` when `m·scale < 1e9`. A zero magnitude makes `_claimable` divide by zero (L17051), and makes `_accumulateReward` add 0 to the integral (L17151). Check whether this is reachable, given how the instantiation computes `scale`.

### K5 — `WordCodec` (L20–L129)

`insertUint` does not mask `value`. Any `value ≥ 2^bitLength` corrupts higher fields. Callers must bound `value`.

### K6 — `FeeCustomization` (L3996–L4110)

The customized rate may be any value in `[0, 1e9]` (L4036). A consumer that divides by `FEE_PRECISION − rate` reverts at `rate == 1e9`; this requires R4.

---

## 7. Finding format

Each finding records:

1. **ID**, and the **bridge** (B1–B5, Atomicity, Exit-liveness, or Intra-stratum).
2. **Invariant**, written as a predicate over the stratified state.
3. **Minimal adversary rank.**
4. **Counterexample trace.** A numbered sequence of `(state projection) —action→ (state projection)` with concrete numbers. Project only onto the variables that matter.
5. **Required assumptions** for the invariant to hold, each tagged [E]/[C]/[L].
6. **Relaxation**: which assumption, relaxed in which way, yields the counterexample.
7. **Refinement gap.** An observable trace, marked either `Impl ⊄ Spec` (the implementation allows a forbidden behaviour) or `Spec ⊄ Impl` (the implementation forbids a permitted behaviour). Name the specification source: NatSpec, the ERC standard, or a documented formula.
8. **Confidence**, one of:
   - *Proven-executed*: an executed model or compiled code reproduces it.
   - *Proven-derived*: a manual derivation with every step cited.
   - *Plausible*: depends on unverified external behaviour.
9. **Evidence**: line citations.

Proofs of absence use the same format. Give the invariant, the minimal assumption set under which it holds, and one relaxation per assumption that breaks it.

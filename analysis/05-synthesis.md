# 05 — Synthesis: global transition system, cross-subsystem laws, consolidated findings

This document composes four sources:

- the kernel analysis (`01-kernel.md`);
- the three subsystem analyses (`02-concentrator.md`, `03-clever.md`, `04-fx.md`);
- the mechanized atlas (`atlas/`).

All four use the Stratified Bridge Decomposition (`00-sbd-framework.md`).

The contribution of this document is a set of **six cross-subsystem laws**. Each law is a structural statement about the codebase. Every verified finding is an instance of at least one law, and every law has instances in at least two of the three subsystems. With the laws, the 67 individual findings reduce to a small number of mechanisms. The atlas then enumerates the remaining sites where each mechanism could recur.

### Confidence vocabulary

| Code | Meaning |
|---|---|
| **PE-c** | Proven-executed on the compiled, unmodified bundle bytecode, and re-executed by the coordinator from `harness/` with output identical to the original run |
| **PE-m** | Executed exact-integer model |
| **PD** | Proven-derived |
| **PL** | Plausible: depends on unverified external behaviour |

---

## 1. Global transition system

### 1.1 Composition

The bundle is modelled as a synchronous product of four component systems that interact only at **ports**. A port is a cross-contract yield point whose callee is another in-bundle component.

```
M = M_K ⊗ M_C ⊗ M_CL ⊗ M_FX ⊗ Env

M_K   kernel instances (K1–K6), embedded in the contracts that inherit them
M_C   Concentrator (02):  GaugeWrapper ⇄ SdCrvCompounder ⇄ stashes;  Convex vaults ⇄ AladdinCRV
M_CL  CLever (03):        CLeverCVXLocker ⇄ Furnace ⇄ AMO (AladdinCVX) ⇄ Curve;  MetaFurnace
M_FX  f(x) (04):          MarketV2/MWFC ⇄ TreasuryV2/TWFC/Wrapped ⇄ (splitter) ⇄ rebalance pools (K4)

S   = Π_c (𝒞_c × ℒ_c × ℐ_c × 𝒯_c × 𝒫_c) × Env
Env = (now, venue states [Convex, StakeDAO, Curve, CvxLockerV2, oracles, crvUSD AMM, ve, gauges],
       ERC20 ledgers, out-of-bundle contracts [splitter, registry, reserve pool, aFXS, clevCVX, fToken/xToken])
S0  = post-initialize states of all components; venue states arbitrary but satisfying their stated contracts
Act = ⋃_c Act_c  ∪  Act_env
Act_env = { tick(Δ>0), venue accrual, price/rate/index moves, third-party venue calls
            (getReward(account), stakeFor, bribe claims on behalf), donations }
→   = interleaving of atomic transactions. Within a transaction, control passes along ports;
      revert is the identity on S. block.timestamp is constant within a transaction and monotone across them.
```

Ports (cross-component edges):

| Port | Caller → callee | Line |
|---|---|---|
| π₁ | Convex vault → `AladdinCRV.deposit` | L12305 |
| π₂ | `SdCrvCompounder` → gauge wrapper | L1426–L1427, L1520 |
| π₃ | wrapper stash → wrapper | L3449 |
| π₄ | `CLeverCVXLocker._distribute` → `Furnace.distribute` | L14076 |
| π₅ | AMO → Furnace | L9089, L9094, L9100 |
| π₆ | MWFC → `treasury.harvest` | L17189 |
| π₇ | treasury → splitter → pools.`depositReward` | L9934–L9939; splitter outside the bundle |
| π₈ | pool → market redeem | `liquidate` |

Several findings exist only as *port compositions*: CL-06 (π₄ ∘ Furnace), FX-02 (π₆ ∘ TWFC), and K1-F2 / FX-04 (gauge mint ∘ K1).

### 1.2 Size of the system (mechanized; `atlas/A1`)

| Quantity | Value |
|---|---|
| Concrete contracts / entry functions | 19 / 560 |
| Mutating entry functions | 377 |
| — open | 137 |
| — `cond[harvester]` | 5 |
| — gated | 221 |
| — initializers | 14 |
| Mutating actions that sample the clock | 114 |
| Mutating actions with a non-static yield point | 157 |
| Mutating actions that write storage after a non-fixed yield point | 55 |
| Mutating actions under `nonReentrant` | 74 |
| Balance-read (`balanceOf(this)`) sites | 74 |
| — reachable from open actions | 49 (9 **A**bsolute, 7 **V**aluation, 28 **D**ifferential, 5 **C**ap) |
| Open clock-sampling actions with clock-coupled writes (poke graph) | 73 |

### 1.3 What is abstracted or omitted

- **External venues.** Modelled as environment actions with stated contracts. Their source is not in the bundle.
- **Out-of-bundle protocol contracts.** Splitter, registry, reserve pool, aFXS, CLeverToken, fToken/xToken internals.
- **`LogExpMathV8`.** Treated as an approximation oracle.
- **Not modelled.** Gas (except where a loop bound is an R3/R4 DoS lever), events, price impact beyond the Curve reference model (CLever T11/T14), and EIP-1271 semantics.

---

## 2. The six laws

Each law has the same parts:

- a **statement** over the stratified state;
- the **instances**, as finding IDs with rank and confidence;
- the **safe side**: the minimal assumption set under which the law's invariant holds;
- the **relaxation** that produces the counterexample class;
- an **atlas prediction**: where else in the bundle the mechanism can occur.

---

### L1 — The Pole Law (singularities of the abstraction map)

**Statement.** Every lazy ledger in the bundle has an abstraction map whose value is a quotient by a *total* `T`:

```
α_u = x_u·(I − I_u)/T,  or  shares·assets/T,  or  b_u·P/P_u
T  ∈ {S, TS, TAS, TU, totalShare, owner aggregate, B, DFP magnitude m}
```

The map has a pole at `T = 0`. It also has a **near-pole region** `𝒩 = {0 < T ≤ ε·inflow}`. Inside 𝒩 the quantization defect is amplified by the factor `A = inflow / T`.

Because α is undefined at the pole, every implementation must pick a **pole-resolution policy** ρ. Each policy found in the bundle produces its own counterexample class:

| Policy ρ (what the code does at T = 0) | Site | Counterexample at the pole | Near-pole counterexample | Rank | Conf. |
|---|---|---|---|---|---|
| **queue** (hold until the next notify) | K2 with P = 0 (L3730 → L2288) | rewards stranded forever; `unregister` blocked (K2-F1) | — | R0, latent | PE-c |
| **freeze clock, credit next** (`lastUpdate` not advanced) | AladdinCompounder (L3103–L3108) | first depositor captures the empty interval (CONC-08) | the victim's 150e18 deposit mints **0 shares** | R1 | PE-c |
| **advance clock, credit nobody** | ConcentratorConvexVault empty pool (L11407) | 200 of 700 orphaned (O-1) | — | R0 | PE-m |
| **identity mint** while TAS > 0 | SdCrvCompounder with P = 0 (L1533) | deposits mint 0 and are locked forever (CONC-06) | — | R0 | PE-c |
| identity mint + **V-read** that can be donated to | AladdinCRV (L10399) | — | 999e18 deposit → 0 shares (CONC-10) | R1 | PE-m |
| identity mint, supply = 1 | AMO (L8575, unchecked) | — | victim's `unlock` → 0 shares (CL-12) | R1 | PE-m |
| **epoch reset** at scale = 0 while S > 0 | MRCA / DFP (L16381–L16404) | orphan supply S = 1 owned by nobody (FX-13) | — | R2 | PE-c |
| near-pole **checked overflow** | MRCA (L17151) | — | every pool action reverts permanently after ≥ 6 277·S tokens (FX-08) | **R1** | PE-c |
| **magnitude pole** (m → 0) | `DFP.mul` (L16669–L16671) | m = 0 ⇒ division by zero; locked even after the next epoch (FX-14) | denormal snapshot ⇒ a 1e24 stake becomes 0 (FX-14b) | R2 | PE-c |
| **paid-off** (TU = 0, `acc := 0`) | Furnace (L4843–L4849) seen through the AMO | AMO `unlock` mints 0; `withdraw` divides by zero (CL-02) | — | R0 | PE-c |
| **owner aggregate = 0** | Shareable (L15691) | vote-sharing stakers locked forever (FX-01) | — | R0 | PE-c |
| **B = 0** | Treasury (L9604 → L8229) | every mint/redeem divides by zero; re-initialization blocked (FX-07) | — | R0 | PD |

**Safe side** (minimal assumptions under which α stays defined and quantization stays bounded):

1. T never reaches 0 while inflow continues **[L]**;
2. no dust T coexists with large inflow **[L]**;
3. the first deposit is never adversarial **[L]**.

None of the three is enforced by code.

**Relaxation.** Any of the three is relaxed by an R0 or R1 trace: a full exit, a full liquidation, or a 1-wei first deposit.

**Law-level observation.** Twelve findings across all three subsystems are instances of one mechanism. The policies differ, but **no site implements a policy that is sound at the pole and bounded in the near-pole region**. A sound design needs both:

- (i) rewards that arrive while `T = 0` are either returned or queued with *guaranteed* release;
- (ii) a minimum-total invariant (`T = 0 ∨ T ≥ T_min`), or virtual shares, so that the amplification factor A stays bounded.

**Atlas prediction.** Every open action in `atlas/A2` that writes ℐ variables of the form `x·1e18/T` is a candidate. All such sites in the bundle are covered by the instances above.

---

### L2 — The Obligation-Subset Polarity Law (B2)

**Statement.** Take an accumulator kernel with obligations:

- **Pre1**: accrue before notify;
- **O3a**: user snapshot before a share change;
- **O3b**: global accrual before a total change;
- **O3c**: `Σ shares = total`.

The **sign** of the aggregate commutation defect `Σ_u δ_u` is determined by *which subset* of obligations an action violates:

| Violated subset | Σδ | Defect class | Instances | Conf. |
|---|---|---|---|---|
| none | ≤ 0, quantized | protocol-favouring dust | all K3 instantiations that discharge (02 GW-1/2), CLever locker (I-L9), f(x) normal snapshots | PE-c |
| Pre1, notify at `now ≥ finishAt` (β1) | **< 0** | **destruction** (orphaned custody) | **K1-F2 = FX-04** (L16306, L15269); **CONC-01 case A** (L3891) | PE-c ×2 |
| Pre1, notify at `now < finishAt` (β2) | = 0 | **temporal reallocation** to later stakers | K1-F2 β2; CONC-01 case B | PE-c / PE-m |
| O3a ∧ O3b | = 0 | **redistribution** between users | kernel demo (`k3_conservation_and_O3a.js`, run 2) | PE-c |
| O3a only | **> 0** | **liability inflation (insolvency)** | kernel demo (run 3: 1050e18 vs 700e18); **CONC-14** (re-activation re-notifies custody that already backs historical claims; 140e18 vs 70e18) | PE-c ×2 |
| O3c, Σ shares < total | < 0 | orphaned distribution | CONC-07 (ghost shares); FX-06 / FX-13 (orphan supply Ω) | PL / PE-c |
| aggregate rounded against the parts (aggregate < Σ parts) | > 0 | last exit wraps or reverts (see L6) | CL-01; FX-05 | PE-c |

**Corollary (side-entry notify hazard).** K2 exposes one canonical, Pre1-safe notify path: `depositReward` (L3659 → L3661). All three Pre1 violations in the bundle are **side entries** that call the internal `_notifyReward` directly:

- `harvestBribes` (L3891);
- `BoostableRebalancePool._checkpoint` (L16306);
- `ShareableRebalancePool._checkpoint` (L15269).

The boost-forfeit side entry (L16348) is Pre1-safe only by its position, after the accrual.

So the law yields a *syntactic* check: **every call to `_notifyReward` that is not dominated by `_distributePendingReward` in the same frame is a Pre1 violation.** The atlas event traces (`atlas/footprint.json`) can decide this mechanically. The three violations above are the complete set in the bundle.

**Safe side.** Instantiations discharge Pre1 and O3a–O3c **[E where code-enforced; violated at the listed sites]**.

**Relaxation.** Remove the accrual from any notify path: β1 then destroys, β2 then reallocates.

---

### L3 — The Custody Aliasing Law (B1)

**Statement.** Suppose all of the following hold:

1. a custody cell `c` backs at least two logical pools: `|κ⁻¹(c)| ≥ 2`;
2. an action `a` derives one pool's credit from an **absolute (A) or valuation (V)** read of `bal(c)`;
3. some action `p` (a "push") can move another pool's value into `c`.

Then "each pool is credited only its own value" fails, at rank `max(rank(p), rank(a))`. If an honest actor performs `a` on schedule anyway, the rank collapses to `rank(p)`; see L5.

Type aliasing is the degenerate case: two logical token identifiers resolve to one address, so κ merges pools that the specification keeps apart.

| Instance | Cell c | A/V read | Push p (rank) | Effect | Conf. |
|---|---|---|---|---|---|
| CONC-09 | reward tokens @ FXS vault and @ CRV vault; plus ETH and CRV @ CRV vault | L11212; L12283, L12289, L12300 | Convex `getReward(vault)` (R1, A-CVX-PERM) | pool A takes B's rewards: 100/0 instead of 50/50 | PE-c (vault); push PL |
| **CONC-02** | FXS @ FXS vault, **type-aliased** with cvxFXS (L17756 = L17760) | transfer of the "cvxFXS" constant = FXS (L17830) | Convex `getReward` of another pool (R1) | non-aFXS claims revert, or are paid out of another pool's FXS (120 of 150); real cvxFXS stranded | PE-c |
| CL-07 | CVX @ locker | L13674 (`totalCVXInPool − TUG`); keeper-trusted amount (L14036) | third-party bribe claim on the locker's behalf (R1) | users' unlocked CVX sent to the Furnace; `withdrawUnlocked` reverts | PE-m |
| CONC-14 | SDT @ wrapper (backs historical claims) | L694 (absolute balance on re-activation) | R3 unregister + R1 `syncActiveRewardTokens` | Σ claims = 2 × custody; second claimant reverts | PE-c |
| CONC-10 | cvxCRV staking balance of aCRV | L10399 (V) | Convex `stakeFor(aCRV)` (R1) | inflation: 999e18 deposit → 0 shares | PE-m |
| CL-08 | reward tokens @ locker | L13486–L13497 (D window) | third-party `getReward(locker, stake)` (R1) | rewards stranded outside the D window | PL |
| (by design) | base @ treasury | L9538 (V) | donation (R1) | donations become rewards. Gives R1 a reward-injection capability, which feeds L4 | PD |

**Completeness by enumeration** (`atlas/A3`). All 49 open-reachable balance reads were classified:

- 28 D and 5 C reads cannot absorb another pool's value, except where the D window itself spans a third party's push (CL-08).
- Of the 9 A and 7 V reads, every one sitting on an aliased cell (|κ⁻¹| ≥ 2) yields a counterexample listed above.
- The remaining A/V sites sit on single-pool cells, or on cells whose second pool is internally accounted:
  - AladdinCRV harvest sweeps (L10656–L10665);
  - last-withdrawer sweep (L10609);
  - Furnace `totalCVXInPool` (L4461–L4463): the realised and pending pools are both subtracted, so I-F2 holds under a fixed P;
  - locker stake rebalance (L14079–L14080);
  - MetaFurnace view (L5079): no aliasing, but exit-liveness under CL-04.

The law is therefore **complete for the bundle**: there are no further A/V-on-aliased-cell sites.

**Safe side.** κ is injective on the cells that A/V reads touch **[violated]**, or every push into a shared cell is gated **[L: Convex `getReward(account)` is permissionless]**.

---

### L4 — The Re-anchoring Law (B3: what breaks schedule invariance)

**Statement.** Every time-driven operator in the bundle factors into two parts:

- a **continuous part** `U_Δ`: accrual at a stored rate;
- a **discrete re-anchoring part** `N_t`: notify / restart / gauge mint / boost checkpoint / epoch processing / funding capture. `N_t` resets the anchor `(rate, lastUpdate, finishAt)` or prices an interval using state sampled at `t`.

The analysis establishes three things:

**(i) Continuous parts are exact flows.** `U_{s+t} = U_t ∘ U_s` holds in every case where the increment over `[t₁, t₂]` uses only parameters anchored at `t₁`:

| Operator | Flow defect | Conf. |
|---|---|---|
| Furnace U_Δ | 0 wei over 200 partitions (CLever T05a) | PE-m |
| K3 integral | exact | PD |
| AladdinCompounder while TAS > 0 | exact | PD |
| EMA | ≤ 87 wei (f(x) T5) | PE-m |

**(ii) The one continuous part that is not a flow prices its whole interval at sample time.** Funding cost uses the price at harvest time, `p(t₂)`, for the interval `[t₁, t₂]`. So two pokes cost 2.68% less than one, and the charge depends on the poke-time price (FX-11). This is the precise boundary of the flow property: **flow ⇔ the generator is anchored, not sampled.**

**(iii) Every CII violation found is a re-anchoring effect.** Inserting or moving an `N_t` changes outcomes, and the poke graph (`atlas/A2`) shows that `N_t` is reachable at R1 in every subsystem:

| Re-anchoring operator | Instance | Measured steering | Rank | Conf. |
|---|---|---|---|---|
| K1 restart (β2 re-extension) | K1-I3 | late staker's share ranges over 302.9 … 350.0 of 1400 for identical inflow | R1 (f(x) harvest path), else R3 | PE-c |
| Furnace restart (`amount + leftover` over a fresh P) | CL-09 | late depositor captures 126.26e18 of 700e18 after six `donate(1)` calls | R1 | PE-m |
| Furnace restart with `amount + leftover < P` | **CL-06** | rate := 0 ⇒ **permanent freeze** (U_Δ then calls `reduce(0)`, which reverts) | **R1**; R0 non-generic | PE-c |
| lump-sum notify (P = 0) | CL-10, CL-13 | just-in-time capture of 5000e18 of 10000e18 | R1 | PE-m |
| empty-interval anchor freeze | CONC-08 | 1-wei captures 350e18; victim gets 0 shares | R1 | PE-c |
| gauge mint notify before accrual | K1-F2 / FX-04 | 660 of 700 FXN orphaned; β2 reallocation on every mint | R0 / R1 timing | PE-c |
| boost checkpoint (history index) | FX-03 (h1c) | forced hourly checkpoints cut the victim to 137.5 vs 333.3 FXN/day | R1 | PE-c |
| ve interpolation at checkpoint | FX-09 | time-weighted boost 0.758 vs 0.40 specified | R1 | PE-m |
| missed epoch processing | CL-17, CL-18 | unlock drift; 109 018.71 CVX shortfall if epoch 2972 is missed | R2 | PE-m |

**Consequence.** For this codebase, B3 needs no continuous-time reasoning. It reduces to a finite check over the re-anchoring operators: enumerate the `N_t` sites, which are the notify / restart / mint / checkpoint writes of `𝒯` variables in `atlas/A2`, and test each for CII.

**Safe side.** Re-anchoring is monotone (it never shrinks pending mass), rate-preserving, and either permissioned or economically neutral **[violated at every listed site]**.

---

### L5 — The Rank Composition Law

**Statement.** The minimal adversary rank of a counterexample trace is the maximum rank over its *adversarial* steps. Honest, scheduled actions of semi-trusted roles (harvester, keeper, distributor, liquidator) behave as environment steps. In addition, the bundle has two kinds of non-constant rank:

- **Policy-conditional rank.** `ensureCallerIsHarvester` (L862–L866) admits anyone when `harvester = 0`. So:

  ```
  rank(τ, σ) = R1  if harvester(σ) = 0,  else R2
  ```

  for every harvest-dependent trace in `SdCrvCompounder`, `AladdinCRV`, both Convex vaults and the AMO (`atlas/A1`, 5 `cond` actions). This is a B4 effect on the *adversary model itself*: a policy write changes who can attack.
- **Time-windowed rank.** `initializeV2` (L1318) is R1 between upgrade and initialization, and ⊥ afterwards (CONC-12, PE-c).

| Composite trace | Adversarial step | Honest step | Effective rank |
|---|---|---|---|
| CONC-09 cross-pool absorption | R1 push (`getReward(vault)`) | harvester's `harvest(A)` | R1 |
| CL-07 locker drain | R1 third-party bribe claim | keeper's `processUnlockableCVX` + bribe harvest | R1 |
| FX-13 → FX-08 | R1 front-run deposit, sized so that S = maxLiq + 1 (PL) | liquidator's `liquidate(maxLiq)` | R1 (PL) |
| CONC-14 | R1 `syncActiveRewardTokens` | manager's `unregisterRewardToken` | R1 given an honest R3 |

**Consequence.** Ranking findings by the *named role* of a step overstates the trust they need. The table in §3 ranks by effective rank.

---

### L6 — The Arithmetic-Regime Duality Law

**Statement.** One logical defect, *a rounding-direction mismatch between an aggregate and its parts* (`Σ parts > aggregate`, or a product leaving its normalized range), shows up differently depending on the arithmetic regime of the site:

| Regime | Observable | Instances |
|---|---|---|
| 0.7.6 unchecked / plain operators | **silent corruption**: the ledger wraps, everything continues, and value is mis-attributed | CL-01 (per-user unrealised rounded **up** at L4707–L4712; aggregate decremented unchecked at L4766: TU = 2¹²⁸ − 1, later distributions stranded, a new depositor realises 29 wei of 1000e18); CL-02 (unchecked share math L8575: 0 shares); CL-16 (`acc` underflow at L4866–L4870 reads as 1.0) |
| 0.8.x checked | **permanent liveness failure** at the first operation that touches the inconsistent aggregate | FX-05 (owner aggregate re-floored at L15420 ends 1 wei below its parts: the last exit panics 0x11); FX-08 (checked uint192 product at L17151); FX-03b (checked uint24 at L16445); FX-14 (magnitude 0 ⇒ panic 0x12) |
| explicit casts (both regimes) | **silent truncation** | K3-F2 (L2233, L2288, L2294), unreachable at realistic scale; contrast FX-08, where the same quantity is a checked product |

**Consequence.** Checked arithmetic does not remove these defects; it converts integrity failures into availability failures. The B2 polarity analysis (L2) must therefore always be paired with an exit-liveness analysis at the same site.

**Safe side.** Parts are floored and the aggregate is decremented by the floored part, or the aggregate is recomputed as the sum of its parts **[violated at the listed sites]**.

---

## 3. Consolidated findings

### 3.1 Counts

| | R0 | R1 | R2 | R3 | R4 | Rv | Σ |
|---|---|---|---|---|---|---|---|
| Kernel (01) | 2 (K2-F1 latent; K1-F2) | 1 (K3-F1, quantized) | — | — | — | 1 (K2-F2) | 4 |
| Concentrator (02) | 7 | 5 | 1 | 1 | 3 | 2 | 19 |
| CLever (03) | 5 | 11 | 3 | 1 | 6 | — | 26 |
| f(x) (04, FX-04 = K1-F2 not double-counted) | 6 | 5 | 3 | — | 2 | 3 | 19 |
| **Σ** | **20** | **22** | **7** | **2** | **11** | **6** | **68** |

Bytecode traces re-executed by the coordinator:

| Source | Traces | Findings covered |
|---|---|---|
| Kernel | 5 | K2-F1, K1-I1/I2/I3, K3 relaxations, K1-F2 |
| Concentrator | 4 + `initv2_race` | CONC-01–06, 08, 09, 12–16 |
| CLever | 4 | CL-01–04, 06, 14, 25 |
| f(x) | 7 | FX-01–03, 05, 08, 13, 14, 16 |

### 3.2 Principal findings

Ordered by effective rank, then impact. Every row has a bytecode trace unless marked otherwise.

| # | ID | Law(s) | Bridge | Rank | Observable consequence | Conf. |
|---|---|---|---|---|---|---|
| 1 | **CL-06** | L4, L1 | B3 / exit-liveness / B5 | **R1** | `CLeverCVXLocker.donate(1)` after `finishAt` sets Furnace rate = 0. Every Furnace action reverts `Furnace: overflow` permanently, and so do AMO checkpoint/withdraw and locker harvest/donate. Only the governor can repair it, by setting P := 0. | PE-c |
| 2 | **FX-08** | L1, L6 | exit-liveness / K4 | **R1** | A 1-wei first deposit into an empty pool with an active stream. Once ≥ 6 277·S reward tokens accrue, every pool action (deposit, withdraw, claim, liquidate, depositReward) reverts permanently. | PE-c (mechanism); volume PL |
| 3 | **CONC-08** | L1, L4 | B3 / B1 | **R1** | asdCRV emptied mid-stream. A 1-wei depositor captures the empty interval (350e18), and a victim's 150e18 deposit mints **0 shares**. | PE-c |
| 4 | **CONC-09** | L3, L5 | B1 | **R1** | Both Convex vaults: `harvest(pid)` credits absolute vault balances, so another pool's pushed rewards are absorbed (100/0 instead of 50/50). | PE-c; push PL |
| 5 | **CONC-02** | L3 (type alias) | B1 / exit-liveness | **R0 / R1** | `FXS ≡ cvxFXS`. Every non-aFXS claim from the FXS vault reverts, or pays out another pool's FXS. Redeemed cvxFXS is stranded. | PE-c |
| 6 | **CL-01** | L6, L2 | B2 | **R0** | Furnace TU wraps to 2¹²⁸ − 1 on an honest full exit (200 of 200 random traces). Later distributions are stranded; a new depositor realises 29 wei of 1000e18. | PE-c |
| 7 | **K1-F2 / FX-04 / CONC-01** | L2 | B2 / B3 | **R0** (timing R1) | Notify before accrue at three side entries. After quiet periods, notified rewards are destroyed: 660/700 FXN and 70/140 SDT orphaned. During normal operation they are reallocated to later stakers. | PE-c |
| 8 | **FX-14** | L1, L6 | K4 | R2 | DFP magnitude reaches 0 after three liquidations. Later depositors are locked even across epochs, and a denormal snapshot zeroes a 1e24 stake. | PE-c |
| 9 | **FX-02** | L4 (sampled, not anchored), L2 | B5 / B1 / B3 | **R0** (+R1) | While the oracle is invalid, every market action deducts funding again without capturing the snapshot. In the trace, 6.23 base tokens are stranded after 5 tiny mints. | PE-c |
| 10 | **FX-01 / FX-05** | L1, L6 | exit-liveness | **R0** | Shareable vote-sharing: the owner aggregate becomes 0 or ends 1 wei short, and stakers' claim, withdraw or reject divide by zero or underflow forever. | PE-c |
| 11 | **CONC-14** | L2 (O3a-only ⇒ Σδ > 0), L3 | B1 + 𝒫 leak | R3 + R1 | Re-activation of an unregistered reward token re-notifies custody that already backs historical claims. Σ claims = 2 × custody, and the second claimant reverts. | PE-c |
| 12 | **FX-03** | L4 | B3 / ℐ | **R0** (R1 forcing) | Off-by-one history index (L16315 vs L15490). Boost forced to 40%, or uint24 underflow locks exits; forced checkpoints cut the victim's FXN by 59%. | PE-c |
| 13 | **CL-07** | L3, L5 | B1 | R1 + honest R2 | A third-party bribe claim is relocked as "extra", then the keeper's harvest sends users' unlocked CVX to the Furnace. `withdrawUnlocked` reverts. | PE-m |
| 14 | **CL-02** | L1 | B5 / exit-liveness | **R0** (TU = 0) | Paid-off Furnace: AMO `unlock` mints 0 shares (1000e18 absorbed), and `withdraw` divides by zero. | PE-c |
| 15 | **CONC-12** | L5 (time-windowed) | 𝒫 leak | R1 (window) | `initializeV2` front-run: the attacker becomes the stash and the wrapper reward receiver, and the owner's initialization reverts. | PE-c |
| 16 | **FX-16** | L3 (stale valuation) | B5 | Rv | Wrapped-token rate drop while CR still reads 2.0. xToken exits at full value, and 600k fToken become unredeemable. | PE-c |

The complete per-subsystem tables are §9 of `02`, `03` and `04`, plus §K of `01`.

### 3.3 Bridge × subsystem matrix (aggregated)

| | B1 backing | B2 lazy–eager | B3 schedule | B4 policy | B5 gluing | Atomicity | Exit-liveness |
|---|---|---|---|---|---|---|---|
| Kernel | K2-F1 (latent), K2-F2 | **K1-F2**; polarity law (L2) | K1-I3 band, K1-I2 | — | — | ✓ (proved) | K2-F1 |
| Concentrator | **CONC-02, 09, 10, 14**, 06, 13 | **CONC-01**, 07 | **CONC-08**, 01β2 | CONC-15 (R4), harvester-conditional rank | ✓ (aCRV / aFXS gluing holds) | ✓ (AT-1 proved) | CONC-02, 03, 04, 06, 14 |
| CLever | **CL-07**, 08, 03, 04 | **CL-01**, 16, 12 | **CL-06**, 09, 10, 13, 17, 18 | CL-21–23 | **CL-02**, CL-06 propagation | CL-11, 15 (MEV) | **CL-06**, 02, 03, 04, 14, 16, 17 |
| f(x) | FX-02 (stranded), FX-16 | **FX-13, 14**, 06 | **FX-03, 04**, 09, 11, 12 | FX-20 | **FX-01, 02, 05, 16** | FX-18 (PL) | **FX-01, 03b, 05, 07, 08, 14** |

---

## 4. Consolidated proofs of absence (what holds)

- **K3 solvency.** Under O3a–O3c, `Σ (claimed + α) ≤ Σ notified`, with quantized polarity ≤ 0 (`01` K3-T1).
- **K1 mass conservation.** Exact, given Pre1 (`01` K1-I1). Pre1 is discharged by `depositReward`.
- **K2.** Re-registration is safe; the transfer-first yield point in `depositReward` is not an atomicity gap.
- **Concentrator.**
  - Gauge-wrapper O3a and O3b are discharged by lock coverage.
  - Per-pool B2 in the Convex vaults is exact.
  - aCRV / aFXS gluing (B5) holds.
  - No Y^U atomicity gap.
  - The stash cells are single-pool.
  - K5 and K6 are discharged.
- **CLever.**
  - The Furnace flow property is exact.
  - CII holds for Furnace deposit and withdraw.
  - clevCVX custody equals TU + TR.
  - AMOMath agrees with the Curve plain pool to within 1 wei.
  - The locker accumulator has polarity ≤ 0.
  - No R1-reachable reentrancy, despite the absence of guards.
- **f(x).**
  - Single-action value partition: 0 dilutions in 200 000 cases.
  - Stability guards hold within a single action.
  - Mode transitions are not poke-steerable.
  - EMA flow holds to ≤ 87 wei.
  - Pool fToken custody is exact.
  - K4 O4a holds.
  - No reentrancy in the market.

---

## 5. Deployment facts that decide reachability (consolidated)

| Fact | Decides | Source doc |
|---|---|---|
| Convex `BaseRewardPool.getReward(account, bool)` and `stakeFor` are permissionless | R1 push for CONC-02 / 09 / 10 | 02 |
| `harvester` value in each compounder and vault | R1 vs R2 for harvest-dependent items (L5) | 02, 03 |
| asdCRV `periodLength` and withdraw fee | CONC-04, 06, 08 | 02 |
| Furnace `periodLength` and harvest cadence relative to P | CL-06, 09 (P > 0) vs CL-10 (P = 0) | 03 |
| Keeper schedule for Convex epochs 2970–2975 (2026-12-03 … 2027-01-07) | CL-18 | 03 |
| MetaFurnace base decimals, P, strategy | CL-03, 04 | 03 |
| Whether Boostable pools are live; FXN emission per pool vs 6 277·S | FX-03, 08, 09 | 04 |
| Frequency of `isValid = false` on funding-cost markets | FX-02 | 04 |
| Liquidator `maxAmount` policy | FX-13, 14 | 04 |
| Splitter → pool `depositReward` path | rank of K1-I3 in f(x) | 01, 04 |

---

## 6. Method, reproducibility, limitations

**Method.**

1. State is stratified by write authority and evolution (𝒞 / ℒ / ℐ / 𝒯 / 𝒫). The 𝒫 boundary is *computed* (`atlas/A5`), which is how the two policy leaks (CONC-12, CONC-14) were found.
2. Invariants are organised by bridge.
3. Kernels are analysed once, as assume-guarantee contracts. Instantiations are checked by obligation discharge, which is how the three Pre1 violations were found.
4. Every arithmetic counterexample is executed: on compiled bytecode where possible, otherwise on an exact-integer model.

**Reproduce.** See `harness/README.md`:

```sh
npm install && npm run setup && npx hardhat compile
npx hardhat run scripts/<kernel|concentrator|clever|fx>/<trace>.js
```

**Limitations.**

- External venue behaviour is assumed; each such assumption is tagged.
- Model-only items (PE-m) were not replayed on bytecode.
- The atlas over-approximates paths (branches are concatenated) and is intra-contract.
- No deployment state was read. All ranks are stated relative to the assumption ledgers.

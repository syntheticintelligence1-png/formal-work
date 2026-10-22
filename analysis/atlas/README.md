# Mechanized SBD atlas

This atlas is generated from solc ASTs. It is not hand-written.

```sh
cd harness
python3 -I tools/footprint.py ../analysis/atlas/footprint.json artifacts/build-info/*.json
python3 -I tools/atlas.py ../analysis/atlas/footprint.json ../gigabundle.txt ../analysis/atlas
```

## How it is built

`footprint.py` walks every external/public entry function of every concrete bundle contract (19 contracts, 560 entry functions, 377 of them mutating). It inlines:

- modifiers;
- internal, library and `super` calls, resolved through the C3 linearization;
- local `storage` aliases and library `storage` parameters.

The output is an ordered event trace of storage reads and writes, `block.timestamp` samples, external calls (each tagged with a callee class), `balanceOf(address(this))` reads, and sender-gating evidence.

| File | Content |
|---|---|
| `A1-action-census.md` | Per-contract census of open, conditional, gated and initializer actions, with counts of clock samples, yield points, post-yield writes and locks |
| `A2-poke-graph.md` | Open actions that sample the clock, and the storage they write in clock-sampling frames. Every B3 operator's schedule is controlled from these rows. |
| `A3-bdr-sites.md` | All 75 balance-differential-read sites. Each site reachable from an open action carries a B1 verdict (D/A/V/C). |
| `A4-yield-segmentation.md` | Storage writes after non-fixed external calls (atomicity lens) |
| `A5-write-authority.md` | The 𝒫 / dynamic boundary, computed from write authority. Policy-like variables written by unprivileged actions are *policy leaks*. |
| `footprint.json` | The full event traces, for re-analysis |

## Findings that come from the atlas itself

- **K1-F2** (`01-kernel.md`). A3 rows L15265/L15267 and L16302/L16304 lead to the FXN gauge-mint notify. That notify precedes accrual, so the K1 precondition is violated. Consequence: reward mass is destroyed or reallocated. Proven-executed.
- **Policy leak: `SdCrvCompounder.stash`** (A5). `initializeV2` (L1318) is guarded only by `stash == 0`. The first caller after the upgrade chooses the stash, and `_updateStash` (L1561–L1569) redirects the compounder's wrapper reward receiver to that address. Proven-executed: `harness/scripts/concentrator/initv2_race.js`.
  - Rank: R1 during the window between the upgrade and initialization.
  - Repair: the owner can call `updateStash`; this is an R4 operation.
- **Cross-pool absorption in both Convex vaults** (A3 rows L11212, L12289, L12300, and the ETH balance at L12283). `harvest(_pid)` attributes *absolute* vault balances to one pool. The Convex `getReward(account, …)` that pushes another pool's rewards is callable by anyone. Effective rank: an R1 push composed with an honest R1/R2 harvest.
- **Conditional gate `ensureCallerIsHarvester`** (L862–L866), used by five harvest actions. The rank of every harvest-dependent counterexample depends on a policy variable: R1 when `harvester == 0`, R2 otherwise.
- **Cross-contract sampling.** MarketV2 has no clock samples of its own (A1). Its open mint and redeem actions reach the treasury's role-gated entry points, which sample the clock (EMA, funding cost). The treasury's sampling schedule is therefore R1-controlled through the market.

## Limitations

- Branches are concatenated: presence is over-approximated, absence is exact.
- Loops are walked once.
- Analysis is intra-contract: an external call is a yield point and is not inlined.
- Calls through function-typed values are not followed.

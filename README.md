# formal-work: SBD analysis of `gigabundle.txt`

This repository holds a transition-system and refinement analysis of `gigabundle.txt`. The bundle contains the AladdinDAO Concentrator, CLever and f(x) Solidity sources: 106 files, 17 881 lines. The analysis uses the **Stratified Bridge Decomposition (SBD)**, and every arithmetic counterexample was executed on the compiled, unmodified sources.

## Start here

| Document | Content |
|---|---|
| [`analysis/05-synthesis.md`](analysis/05-synthesis.md) | Global transition system, the **six cross-subsystem laws**, consolidated findings, and the bridge × subsystem matrix |
| [`analysis/00-sbd-framework.md`](analysis/00-sbd-framework.md) | The decomposition: strata 𝒞/ℒ/ℐ/𝒯/𝒫, bridges B1–B5, yield-point atomicity, adversary ranks, assumption tags, kernel obligations |
| [`analysis/01-kernel.md`](analysis/01-kernel.md) | Assume-guarantee analysis of the shared reward kernels: LinearReward, the distributor, both accumulators, WordCodec, FeeCustomization |
| [`analysis/02-concentrator.md`](analysis/02-concentrator.md) | Concentrator: compounders, StakeDAO gauge wrapper, stashes, Convex vaults (CONC-01…19) |
| [`analysis/03-clever.md`](analysis/03-clever.md) | CLever: Furnace, MetaFurnace, AMO, CVX locker (CL-01…26) |
| [`analysis/04-fx.md`](analysis/04-fx.md) | f(x): markets, treasuries, rebalance pools, kernel K4 (FX-01…20) |
| [`analysis/atlas/`](analysis/atlas/) | Mechanized atlas computed from solc ASTs: action census, poke graph, balance-read sites with B1 verdicts, yield-point segmentation, write-authority strata |
| [`harness/`](harness/) | Hardhat project that compiles the bundle unmodified (solc 0.7.6 / 0.8.20, OZ 3.4.2 / 4.9.6) and replays every bytecode trace |

## Reproduce

```sh
cd harness
npm install && npm run setup && npx hardhat compile
npx hardhat run scripts/kernel/k3_conservation_and_O3a.js      # any trace under scripts/{kernel,concentrator,clever,fx}/
python3 -I tools/footprint.py ../analysis/atlas/footprint.json artifacts/build-info/*.json   # regenerate atlas input
python3 -I tools/atlas.py ../analysis/atlas/footprint.json ../gigabundle.txt ../analysis/atlas
```

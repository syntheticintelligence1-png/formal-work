# SBD executable harness

This harness compiles the **unmodified** sources of `../gigabundle.txt` and replays the counterexample traces cited in `../analysis/`.

- **Compilers:** solc 0.7.6 and 0.8.20, optimizer at 200 runs.
- **OpenZeppelin versions:** 3.4.2 (`@openzeppelin/contracts{,-upgradeable}`) and 4.9.6 (`@openzeppelin/contracts{,-upgradeable}-v4`), installed as npm aliases.

## Setup

```sh
npm install
npm run setup                 # extracts the 106 bundle files into contracts/bundle/ (tools/extract.py)
npx hardhat compile           # 151 compilation units: the bundle, OpenZeppelin and the harness
```

## Running a trace

```sh
npx hardhat run scripts/kernel/k2_periodzero_trap.js
```

Each script prints its trace as rows of `(action) | state projection`.

## Layout

| Path | Content |
|---|---|
| `contracts/bundle/` | Generated: the bundle files, extracted verbatim |
| `contracts/harness/` | Minimal instantiations and mocks used by the traces |
| `scripts/kernel/` | K1–K3 kernel traces (`analysis/01-kernel.md`) |
| `scripts/<subsystem>/` | Subsystem traces (`analysis/02-…`, `03-…`, `04-…`), where they exist |
| `tools/extract.py` | Bundle → source tree. It splits on the `FILE: <path> (<n> lines)` headers. |

"""Render the mechanized SBD atlas (analysis/atlas/*.md) from footprint.json (tools/footprint.py)."""

import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from bundlemap import header_lines, to_bundle  # noqa: E402

RANK = {"Y0": 0, "self": 0, "YP": 1, "Yext": 2, "?": 3, "YU": 4}

# Manual B1 verdicts for every balance-read site reachable from an open (or harvester-conditional) action.
# Kinds: D = differential around a call; A = absolute amount; V = valuation (enters a price/total); C = cap/sourcing.
BDR_VERDICTS = {
    694: ("A", "New gauge reward token: whole balance notified as reward. Donations become rewards (benign). Aliasing would need reward token == a principal token held here; the wrapper forwards principal to the locker [C]."),
    1423: ("D", "Before-snapshot for the claim window at L1426–L1427. Tokens outside `getActiveRewardTokens()` are not counted (see 02-concentrator)."),
    1430: ("D", "After-read of the same window."),
    4461: ("V", "`totalCVXInPool`: custody enters the realisation price. Donations are absorbed into pending distribution (see 03-clever)."),
    4463: ("V", "Same valuation: staked CVX part."),
    4781: ("C", "Liquidity sourcing: withdraw the shortfall from the reward pool. Safe."),
    5079: ("V", "`totalBaseTokenInPool` uses SafeMath `.sub(_leftover)`. Reverts when leftover > balance (exit-liveness, 03-clever T07)."),
    5386: ("C", "Liquidity sourcing from the strategy. Safe."),
    7324: ("C", "`min(balance, baseOut)` cap after treasury redeem. Can only reduce the payout. Safe."),
    7374: ("C", "Same cap for xToken redeem."),
    9099: ("D", "Furnace claim window. Safe."),
    9101: ("D", "Furnace claim window. Safe."),
    9122: ("D", "Strategy-harvest window (Y^𝒫 strategy). Safe if the strategy is honest [R4]."),
    9130: ("D", "Same window: rewardPerShare += Δ/totalSupply."),
    9538: ("V", "`harvestable = balance − wrapped(totalBaseToken)`. A donation becomes distributable reward, giving an R1 reward-injection capability (feeds the K1 schedule, 01-kernel K1-I3)."),
    10399: ("V", "`totalUnderlying` = staking balance. `stakeFor(aCRV)` donation inflates the share price, enabling first-depositor inflation (02-concentrator)."),
    10434: ("D", "Transfer-in measurement (fee-on-transfer tolerant). Safe."),
    10436: ("D", "Same."),
    10453: ("D", "Same (CRV)."),
    10455: ("D", "Same (CRV)."),
    10609: ("A", "Last withdrawer receives the whole cvxCRV balance (by design; absorbs donations)."),
    10656: ("A", "Harvest sweeps the whole CVX balance."),
    10658: ("A", "Harvest sweeps the whole 3CRV balance."),
    10662: ("A", "Harvest sweeps the whole CRV balance."),
    10665: ("A", "Harvest output = whole cvxCRV balance."),
    11105: ("D", "LP transfer-in measurement. Safe."),
    11107: ("D", "Same."),
    11212: ("A", "**Cross-pool absorption.** Absolute reward-token balances are attributed to pool `_pid` after `getReward` for that pool only. Any account can push another pool's Convex rewards into the vault first (`getReward(vault, true)` is permissionless on Convex) [B1, R1]."),
    11997: ("D", "LP transfer-in measurement. Safe."),
    11999: ("D", "Same."),
    12062: ("D", "Zap-and-deposit LP measurement."),
    12064: ("D", "Same."),
    12208: ("D", "Withdraw-and-zap output measurement."),
    12210: ("D", "Same."),
    12289: ("A", "**Cross-pool absorption** in AladdinCRVConvexVault.harvest: absolute reward-token balances. L12283 also takes the vault's whole ETH balance [B1, R1 push + R1/R2 harvest]."),
    12300: ("A", "Absolute CRV balance attributed to `_pid`."),
    12586: ("D", "CRV→cvxCRV swap measurement."),
    12594: ("D", "Same."),
    13388: ("C", "Liquidity sourcing from the CVX reward pool. Safe."),
    13487: ("D", "Locker/reward-pool getReward window. Safe."),
    13497: ("D", "Same."),
    14079: ("V", "Stake-percentage rebalancing; no claim depends on it. Safe."),
    14080: ("V", "Same."),
    15265: ("D", "FXN gauge-mint window. The measurement is safe, but the subsequent `_notifyReward` at L15269 precedes accrual: **K1-Pre1 violated** (01-kernel K1-F2)."),
    15267: ("D", "Same."),
    16302: ("D", "FXN gauge-mint window. `_notifyReward` at L16306 precedes accrual at L16309: **K1-Pre1 violated** (01-kernel K1-F2)."),
    16304: ("D", "Same."),
    17188: ("D", "Funding-cost harvest window; the bounty goes to the platform. Safe."),
    17190: ("D", "Same."),
}


def load(path):
    rows = json.load(open(path))
    return rows


def clock_coupled_writes(events):
    """Writes performed in a call frame that also samples block.timestamp."""
    frames = defaultdict(lambda: {"T": False, "W": set()})
    for e in events:
        path = tuple(e[-1])
        if e[0] == "T":
            frames[path]["T"] = True
        elif e[0] == "W" and not e[1].endswith("._status"):
            frames[path]["W"].add(e[1])
    out = set()
    for f in frames.values():
        if f["T"]:
            out |= f["W"]
    return sorted(out)


def md_escape(s):
    return str(s).replace("|", "\\|")


def main(footprint, bundle, outdir):
    rows = load(footprint)
    hdrs = header_lines(bundle)
    os.makedirs(outdir, exist_ok=True)
    mut = [r for r in rows if r["mutability"] not in ("view", "pure")]

    def bl(r):
        return to_bundle(f"{r['file']}:{r['line']}", hdrs)

    # ---------------------------------------------------------------- census
    by_c = defaultdict(list)
    for r in mut:
        by_c[r["contract"]].append(r)
    lines = [
        "# Atlas 1 — Action census (mechanized)",
        "",
        "Source: `harness/tools/footprint.py`, which walks solc ASTs from the Hardhat build-info. It covers every external or public **mutating** entry function of every concrete bundle contract, with inherited functions resolved through the contract's C3 linearization.",
        "",
        "## Column definitions",
        "",
        "| Column | Meaning |",
        "|---|---|",
        "| `open` | No sender gate on any path |",
        "| `cond` | Gated only when `harvester ≠ 0`, via `ensureCallerIsHarvester` (L862). With the harvester unset, the action is effectively `open`. |",
        "| `gated` | A modifier or body compares the sender with storage, or performs a role check |",
        "| `clock` | Samples `block.timestamp` |",
        "| `yield` | Has at least one non-static external call |",
        "| `W-after-Y⁺` | Writes storage after a yield point whose callee is policy-, user- or externally-derived (YP, YU, Yext, ?) |",
        "",
        "| Contract | Mutating actions | open | cond | gated | init | clock | yield | W-after-Y⁺ | locked (`nonReentrant`) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    tot = Counter()
    for c in sorted(by_c):
        rs = by_c[c]
        acc = Counter(r["summary"]["access"].split("[")[0] for r in rs)
        clock = sum(1 for r in rs if r["summary"]["clock"])
        yld = sum(1 for r in rs if r["summary"]["n_yield"] > 0)
        wy = sum(1 for r in rs if any(RANK.get(p[0], 3) >= 1 for p in r["summary"]["post_yield_writes"]))
        lk = sum(1 for r in rs if r["summary"]["locks"])
        lines.append(f"| {c} | {len(rs)} | {acc['open']} | {acc['cond']} | {acc['gated']} | {acc['init']} | {clock} | {yld} | {wy} | {lk} |")
        for k, v in (("n", len(rs)), ("open", acc["open"]), ("cond", acc["cond"]), ("gated", acc["gated"]), ("init", acc["init"]), ("clock", clock), ("yield", yld), ("wy", wy), ("lk", lk)):
            tot[k] += v
    lines.append(f"| **Σ** | **{tot['n']}** | **{tot['open']}** | **{tot['cond']}** | **{tot['gated']}** | **{tot['init']}** | **{tot['clock']}** | **{tot['yield']}** | **{tot['wy']}** | **{tot['lk']}** |")
    lines += [
        "",
        "## Approximations",
        "",
        "- Branches are concatenated, so every reported write and call is *possible* on some path. Absence is exact; presence is an over-approximation.",
        "- Loops are walked once.",
        "- Calls through function-typed values are not followed.",
        "- Sender gating is detected from evidence: `msg.sender`/`_msgSender()` compared with storage, a bool storage mapping indexed by sender, or `hasRole`/`_checkRole`/`_checkOwner`.",
    ]
    open(os.path.join(outdir, "A1-action-census.md"), "w").write("\n".join(lines) + "\n")

    # ---------------------------------------------------------------- poke graph
    lines = [
        "# Atlas 2 — Poke graph: who controls the clock samples",
        "",
        "Each row is an `open` or `cond` mutating action that samples `block.timestamp`, together with the storage written *in a frame that samples the clock* (clock-coupled writes). These are the sampling points of the B3 operators U_Δ.",
        "",
        "Every row is an R1 schedule-control capability, or R1/R2 for `cond` rows. Any B3 or CII defect in a clock-coupled variable listed here therefore has minimal rank R1.",
        "",
        "| Contract | Action | Access | Bundle line | Clock-coupled writes |",
        "|---|---|---|---|---|",
    ]
    for r in sorted(mut, key=lambda r: (r["contract"], r["function"])):
        s = r["summary"]
        if s["access"] not in ("open", "cond[harvester]") or not s["clock"]:
            continue
        cw = clock_coupled_writes(r["events"])
        if not cw:
            continue
        lines.append(f"| {r['contract']} | `{r['function']}` | {s['access']} | L{bl(r)} | {', '.join('`' + w + '`' for w in cw)} |")
    open(os.path.join(outdir, "A2-poke-graph.md"), "w").write("\n".join(lines) + "\n")

    # ---------------------------------------------------------------- BDR atlas
    sites = {}
    for r in mut:
        for e in r["events"]:
            if e[0] == "B":
                L = to_bundle(e[3], hdrs)
                d = sites.setdefault(L, {"tokens": set(), "via": set(), "open": False})
                d["tokens"].add(e[1])
                d["via"].add(f"{r['contract']}.{r['function']}")
                if r["summary"]["access"] in ("open", "cond[harvester]"):
                    d["open"] = True
    lines = [
        "# Atlas 3 — Balance-differential reads (B1 sites)",
        "",
        "Each row is a `balanceOf(address(this))` read reachable from a mutating entry function. Kinds:",
        "",
        "- **D** (differential): before/after a call.",
        "- **A** (absolute): the whole balance is taken as an amount.",
        "- **V** (valuation): the balance enters a price or total.",
        "- **C** (cap/sourcing): the balance only bounds or sources a payout.",
        "",
        "B1 hazard rule: an **A** or **V** read on a custody cell that backs two or more logical pools (|κ⁻¹(c)| ≥ 2), reachable at rank R, is an aliasing-absorption counterexample at rank R.",
        "",
        f"Mechanically found sites: **{len(sites)}**. Sites reachable from open or `cond` actions: **{sum(1 for d in sites.values() if d['open'])}**. Each of these carries a manual verdict.",
        "",
        "| Bundle line | Reach | Kind | Token(s) | Reached from | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for L in sorted(sites):
        d = sites[L]
        kind, verdict = BDR_VERDICTS.get(L, ("—", "gated-only site (R2+/R4); see subsystem report") if not d["open"] else ("?", "unclassified"))
        via = sorted(d["via"])
        via_s = ", ".join(via[:3]) + (f" (+{len(via) - 3})" if len(via) > 3 else "")
        lines.append(f"| L{L} | {'open' if d['open'] else 'gated'} | {kind} | {md_escape(', '.join(sorted(d['tokens'])))} | {md_escape(via_s)} | {md_escape(verdict)} |")
    open(os.path.join(outdir, "A3-bdr-sites.md"), "w").write("\n".join(lines) + "\n")

    # ---------------------------------------------------------------- yield segmentation
    lines = [
        "# Atlas 4 — Yield-point segmentation (atomicity lens)",
        "",
        "Each row is a mutating action that writes storage **after** a non-static external call whose callee is not a fixed venue (YP = address from policy storage, Yext = address returned by another call, YU = user-supplied, ? = computed).",
        "",
        "The *worst callee class* is the least trusted callee preceding the write. `lock` shows whether a `nonReentrant` guard covers the action. A guard blocks write-reentrancy into the same lock domain only; it does not block cross-contract reentrancy or read-only reentrancy.",
        "",
        "| Contract | Action | Access | Lock | Worst callee class → writes after it |",
        "|---|---|---|---|---|",
    ]
    for r in sorted(mut, key=lambda r: (r["contract"], r["function"])):
        s = r["summary"]
        pw = [p for p in s["post_yield_writes"] if RANK.get(p[0], 3) >= 1]
        if not pw:
            continue
        grp = defaultdict(list)
        for cls, w in pw:
            grp[cls].append(w.split(".", 1)[1])
        desc = "; ".join(f"{cls} → {', '.join(sorted(set(v))[:6])}{' …' if len(set(v)) > 6 else ''}" for cls, v in sorted(grp.items(), key=lambda kv: -RANK.get(kv[0], 3)))
        lines.append(f"| {r['contract']} | `{r['function']}` | {s['access']} | {'Y' if s['locks'] else 'N'} | {md_escape(desc)} |")
    open(os.path.join(outdir, "A4-yield-segmentation.md"), "w").write("\n".join(lines) + "\n")

    # ---------------------------------------------------------------- write-authority strata
    writers = defaultdict(lambda: {"open": set(), "gated": set(), "init": set()})
    for r in mut:
        a = r["summary"]["access"]
        cls = "init" if a == "init" else ("gated" if a.startswith("gated") else "open")
        for w in r["summary"]["writes"]:
            if w.endswith("._status"):
                continue
            writers[w][cls].add(f"{r['contract']}.{r['function']}")
    pol = sorted(v for v, d in writers.items() if not d["open"])
    dyn = sorted(v for v, d in writers.items() if d["open"])
    lines = [
        "# Atlas 5 — Write-authority partition of storage (mechanized strata boundary)",
        "",
        "SBD defines the policy stratum 𝒫 by write authority. A storage variable is in 𝒫 iff **no** open or `cond` action writes it, i.e. it is written only by gated actions or initializers. All other variables are dynamic (𝒞-shadow / ℒ / ℐ / 𝒯).",
        "",
        "Constants and immutables (𝒫₀) never appear because they are never written.",
        "",
        "This partition is computed, not asserted. A variable that the specification treats as policy but that appears in the dynamic column is a **policy leak**: an unprivileged path writes a policy-like variable.",
        "",
        f"## 𝒫 — written only by gated or initializer actions ({len(pol)})",
        "",
        ", ".join(f"`{v}`" for v in pol),
        "",
        f"## Dynamic — written by at least one open or `cond` action ({len(dyn)})",
        "",
        "| Variable | Open writers (sample) | Gated writers (sample) |",
        "|---|---|---|",
    ]
    for v in dyn:
        d = writers[v]
        ow = sorted(d["open"])
        gw = sorted(d["gated"])
        lines.append(f"| `{v}` | {md_escape(', '.join(ow[:3]))}{' …' if len(ow) > 3 else ''} | {md_escape(', '.join(gw[:2]))}{' …' if len(gw) > 2 else ''} |")
    open(os.path.join(outdir, "A5-write-authority.md"), "w").write("\n".join(lines) + "\n")
    print("atlas written to", outdir)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])

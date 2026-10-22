"""T14  AMO conversion with zero slippage bounds (Atomicity / Rv+R1).

CLeverAMOBase.checkpoint() is permissionless (L8679-L8681) and _checkpoint converts all base
claimed from the Furnace plus pendingBaseToken (L8772-L8786) through
add_liquidity(amounts, 0) and exchange(..., 0, ...) (L9057-L9064): no minimum outputs.
The split is computed from the *current* pool balances (L9153-L9157), so a front-run moves it.
Attacker: front-run swap CVX->clevCVX, call checkpoint(), back-run swap clevCVX->CVX.
"""
import os, sys, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amo_model as M

E18 = 10**18
LP_AMO, DEBT_AMO = 60_000 * E18, 50_000 * E18

def amo_convert(pool, B):
    add = M.searchSplit(pool, B, LP_AMO, DEBT_AMO)
    lp = pool.add_liquidity([add, 0], 0)
    debt = pool.exchange(0, 1, B - add, 0)
    return lp, debt

def value_in_cvx(pool, lp, debt):
    # value LP by the CVX it would redeem at the *undisturbed* virtual price, debt at 1 CVX (Furnace face value)
    vp = pool.get_D(pool.balances) * E18 // pool.totalSupply
    return lp * vp // E18 + debt

base_pool = M.CurvePlain2(1_000_000 * E18, 1_200_000 * E18, A=100)
B = 5_000 * E18
ref = copy.deepcopy(base_pool)
lp0, d0 = amo_convert(ref, B)
v0 = value_in_cvx(copy.deepcopy(base_pool), lp0, d0)
print("no sandwich: AMO gets lp=%d debt=%d  value=%.4f CVX" % (lp0, d0, v0 / E18))
for X in (20_000, 100_000, 300_000):
    p = copy.deepcopy(base_pool)
    got = p.exchange(0, 1, X * E18, 0)          # attacker front-run CVX -> clevCVX
    lp1, d1 = amo_convert(p, B)                 # attacker calls AMO.checkpoint()
    back = p.exchange(1, 0, got, 0)             # attacker back-run clevCVX -> CVX
    v1 = value_in_cvx(copy.deepcopy(base_pool), lp1, d1)
    print("front-run %7d CVX: AMO lp=%d debt=%d value=%.4f CVX (loss %.4f CVX) | attacker P&L %+.4f CVX" % (
        X, lp1, d1, v1 / E18, (v0 - v1) / E18, (back - X * E18) / E18))

print()
print("scan: max attacker P&L over front-run size X (both directions), various A, B, pool imbalance")
best_overall = None
for A in (5, 10, 50, 100, 400):
    for B in (5_000, 50_000, 200_000):
        for (b0, b1) in ((1_000_000, 1_200_000), (1_000_000, 3_000_000), (300_000, 300_000)):
            best = None
            for direction in ("buy_debt", "sell_debt"):
                for X in (1_000, 5_000, 20_000, 50_000, 100_000, 250_000):
                    p = M.CurvePlain2(b0 * E18, b1 * E18, A=A)
                    try:
                        if direction == "buy_debt":
                            got = p.exchange(0, 1, X * E18, 0)
                            amo_convert(p, B * E18)
                            pnl = p.exchange(1, 0, got, 0) - X * E18
                        else:
                            got = p.exchange(1, 0, X * E18, 0)
                            amo_convert(p, B * E18)
                            pnl = p.exchange(0, 1, got, 0) - X * E18   # P&L in clevCVX units
                    except Exception as e:
                        continue
                    if best is None or pnl > best[0]:
                        best = (pnl, direction, X)
            if best_overall is None or best[0] > best_overall[0]:
                best_overall = (best[0], A, B, b0, b1, best[1], best[2])
print("  best (P&L wei, A, B, pool0, pool1, direction, X):", best_overall, " = %.4f tokens" % (best_overall[0] / E18))

print()
print("threshold scan (pool 1,000,000 CVX / 1,200,000 clevCVX): max attacker P&L (CVX) by B and A")
Xs = [2_000 * k for k in range(1, 151, 6)]
print("  %8s" % "B\\A" + "".join("%14d" % A for A in (10, 50, 100, 200)))
for B in (5_000, 20_000, 50_000, 100_000, 200_000):
    row = []
    for A in (10, 50, 100, 200):
        best = -10**40
        for X in Xs:
            p = M.CurvePlain2(1_000_000 * E18, 1_200_000 * E18, A=A)
            got = p.exchange(0, 1, X * E18, 0)
            amo_convert(p, B * E18)
            best = max(best, p.exchange(1, 0, got, 0) - X * E18)
        row.append(best / E18)
    print("  %8d" % B + "".join("%14.2f" % v for v in row))

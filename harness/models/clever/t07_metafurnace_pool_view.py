"""T07  MetaFurnace.totalBaseTokenInPool (L5070-L5085) defects.

(a) ordering: balanceOf(this).sub(_leftover) is evaluated BEFORE the strategy balance is
    added (L5079-L5083).  _claim pays from the contract balance first (L5386-L5395), so a
    claim can push the contract balance below the leftover although contract+strategy >=
    leftover.  Then _deposit (L5334) and _distribute (L5436) revert until leftover decays.
    (Furnace.totalCVXInPool does add-then-sub, L4460-L4464.)
(b) units: _distribute scales the amount to debt units (L5411-L5412) before computing
    ratePerSecond (L5420/L5424); totalBaseTokenInPool multiplies that debt-unit rate by the
    remaining time and subtracts it from a base-unit balance (L5075, L5079).  For base tokens
    with decimals < 18 (admitted by initialize, L5037) the subtraction underflows.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import atomic
from furnace_model import MetaFurnace, MockYieldStrategy

DAY = 86400
P = 7 * DAY
E18 = 10**18

def run(label, F, fn, *a):
    r = atomic(F, fn, *a)
    print("  %-60s -> %s" % (label, r))
    return r

def pool_view(F):
    try:
        return F.totalBaseTokenInPool()
    except Exception as e:
        return "REVERT(%s)" % e

print("=== T07a: 18-decimal base, P=7d, strategy percentage = 100%% ===")
S = MockYieldStrategy()
F = MetaFurnace(baseDecimals=18, periodLength=P, percentage=10**5, threshold=0, strategy=S)
run("alice.deposit(debt 1000e18)", F, F.deposit, "alice", 1000 * E18)
F.base += 700 * E18
run("distributor: transfer 700e18 base + distribute(700e18)", F, F.distribute, "d", 700 * E18)
F.now += 8 * DAY
run("poke after period 1", F, F.updatePendingDistribution)
F.base += 700 * E18
run("distributor: transfer 700e18 base + distribute(700e18)", F, F.distribute, "d", 700 * E18)
print("  state:", F.snap("alice"))
print("  totalBaseTokenInPool() =", pool_view(F))
run("alice.claim()  (realised from period 1, ~700e18)", F, F.claim, "alice")
print("  state:", F.snap("alice"))
print("  contract+strategy = %d  >= leftover = %d ; view = %s" % (F.base + S.underlying, F.leftover(), pool_view(F)))
run("bob.deposit(debt 10e18)", F, F.deposit, "bob", 10 * E18)
F.base += 50 * E18
run("distributor: transfer 50e18 + distribute(50e18)", F, F.distribute, "d", 50 * E18)
F.now += 6 * DAY + 23 * 3600
run("bob.deposit(debt 10e18) @ +6d23h", F, F.deposit, "bob", 10 * E18)
F.now += 3600
run("bob.deposit(debt 10e18) @ +7d (leftover 0)", F, F.deposit, "bob", 10 * E18)

print()
print("=== T07b: 6-decimal base (e.g. USDC-like), P=7d, no strategy ===")
G = MetaFurnace(baseDecimals=6, periodLength=P)
run("alice.deposit(debt 1000e18)", G, G.deposit, "alice", 1000 * E18)
G.base += 700 * 10**6
run("distributor: transfer 700e6 base + distribute(700e6)", G, G.distribute, "d", 700 * 10**6)
print("  rate (debt units/s) = %d ; leftover = %d (debt units) vs base balance = %d (base units)" % (G.rate, G.leftover(), G.base))
G.now += DAY
run("bob.deposit(debt 10e18) during period", G, G.deposit, "bob", 10 * E18)
run("alice.claim() during period (claim path has no view)", G, G.claim, "alice")
G.now += 7 * DAY
run("bob.deposit(debt 10e18) after finishAt", G, G.deposit, "bob", 10 * E18)

print()
print("=== T07c: 6-decimal base, P=7d, WITH strategy (percentage 50%) ===")
S2 = MockYieldStrategy()
H = MetaFurnace(baseDecimals=6, periodLength=P, percentage=50_000, strategy=S2)
run("alice.deposit(debt 1000e18)", H, H.deposit, "alice", 1000 * E18)
H.base += 700 * 10**6
run("distributor: transfer 700e6 + distribute(700e6)", H, H.distribute, "d", 700 * 10**6)
print("  => every distribute/harvest reverts while P>0: the stake step (L5436) reads the view")

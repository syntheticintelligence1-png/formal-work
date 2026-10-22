"""T01  Furnace rate-0 freeze (B3 / exit-liveness).

Claim: with periodLength P>0, a distribute of 0 < a < P made at now >= finishAt sets
ratePerSecond = a // P = 0 (L4806) and lastUpdate = now (L4813).  Every later
_updatePendingDistribution with dur>0 calls _reduceGlobalDebt(dur*0 = 0) (L4684); if
totalUnrealised>0 the else-branch computes _toU128((TU-0)*2^128/TU) = _toU128(2^128) which
reverts (L4854, L4861).  All user entry points call it first (L4498, L4505, L4513, L4521,
L4729, L4798) -> all revert.  CLeverCVXLocker.donate (L13471, permissionless) forwards any
amount >= 1 to Furnace.distribute (L14076).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import atomic
from furnace_model import Furnace

DAY = 86400
P = 7 * DAY
E18 = 10**18

def run(label, F, fn, *a):
    r = atomic(F, fn, *a)
    print("  %-58s -> %s" % (label, r))
    return r

print("=== T01a: freeze via 1-wei distribute after finishAt (P = 7 days) ===")
F = Furnace(periodLength=P)
t0 = F.now
run("alice.deposit(1000e18)", F, F.deposit, "alice", 1000 * E18)
run("bob.deposit(500e18)", F, F.deposit, "bob", 500 * E18)
run("locker harvest -> distribute(100e18)", F, F.distribute, "locker", 100 * E18)
print("  state:", F.snap("alice", "bob"))
F.now = t0 + 3 * DAY
run("poke updatePendingDistribution() @t0+3d", F, F.updatePendingDistribution)
F.now = t0 + 8 * DAY  # finishAt = t0+7d has passed, no new distribution yet
print("  @t0+8d (> finishAt=%d): state:" % F.finishAt, F.snap())
run("R1: locker.donate(1) -> distribute(1)", F, F.distribute, "locker", 1)
print("  after donate(1):", F.snap())
F.now += 12
for lbl, fn, args in [("alice.withdrawAll()", F.withdrawAll, ("alice",)),
                      ("alice.claim()", F.claim, ("alice",)),
                      ("bob.exit()", F.exit, ("bob",)),
                      ("carol.deposit(10e18)", F.deposit, ("carol", 10 * E18)),
                      ("locker harvest -> distribute(100e18)", F.distribute, ("locker", 100 * E18)),
                      ("updatePendingDistribution()", F.updatePendingDistribution, ())]:
    run(lbl + " @+12s", F, fn, *args)
F.now += 365 * DAY
run("alice.withdrawAll() @+1 year", F, F.withdrawAll, "alice")

print("  -- recovery attempt: governor updatePeriodLength(0) --")
run("gov.updatePeriodLength(0)", F, F.updatePeriodLength, 0)
run("alice.withdrawAll()", F, F.withdrawAll, "alice")
print("  state:", F.snap("alice", "bob"))
run("gov.updatePeriodLength(7d) (re-enable linear mode)", F, F.updatePeriodLength, P)
F.now += 12
run("bob.exit() (TU>0 still: bob unrealised)", F, F.exit, "bob")
run("locker harvest -> distribute(100e18)", F, F.distribute, "locker", 100 * E18)
print("  => linear mode cannot be re-enabled while TU>0 (stale lastUpdate, rate=0 persists)")

print()
print("=== T01b: same block repair (honest distribute in the SAME block as donate(1)) ===")
G = Furnace(periodLength=P)
run("alice.deposit(1000e18)", G, G.deposit, "alice", 1000 * E18)
run("distribute(100e18)", G, G.distribute, "locker", 100 * E18)
G.now += 8 * DAY
run("R1 donate(1)", G, G.distribute, "locker", 1)
run("honest harvest distribute(100e18) same block", G, G.distribute, "locker", 100 * E18)
G.now += 12
run("alice.withdrawAll() next block", G, G.withdrawAll, "alice")
print("  => the attack needs one block boundary after donate(1) with no distribute >= P in that block")

print()
print("=== T01c: boundary: TU == 0 at the poke -> no revert (paid-off branch) ===")
H = Furnace(periodLength=P)
run("distribute(5) with TU=0", H, H.distribute, "locker", 5)
H.now += 12
run("updatePendingDistribution() TU=0", H, H.updatePendingDistribution)
print("  state:", H.snap())

print()
print("=== T01d: P = 0 configuration: donate(1) is harmless ===")
K = Furnace(periodLength=0)
run("alice.deposit(1000e18)", K, K.deposit, "alice", 1000 * E18)
run("donate(1) -> distribute(1)", K, K.distribute, "locker", 1)
K.now += 12
run("alice.withdrawAll()", K, K.withdrawAll, "alice")
print("  state:", K.snap("alice"))

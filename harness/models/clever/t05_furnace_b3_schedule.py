"""T05  B3 sampling-schedule invariance of the Furnace linear schedule.

U_Delta := _updatePendingDistribution after Delta seconds (L4672-L4687).
(a) flow property  U_{s+t} vs U_t o U_s  (permissionless poke L4578)  -> defect size
(b) CII for the permissionless distribute(epsilon) path (CLeverCVXLocker.donate L13471 ->
    Furnace.distribute L4530): every distribute restarts a full period over
    amount + leftover (L4808-L4814), so inserting donate(1) re-schedules the leftover.
"""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import atomic
from furnace_model import Furnace

E18 = 10**18
DAY = 86400
P = 7 * DAY
random.seed(5)

def base():
    F = Furnace(periodLength=P)
    atomic(F, F.deposit, "alice", 3000 * E18 + 12345)
    atomic(F, F.deposit, "bob", 1000 * E18 + 777)
    atomic(F, F.distribute, "locker", 700 * E18)
    return F

print("=== T05a: flow property of U_Delta (single poke at t0+5d vs k random pokes) ===")
worst = {"TU": 0, "TR": 0, "alpha": 0}
for trial in range(200):
    A = base(); B = base(); t0 = A.now
    A.now = t0 + 5 * DAY; atomic(A, A.updatePendingDistribution)
    k = random.randint(2, 30)
    cuts = sorted(random.sample(range(1, 5 * DAY), k - 1)) + [5 * DAY]
    for c in cuts:
        B.now = t0 + c; atomic(B, B.updatePendingDistribution)
    worst["TU"] = max(worst["TU"], abs(A.totalUnrealised - B.totalUnrealised))
    worst["TR"] = max(worst["TR"], abs(A.totalRealised - B.totalRealised))
    for u in ("alice", "bob"):
        worst["alpha"] = max(worst["alpha"], abs(A.getUserInfo(u)[0] - B.getUserInfo(u)[0]))
print("  max |D(s,t)| over 200 random partitions: TU=%d wei, TR=%d wei, alpha^U=%d wei" % (worst["TU"], worst["TR"], worst["alpha"]))

print()
print("=== T05b: CII w.r.t. permissionless distribute(1) (via CLeverCVXLocker.donate) ===")
def realised_profile(donate_every=None, horizon_days=28):
    F = base(); t0 = F.now; out = {}
    for d in range(1, horizon_days + 1):
        F.now = t0 + d * DAY
        if donate_every and d % donate_every == 0 and d < horizon_days:
            atomic(F, F.distribute, "locker", 1)  # R1: donate(1)
        else:
            atomic(F, F.updatePendingDistribution)
        if d in (3, 7, 14, 21, 28):
            out[d] = F.totalRealised
    return out, F
ref, _ = realised_profile(None)
att, Fa = realised_profile(1)
print("  day | realised (no insertion)      | realised (donate(1) daily)   | shortfall")
for d in sorted(ref):
    print("  %3d | %28d | %28d | %6.2f%%" % (d, ref[d], att[d], 100.0 * (ref[d] - att[d]) / ref[d]))
print("  leftover still scheduled at day 28 with daily donate(1): %d wei (%.2f%% of 700e18)" % (
    Fa.leftover(), 100.0 * Fa.leftover() / (700 * E18)))

print()
print("=== T05c: value transfer to a late depositor through re-extension ===")
def late_depositor(donate):
    F = base(); t0 = F.now
    for d in range(1, 8):
        F.now = t0 + d * DAY
        if donate and d < 7:
            atomic(F, F.distribute, "locker", 1)
        else:
            atomic(F, F.updatePendingDistribution)
    atomic(F, F.deposit, "late", 4000 * E18)  # deposit at t0+7d (= original finishAt)
    for d in range(8, 36):
        F.now = t0 + d * DAY
        atomic(F, F.updatePendingDistribution)
    return F.getUserInfo("late")[1], F.getUserInfo("alice")[1] + F.getUserInfo("bob")[1]
l0, e0 = late_depositor(False)
l1, e1 = late_depositor(True)
print("  late depositor's realised CVX of the 700e18 harvest: no insertion=%d  with 6x donate(1)=%d" % (l0, l1))
print("  early depositors' realised:                           no insertion=%d  with 6x donate(1)=%d" % (e0, e1))

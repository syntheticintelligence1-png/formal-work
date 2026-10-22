"""T10  CLeverCVXLocker reward sampling (B3, CII): harvest() is permissionless (L13482) and credits
the whole accrued vlCVX reward with the *current* totalLockedGlobal (L14068-L14070); a deposit
(L13283) increases totalLocked immediately (L13300, L13304) although the Convex lock only starts
earning at the next epoch (L13039-L13042 comment, A-CVX1).
Eager reference: reward accrued over [t_prev, t_harvest] is shared by time-weighted locked balance.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import atomic
from locker_model import Locker

E18 = 10**18
for D in (0, 1_000_000 * E18):
    L = Locker()
    atomic(L, L.deposit, "honest", 1_000_000 * E18)
    L.now += 7 * 86400  # one week of vlCVX rewards accrues in Convex (10_000 CVX after zap)
    if D:
        atomic(L, L.deposit, "att", D)                   # same tx / block as the harvest
    atomic(L, L.harvest, 10_000 * E18)                   # R1 calls harvest()
    for a in ("honest", "att"):
        if a in L.users:
            atomic(L, L._updateReward, a)
    print("D=%-26d honest reward credit=%d  attacker reward credit=%d" % (
        D, L.u("honest").rewards, L.u("att").rewards if "att" in L.users else 0))
print("eager (time-weighted) attacker entitlement for the past week = 0")

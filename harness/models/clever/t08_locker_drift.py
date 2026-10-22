"""T08  CLeverCVXLocker unlock schedule under a missed keeper epoch (B3 / B5 / exit-liveness).

processUnlockableCVX (L13665, onlyKeeper) only consumes pendingUnlocked[currentEpoch]
(L13683-L13692).  If epoch e is not processed, pendingUnlocked[e] is never moved into
totalUnlockedGlobal, while the Convex lock that expired at e is released one epoch later
and relocked (L13695-L13701) as part of `_unlocked`.  Users' entries with unlockEpoch=e are
nevertheless credited per-user by _updateUnlocked (L13964-L13966).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import atomic
from locker_model import Locker, WEEK

E18 = 10**18

def run(label, L, fn, *a):
    r = atomic(L, fn, *a)
    print("  [epoch %d] %-46s -> %s" % (L.epoch(), label, r))
    return r

def inv(L):
    v = L.invariants()
    print("     invariants: %s | %s" % (", ".join("%s=%s" % (k, v[k]) for k in v if k != "_"), v["_"]))

def week(L, process=True):
    L.now += WEEK
    if process:
        run("keeper.processUnlockableCVX()", L, L.processUnlockableCVX)

print("=== T08a: reference trace, keeper processes every epoch ===")
L = Locker()
e0 = L.epoch()
run("alice.deposit(100e18)", L, L.deposit, "alice", 100 * E18)
run("eve.deposit(100e18)", L, L.deposit, "eve", 100 * E18)
week(L, process=False)
run("bob.deposit(100e18)", L, L.deposit, "bob", 100 * E18)
for _ in range(4):
    week(L, process=False)
run("alice.unlock(100e18)", L, L.unlock, "alice", 100 * E18)
print("     alice pendingUnlockList:", L.u("alice").pendingUnlockList)
while L.epoch() < e0 + 17:
    week(L, process=False)
run("keeper.processUnlockableCVX()", L, L.processUnlockableCVX)
run("alice.withdrawUnlocked()", L, L.withdrawUnlocked, "alice")
inv(L)

print()
print("=== T08b: keeper misses epoch e0+17 (one week) ===")
L = Locker()
run("alice.deposit(100e18)", L, L.deposit, "alice", 100 * E18)
run("eve.deposit(100e18)", L, L.deposit, "eve", 100 * E18)
week(L, process=False)
run("bob.deposit(100e18)", L, L.deposit, "bob", 100 * E18)
run("carol.deposit(100e18)", L, L.deposit, "carol", 100 * E18)
for _ in range(4):
    week(L, process=False)
run("alice.unlock(100e18)   -> unlockEpoch e0+17", L, L.unlock, "alice", 100 * E18)
run("carol.unlock(100e18)   -> unlockEpoch e0+18", L, L.unlock, "carol", 100 * E18)
while L.epoch() < e0 + 17:
    week(L, process=False)
print("  [epoch %d] (keeper does not run in this epoch)" % L.epoch())
inv(L)
week(L, process=True)  # epoch e0+18
inv(L)
print("     convex locks:", L.convex.locks, " pendingUnlocked[e0+17] =", L.pendingUnlocked.get(e0 + 17))
run("alice.withdrawUnlocked()  (first: drains carol's)", L, L.withdrawUnlocked, "alice")
run("carol.withdrawUnlocked()", L, L.withdrawUnlocked, "carol")
inv(L)

print()
print("=== T08c: drift propagation 17 epochs later (residue class moved by one) ===")
week(L, process=True)  # e0+19
run("eve.unlock(100e18)  (eve's residue = e0 mod 17 -> unlockEpoch e0+34)", L, L.unlock, "eve", 100 * E18)
print("     eve pendingUnlockList:", L.u("eve").pendingUnlockList, " convex locks:", L.convex.locks)
while L.epoch() < e0 + 33:
    L.now += WEEK
    r = atomic(L, L.processUnlockableCVX)
week(L, process=True)  # e0+34
inv(L)
week(L, process=True)  # e0+35
run("eve.withdrawUnlocked()", L, L.withdrawUnlocked, "eve")
inv(L)
print("     pendingUnlocked never consumed:", {k - e0: v for k, v in L.pendingUnlocked.items() if v})

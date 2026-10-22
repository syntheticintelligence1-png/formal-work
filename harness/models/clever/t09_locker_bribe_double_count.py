"""T09  CVX custody aliasing in CLeverCVXLocker (B1): third-party bribe claim + weekly relock
       + keeper bribe harvest that trusts the claim amount.

* Votium/Paladin stashes let anyone claim *for* the locker (acknowledged in code, L13560,
  L13605); the CVX then sits in the locker balance.
* processUnlockableCVX treats every CVX above totalUnlockedGlobal as "extra" and relocks it
  (BDR, L13674, L13680, L13695-L13701).
* harvestVotiumLikeBribes skips the claim when isClaimed (L13561) and _swapToCVX counts the
  keeper-supplied _amounts[i] for token == CVX without measuring the balance (L14036-L14037);
  _distribute then pulls that amount from the locker balance (L14074-L14076).
Composition debits the CVX that backs totalUnlockedGlobal (users' unlocked principal).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import atomic
from locker_model import Locker, WEEK

E18 = 10**18

def run(label, L, fn, *a):
    r = atomic(L, fn, *a)
    print("  [epoch %d] %-58s -> %s" % (L.epoch(), label, r))
    return r

def inv(L):
    v = L.invariants()
    print("     %s | %s" % (", ".join("%s=%s" % (k, v[k]) for k in v if k != "_"), v["_"]))

for third_party_claims_first in (False, True):
    print("=== T09 third_party_claims_first=%s ===" % third_party_claims_first)
    L = Locker(platformFee=10**8)
    e0 = L.epoch()
    run("alice.deposit(1000e18)", L, L.deposit, "alice", 1000 * E18)
    run("carol.deposit(500e18)", L, L.deposit, "carol", 500 * E18)
    L.now += WEEK
    run("dave.deposit(10e18)  (a lock expiring at e0+18)", L, L.deposit, "dave", 10 * E18)
    L.now += WEEK
    run("erin.deposit(10e18)  (a lock expiring at e0+19)", L, L.deposit, "erin", 10 * E18)
    run("carol.unlock(500e18) -> unlockEpoch e0+17", L, L.unlock, "carol", 500 * E18)
    while L.epoch() < e0 + 17:
        L.now += WEEK
    run("keeper.processUnlockableCVX()", L, L.processUnlockableCVX)
    inv(L)
    L.now += WEEK  # epoch e0+18: a 200e18 CVX Votium bribe is claimable for the locker
    if third_party_claims_first:
        L.cvx += 200 * E18
        print("  [epoch %d] R1: VotiumStash.claim(CVX, idx, locker, 200e18, proof)  (permissionless)" % L.epoch())
        run("keeper.processUnlockableCVX()  (relocks 'extra' CVX)", L, L.processUnlockableCVX)
        run("keeper.harvestVotiumLikeBribes([CVX,200e18]) isClaimed=true", L, L.bribe_harvest_cvx, False, 200 * E18)
    else:
        run("keeper.harvestVotiumLikeBribes([CVX,200e18]) claims now", L, L.bribe_harvest_cvx, True, 200 * E18)
        run("keeper.processUnlockableCVX()", L, L.processUnlockableCVX)
    inv(L)
    print("     furnace received %d, platform received %d" % (L.furnace_received, L.platform_received))
    run("carol.withdrawUnlocked()", L, L.withdrawUnlocked, "carol")
    L.now += WEEK
    run("keeper.processUnlockableCVX() next week", L, L.processUnlockableCVX)
    print()

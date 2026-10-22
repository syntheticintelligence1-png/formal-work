"""T02  Furnace totalUnrealised wrap (B2 polarity + unchecked subtraction).

alpha^U_u = min(floor(U*acc/paid)+1, U) (L4707-L4712) rounds each user's unrealised UP,
while totalUnrealised is decreased exactly (L4851).  _withdraw subtracts the user's
alpha^U from totalUnrealised with an unchecked 0.7 subtraction (L4766, "never overflow
here").  When sum_u alpha^U_u > TU and all unrealised holders exit, the last withdrawal
wraps TU to 2^128-k.  Afterwards: (i) any deposit that needs >= k unrealised reverts in
_toU128 (L4754, L4861); (ii) every distribution goes to the else-branch of
_reduceGlobalDebt and is booked to totalRealised with no owner (L4851-L4852): the CVX is
stranded.
"""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import atomic, U128
from furnace_model import Furnace

E18 = 10**18

def run(label, F, fn, *a):
    r = atomic(F, fn, *a)
    print("  %-52s -> %s" % (label, r))
    return r

def ownerless_cvx(F):
    claimable = sum(F.getUserInfo(a)[1] for a in F.users)
    return F.totalRealised - claimable

print("=== T02a: single user, exact (power-of-two) fraction, P = 0 ===")
F = Furnace(periodLength=0)
run("alice.deposit(8)", F, F.deposit, "alice", 8)
run("distribute(4)", F, F.distribute, "locker", 4)
print("  state:", F.snap("alice"))
run("alice.withdrawAll()", F, F.withdrawAll, "alice")
print("  state:", F.snap("alice"))
print("  TU == 2^128-1 ?", F.totalUnrealised == U128 - 1)
run("alice.claim()", F, F.claim, "alice")
run("bob.deposit(10e18)  (needs unrealised)", F, F.deposit, "bob", 10 * E18)
run("locker distribute(1000e18)", F, F.distribute, "locker", 1000 * E18)
print("  state:", F.snap("alice", "bob"))
print("  owner-less CVX booked in totalRealised:", ownerless_cvx(F))
run("bob.deposit(10e18) again (headroom = distributed amount)", F, F.deposit, "bob", 10 * E18)
run("locker distribute(1000e18)", F, F.distribute, "locker", 1000 * E18)
print("  state:", F.snap("bob"))
print("  bob realised from a 1000e18 distribution while holding 10e18 unrealised:", F.getUserInfo("bob")[1])
print("  owner-less CVX booked in totalRealised:", ownerless_cvx(F))
run("carol.deposit(5000e18) (> headroom)", F, F.deposit, "carol", 5000 * E18)

print()
print("=== T02b: two users, generic amounts, P = 0 ===")
F = Furnace(periodLength=0)
run("alice.deposit(1e18)", F, F.deposit, "alice", 10**18)
run("bob.deposit(2e18)", F, F.deposit, "bob", 2 * 10**18)
run("distribute(1e18)", F, F.distribute, "locker", 10**18)
print("  state:", F.snap("alice", "bob"))
print("  sum alpha^U - TU =", sum(F.getUserInfo(a)[0] for a in ("alice", "bob")) - F.totalUnrealised)
run("alice.exit()", F, F.exit, "alice")
run("bob.exit()", F, F.exit, "bob")
print("  state:", F.snap("alice", "bob"))
print("  TU wrapped:", F.totalUnrealised > U128 // 2, " owner-less CVX:", ownerless_cvx(F))

print()
print("=== T02c: honest population, linear mode P=7d, random deposits/pokes, everybody exits ===")
random.seed(7)
wraps = 0
trials = 200
excess_hist = {}
for t in range(trials):
    F = Furnace(periodLength=7 * 86400)
    users = ["u%d" % i for i in range(random.randint(2, 12))]
    for u in users:
        atomic(F, F.deposit, u, random.randint(1, 10**6) * 10**15 + random.randint(0, 10**15))
    atomic(F, F.distribute, "locker", random.randint(1, 10**5) * 10**15)
    for _ in range(random.randint(1, 6)):
        F.now += random.randint(60, 86400)
        atomic(F, F.updatePendingDistribution)
        if random.random() < 0.3:
            atomic(F, F.deposit, random.choice(users), random.randint(1, 10**6) * 10**15)
    exc = sum(F.getUserInfo(u)[0] for u in users) - F.totalUnrealised
    excess_hist[exc] = excess_hist.get(exc, 0) + 1
    for u in users:
        atomic(F, F.withdrawAll, u)
    if F.totalUnrealised >= U128 // 2:
        wraps += 1
print("  trials=%d  full-exit trials ending with wrapped TU=%d" % (trials, wraps))
print("  distribution of (sum alpha^U - TU) before exit: %s" % dict(sorted(excess_hist.items())))

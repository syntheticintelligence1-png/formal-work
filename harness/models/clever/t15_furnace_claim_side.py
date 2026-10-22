"""T15  Claim-side liveness of the Furnace: can sum_u alpha^R_u exceed totalRealised (then the last
claimer's SafeMath sub at L4778 reverts, and claim is all-or-nothing, L4776)?
Equivalent (per-user U+R conservation, L4713/L4701) to sum_u alpha^U_u < totalUnrealised.
Random honest traces in both modes; also count the opposite (wrap-side) excess.
"""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import atomic, U128
from furnace_model import Furnace

random.seed(31337)
neg = pos = zero = 0
worst_neg = 0
example = None
for trial in range(1500):
    F = Furnace(periodLength=random.choice([0, 7 * 86400]))
    users = ["u%d" % i for i in range(random.randint(1, 6))]
    for step in range(random.randint(5, 40)):
        k = random.random()
        if k < 0.35:
            atomic(F, F.deposit, random.choice(users), random.randint(1, 10**22))
        elif k < 0.6:
            atomic(F, F.distribute, "locker", random.randint(1, 10**21))
        elif k < 0.75:
            F.now += random.randint(1, 10**6); atomic(F, F.updatePendingDistribution)
        elif k < 0.85:
            atomic(F, F.claim, random.choice(users))
        else:
            u = random.choice(users)
            amt = random.randint(1, 10**21)
            atomic(F, F.withdraw, u, amt)
        if F.totalUnrealised >= U128 // 2:
            break
        s = sum(F.getUserInfo(u)[0] for u in users) - F.totalUnrealised
        if s < 0:
            neg += 1
            if s < worst_neg:
                worst_neg = s; example = (trial, step, F.snap(*users))
        elif s > 0:
            pos += 1
        else:
            zero += 1
print("states sampled: sum alpha^U - TU  <0: %d   =0: %d   >0: %d" % (neg, zero, pos))
print("worst negative excess (claim-side shortfall in wei):", worst_neg)
if example:
    print("example:", example[0], example[1]); print(example[2])

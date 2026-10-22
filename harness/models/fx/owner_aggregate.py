# ShareableRebalancePool vote-owner aggregate vs. stakers' compounded balances.
#   _updateVoteOwnerBalance L15408-L15438: owner.amount = compounded(owner.amount, owner.product, supply.product)
#   _updateUserBalance     L15444-L15460: staker.amount = compounded(staker.amount, staker.product, supply.product)
#   _withdraw              L15361-L15365: ownerBalance.amount -= amount   (checked, outside the unchecked block L15354-L15358)
#   _revokeVoteSharing     L15393:        ownerBalance.amount -= staker.amount  ("no uncheck here, just in case")
# The owner aggregate is re-floored at every checkpoint of ANY of its stakers; a staker that skips
# intermediate checkpoints is floored once. Search for a trace where owner < sum(stakers).
# Run: python3 -I owner_aggregate.py
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from k4lib import Pool, Revert, PREC, fmt  # noqa

random.seed(2024)
found = None
for trial in range(20000):
    p = Pool()
    bA = random.randint(10**17, 10**21)
    bB = random.randint(10**17, 10**21)
    other = random.randint(10**18, 10**22)
    p.deposit("A", bA); p.deposit("B", bB); p.deposit("Z", other)
    owner = [bA + bB, p.prod]                      # accepted at the same product
    trace = []
    try:
        for step in range(3):
            L = random.randint(1, p.S // 3)
            p.liquidate(L)
            trace.append(("liquidate", L))
            # staker A checkpoints (owner aggregate re-compounded); B does not
            p.checkpoint("A")
            owner = [Pool.compounded(owner[0], owner[1], p.prod), p.prod]
            trace.append(("checkpoint A (owner re-floored)", None))
        p.checkpoint("B")
        owner = [Pool.compounded(owner[0], owner[1], p.prod), p.prod]
        a, b = p.bal["A"][0], p.bal["B"][0]
        if owner[0] < a + b:
            found = (bA, bB, other, trace, owner[0], a, b)
            break
    except Revert:
        continue

if found:
    bA, bB, other, trace, o, a, b = found
    print("trial found: bA=%d bB=%d other=%d" % (bA, bB, other))
    for t in trace:
        print("   ", t)
    print("after B's checkpoint: owner aggregate=%d, A=%d, B=%d, A+B=%d, deficit=%d wei" % (o, a, b, a + b, a + b - o))
    o2 = o - a
    print("A withdraws all (%d): owner -> %d" % (a, o2))
    if o2 - b < 0:
        print("B withdraws all (%d): owner %d - %d < 0 -> Panic(0x11) at L15364; rejectSharedVote also reverts at L15393" % (b, o2, b))
else:
    print("no divergence found")

# frequency
cnt = 0; tot = 0
for trial in range(5000):
    p = Pool()
    bA, bB = random.randint(10**17, 10**21), random.randint(10**17, 10**21)
    p.deposit("A", bA); p.deposit("B", bB); p.deposit("Z", random.randint(10**18, 10**22))
    owner = [bA + bB, p.prod]
    try:
        for step in range(3):
            p.liquidate(random.randint(1, p.S // 3))
            p.checkpoint("A")
            owner = [Pool.compounded(owner[0], owner[1], p.prod), p.prod]
        p.checkpoint("B")
        owner = [Pool.compounded(owner[0], owner[1], p.prod), p.prod]
    except Revert:
        continue
    tot += 1
    if owner[0] < p.bal["A"][0] + p.bal["B"][0]:
        cnt += 1
print("frequency over %d random 3-liquidation traces: owner < A+B in %d (%.1f%%)" % (tot, cnt, 100.0 * cnt / tot))

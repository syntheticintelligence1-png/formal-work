# K4 counterexample search for the f(x) rebalance pools. Run: python3 -I k4_scenarios.py
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from k4lib import *  # noqa

print("=== S0: library sanity (matches coordinator's executed values) ===")
print("mul(encode(0,0,1e9), 1)   ->", fmt(dfp_mul(encode(0, 0, 10**9), 1)))
print("mul(encode(0,0,1), 5e8)   ->", fmt(dfp_mul(encode(0, 0, 1), 5 * 10**8)))

print("\n=== S1: epoch reset (scale==0) while residual supply > 0 (L16386-L16403) ===")
# For loss L < S: x = floor((L*1e18 - err)/S) + 1 ; scale = 1e18 - x ; scale == 0 iff x == 1e18.
for S in [10**18 + 1, 10**18 + 5, 2 * 10**18, 10**24, 10**27]:
    err = 0
    # smallest L < S with x == 1e18  <=>  L*1e18 - err >= (1e18-1)*S
    Lmin = -(-((PREC - 1) * S + err) // PREC)
    if Lmin < S:
        p = Pool(); p.S = S; p.err = err
        x, f = p.notify_loss(Lmin)
        print("S=%d err=0: window L in [%d, %d] (%d values); at L=%d: x=%d scale=%d -> prod %s, residual S=%d"
              % (S, Lmin, S - 1, S - Lmin, Lmin, x, f, fmt(p.prod), p.S))
    else:
        print("S=%d: no L<S gives scale 0" % S)

print("\n--- S1b: users' view after the reset (one user owns all of S=1e18+1, L=S-1) ---")
p = Pool()
p.deposit("A", 10**18 + 1)
x, f = p.liquidate(10**18, base_out=0)
print("after liquidate(L=1e18): x=%d scale=%d prod=%s totalSupply=%d" % (x, f, fmt(p.prod), p.S))
amt, pu = p.bal["A"]
print("balanceOf(A) = compounded(%d, %s, %s) = %d   => sum_u balance = 0 != totalSupply = %d (O3c violated)"
      % (amt, fmt(pu), fmt(p.prod), Pool.compounded(amt, pu, p.prod), p.S))

print("\n=== S2: uint192 integral overflow at dust total share (L17151) ===")
lim = U192
for S in [1, 2, 10, 1000, 10**6]:
    for mag in [PREC]:
        # largest single-call amount that does not revert: floor(a*1e18/S)*mag <= 2^192-1
        amax = ((lim // mag) * S + (S - 1)) // PREC
        print("S=%-8d mag=1e18: single-call revert threshold a > %d wei (= %.4f tokens of 18 dec); cumulative threshold identical"
              % (S, amax, amax / 1e18))
# executed: reward stream after the S1b reset (S=1 orphan, mag=1e18)
p2 = Pool(); p2.deposit("A", 10**18 + 1); p2.liquidate(10**18)
rate = (10_000 * 10**18) // (7 * 86400)    # 10,000 tokens/week linear stream (assumption, see report)
t = 0; ok = True
while ok:
    t += 3600                               # someone pokes every hour (checkpoint(address(0)) is permissionless)
    try:
        p2.accumulate(rate * 3600)
    except Revert as e:
        ok = False
        print("orphan S=1, 10k tokens/week, hourly pokes: first revert after %.1f h (%.2f days): %s" % (t / 3600, t / 86400, e))
p3 = Pool(); p3.deposit("A", 10**18 + 1); p3.liquidate(10**18)
try:
    p3.accumulate(rate * 5 * 86400)
except Revert as e:
    print("orphan S=1, single poke after 5 days (%.1f tokens pending): %s" % (rate * 5 * 86400 / 1e18, e))
# rewards attributed to the orphan are unclaimable by anyone who deposits later
p4 = Pool(); p4.deposit("A", 10**18 + 1); p4.liquidate(10**18)
p4.accumulate(100 * 10**18)      # 100 tokens streamed while only the orphan wei exists
p4.deposit("B", 50 * 10**18)
p4.accumulate(100 * 10**18)
p4.checkpoint("B")
print("100 tokens while S=1 orphan, then B deposits 50e18 and 100 more tokens: claimable(B) = %d wei; unattributed = %d wei (%.6f tokens)"
      % (p4.pending["B"], 200 * 10**18 - p4.pending["B"], (200 * 10**18 - p4.pending["B"]) / 1e18))

print("\n=== S3: magnitude collapse to 0 via three liquidations (L16669-L16671) ===")
p = Pool()
p.deposit("A", 10**18)
x, f = p.liquidate(10**18 - 10**9 - 1)
print("L1=1e18-1e9-1 on S=1e18:            x=%d scale=%d -> %s  S=%d err=%d" % (x, f, fmt(p.prod), p.S, p.err))
p.deposit("B", 10**18 - p.S)
x, f = p.liquidate(10**18 - 1)
print("deposit to S=1e18; L2=1e18-1:      x=%d scale=%d -> %s  S=%d err=%d" % (x, f, fmt(p.prod), p.S, p.err))
p.deposit("C", 10**18 - p.S)
x, f = p.liquidate(10**18 - 10**9 + 1)
print("deposit to S=1e18; L3=1e18-1e9+1:  x=%d scale=%d -> %s  S=%d err=%d" % (x, f, fmt(p.prod), p.S, p.err))
p.deposit("D", 5 * 10**18)
print("D deposits 5e18 at product %s" % fmt(p.bal["D"][1]))
for what, fn in [("withdraw(D)", lambda: p.withdraw("D", 10**18)),
                 ("claimable(D)", lambda: p.claimable("D")),
                 ("balanceOf(D)", lambda: Pool.compounded(p.bal["D"][0], p.bal["D"][1], p.prod))]:
    try:
        print("  %s -> %s" % (what, fn()))
    except Revert as e:
        print("  %s -> REVERT %s" % (what, e))
before = dict(p.integral)
p.accumulate(1000 * 10**18)
print("  accumulate(1000e18) at mag 0: integral delta = %d (reward lost)"
      % (p.integral.get(epoch_exponent(p.prod), 0) - before.get(epoch_exponent(p.prod), 0)))
# a later full wipe starts a new epoch, D is still locked
p.liquidate(p.S)
print("  after a full wipe: prod=%s" % fmt(p.prod))
try:
    p.checkpoint("D")
except Revert as e:
    print("  checkpoint(D) after new epoch -> REVERT %s (permanent)" % e)

print("\n=== S4: O4d with a denormal snapshot (mag_u = 1): two small liquidations zero a ~unchanged stake ===")
p = Pool()
p.deposit("A", 10**18)
p.liquidate(10**18 - 10**9 - 1)          # -> mag 1e9 at exp 0 (normal branch)
p.deposit("B", 10**18 - p.S)
p.liquidate(10**18 - 1)                  # -> (exp 1, mag 1)
print("after setup: %s S=%d" % (fmt(p.prod), p.S))
p.deposit("U", 10**24)                   # victim deposits 1e6 tokens at a denormal product
pu = p.bal["U"][1]
S_before = p.S
print("U deposits 1e24 at %s; S=%d" % (fmt(pu), p.S))
for k in range(2):
    L = 10**18                           # 1 token liquidated out of ~1e6 tokens
    x, f = p.liquidate(L)
    real = None
    print("  small liquidation L=1e18: scale=%d -> %s  compounded(U)=%d" % (f, fmt(p.prod), Pool.compounded(10**24, pu, p.prod)))
print("  exact (real-number) stake of U = 1e24 * prod(now)/prod(U) = %.6e  vs implementation 0"
      % (10**24 * (magnitude(p.prod) * 10.0 ** (-9 * exponent(p.prod))) / (magnitude(pu) * 10.0 ** (-9 * exponent(pu)))))

print("\n=== S5: B2 commutation defect of a liquidation (lazy floor vs eager b*(S-L)/S) ===")
random.seed(7)
worst = 0; total_orphan = 0
for trial in range(2000):
    p = Pool()
    users = ["u%d" % i for i in range(random.randint(1, 8))]
    for u in users:
        p.deposit(u, random.randint(1, 10**6) * 10**random.randint(12, 21))
    for _ in range(random.randint(1, 4)):
        L = random.randint(1, p.S - 1) if p.S > 1 else 0
        if L == 0:
            break
        eager = {u: Pool.compounded(*p.bal[u], p.prod) for u in users}
        Sb = p.S
        p.liquidate(L)
        lazy = {u: Pool.compounded(*p.bal[u], p.prod) for u in users}
        for u in users:
            e = eager[u] * (Sb - L) / Sb
            d = lazy[u] - e
            if d > 1e-6 * max(1, e):   # positive defect would be liability-inflating
                print("POSITIVE DEFECT", trial, u, d)
            worst = min(worst, d / max(e, 1))
    total_orphan = max(total_orphan, p.S - sum(Pool.compounded(*p.bal[u], p.prod) for u in users))
print("2000 random traces: max relative per-user defect = %.3e (polarity <= 0); max orphan S - sum(balances) = %d wei"
      % (worst, total_orphan))

print("\n=== S6: _lossNumerator underflow (L16392): tiny loss after a large-error liquidation ===")
p = Pool(); p.deposit("A", 10**24); p.liquidate(3 * 10**23 + 7)
print("err after first liquidation = %d" % p.err)
try:
    p.liquidate(1)
except Revert as e:
    print("liquidate(L=1 wei) -> REVERT %s" % e)

"""T04  B2 lazy-eager refinement of the Furnace accumulator (commutation defect, polarity).

alpha_u(sigma) = getUserInfo(u) (L4432-L4448) applied to the lazy state.
Eager reference M^E (one reduction event, amount a, abstract total T = sum_u alpha^U_u):
    a >= T :  U'_u = 0,                R'_u = R_u + U_u
    a <  T :  U'_u = U_u (T-a)/T,      R'_u = R_u + U_u a/T          (exact rationals)
For every action in random honest traces we compute
    delta_a(sigma) = alpha(a(sigma)) - a^E(alpha(sigma))     (per user, U component)
and report max/min per user and the polarity sign(sum_u delta_u).
Deposit/withdraw/claim are applied to M^E with the same amounts the implementation used.
"""
import os, sys, random
from fractions import Fraction as Fr
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import atomic, U128
from furnace_model import Furnace

random.seed(2024)
E18 = 10**18
stats = {}

def alpha_vec(F, users):
    return {u: F.getUserInfo(u) for u in users}

def eager_reduce(av, a):
    T = sum(Fr(v[0]) for v in av.values())
    out = {}
    for u, (U, R) in av.items():
        if T == 0:
            out[u] = (Fr(U), Fr(R))
        elif a >= T:
            out[u] = (Fr(0), Fr(R) + U)
        else:
            out[u] = (Fr(U) * (T - a) / T, Fr(R) + Fr(U) * a / T)
    return out

def record(kind, d):
    s = stats.setdefault(kind, {"n": 0, "max": Fr(-10**9), "min": Fr(10**9), "sum_pos": 0, "sum_neg": 0, "sum_zero": 0})
    s["n"] += 1
    for v in d.values():
        s["max"] = max(s["max"], v)
        s["min"] = min(s["min"], v)
    tot = sum(d.values())
    if tot > 0: s["sum_pos"] += 1
    elif tot < 0: s["sum_neg"] += 1
    else: s["sum_zero"] += 1

for trial in range(300):
    P = random.choice([0, 7 * 86400])
    F = Furnace(periodLength=P)
    users = ["u%d" % i for i in range(random.randint(2, 8))]
    for step in range(40):
        before = alpha_vec(F, users)
        kind = random.choice(["dep", "dep", "dist", "dist", "poke", "wd", "claim"])
        if kind == "dep":
            u = random.choice(users); amt = random.randint(1, 10**4) * 10**15 + random.randint(0, 10**15)
            r = atomic(F, F.deposit, u, amt)
            if r[0] != "ok": continue
            nu, nr = r[1]
            exp = dict((k, (Fr(v[0]), Fr(v[1]))) for k, v in before.items())
            exp[u] = (exp[u][0] + nu, exp[u][1] + nr)
        elif kind == "dist":
            amt = random.randint(1, 10**3) * 10**15
            if P == 0:
                r = atomic(F, F.distribute, "locker", amt)
                if r[0] != "ok": continue
                exp = eager_reduce(before, amt)
            else:  # linear mode: distribute only schedules; no reduction in this block
                r = atomic(F, F.distribute, "locker", amt)
                if r[0] != "ok": continue
                exp = dict((k, (Fr(v[0]), Fr(v[1]))) for k, v in before.items())
        elif kind == "poke":
            dt = random.randint(1, 3 * 86400)
            F.now += dt
            tu0, tr0 = F.totalUnrealised, F.totalRealised
            r = atomic(F, F.updatePendingDistribution)
            if r[0] != "ok": continue
            a = (F.totalRealised - tr0)  # amount actually reduced (capped at TU)
            if F.totalUnrealised == 0 and tu0 > 0:
                a = tu0
            exp = eager_reduce(before, a) if a > 0 else dict((k, (Fr(v[0]), Fr(v[1]))) for k, v in before.items())
            kind = "poke(linear)"
        elif kind == "wd":
            u = random.choice(users)
            r = atomic(F, F.withdrawAll, u)
            if r[0] != "ok": continue
            exp = dict((k, (Fr(v[0]), Fr(v[1]))) for k, v in before.items())
            exp[u] = (exp[u][0] - r[1], exp[u][1])
        else:
            u = random.choice(users)
            r = atomic(F, F.claim, u)
            if r[0] != "ok": continue
            exp = dict((k, (Fr(v[0]), Fr(v[1]))) for k, v in before.items())
            exp[u] = (exp[u][0], exp[u][1] - r[1])
        after = alpha_vec(F, users)
        d = {u: Fr(after[u][0]) - exp[u][0] for u in users}
        regime = "wrapped-TU" if F.totalUnrealised >= U128 // 2 else "sane-TU"
        record(kind + "/" + regime, d)

print("per-action commutation defect on the unrealised component, delta^U = alpha(a(s)) - a^E(alpha(s)):")
for k, s in sorted(stats.items()):
    print("  %-14s n=%5d  max=%s  min=%s  polarity(sum>0/sum<0/sum=0)=%d/%d/%d" % (
        k, s["n"], float(s["max"]), float(s["min"]), s["sum_pos"], s["sum_neg"], s["sum_zero"]))
print("(realised component is the exact complement: delta^R = -delta^U, because U+R is conserved per user)")

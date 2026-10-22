# ExponentialMovingAverageV8 (L9216-L9249) as used by TreasuryV2._updateEMALeverageRatio (L9908-L9915).
# LogExpMathV8.exp is treated as an approximation oracle: exp_oracle(x) = floor(e^(x/1e18) * 1e18) (assumed
# |error| <= a few 1e-18 relative, Balancer documentation [C]); internals not re-verified.
# Run: python3 -I ema.py
import math, random
from decimal import Decimal, getcontext
getcontext().prec = 60
PREC = 10**18
U96 = (1 << 96) - 1


def exp_oracle(neg_e):  # LogExpMathV8.exp(-int256(e)) for e in [0, 41e18]
    return int((Decimal(-neg_e) / Decimal(PREC)).exp() * PREC)


class EMA:
    def __init__(s, t, T, v, e):
        s.lastTime, s.T, s.lastValue, s.lastEma = t, T, v, e

    def value(s, now):
        if s.lastTime < now:
            dt = now - s.lastTime
            e = (dt * PREC) // s.T
            if e > 41 * PREC:
                return s.lastValue
            a = exp_oracle(e)
            return (s.lastValue * (PREC - a) + s.lastEma * a) // PREC
        return s.lastEma

    def save(s, v, now):
        s.lastEma = s.value(now) & U96
        s.lastValue = v
        s.lastTime = now

    def copy(s):
        return EMA(s.lastTime, s.T, s.lastValue, s.lastEma)


print("=== flow property: U_{s+t} vs U_t o U_s with an intermediate poke that re-samples the SAME value ===")
random.seed(1)
worst = 0
for _ in range(20000):
    T = random.choice([60, 600, 3600, 86400])
    v = random.randint(PREC, 100 * PREC)
    e0 = random.randint(PREC, 100 * PREC)
    s1, s2 = random.randint(1, 5 * T), random.randint(1, 5 * T)
    a = EMA(0, T, v, e0)
    b = a.copy(); b.save(v, s1)
    d = a.value(s1 + s2) - b.value(s1 + s2)
    worst = max(worst, abs(d))
print("max |D(s,t)| over 20000 random cases = %d wei (quantized; exact in real arithmetic)" % worst)

print("\n=== CII: a permissionless poke (harvest(), L9648) samples a transient leverage value ===")
for T in [60, 600, 3600]:
    base = 2 * PREC                     # steady leverage ratio 2.0
    ema = EMA(0, T, base, base)
    # block N (t=1000): attacker mints xToken (L9578 samples the pre-mint ratio 2.0), then calls harvest()
    # which samples the post-mint ratio 1.2 in the same block (lastTime==now: lastEma unchanged, lastValue overwritten)
    ema.save(base, 1000); ema.save(int(1.2 * PREC), 1000)
    # block N+1 (t=1012): attacker redeems xToken (L9599 samples pre-redeem ratio 1.2 -> EMA moves)
    ema.save(int(1.2 * PREC), 1012)
    after = ema.value(1012)
    ema.save(base, 1012)               # same block: back to 2.0 after the redeem (sampled by a later poke in block N+1)
    print("T=%5ds: EMA %.6f -> %.6f after one 12s held sample (%.3f%% move); value 1h later %.6f"
          % (T, base / 1e18, after / 1e18, 100 * (base - after) / base, ema.value(1012 + 3600) / 1e18))
